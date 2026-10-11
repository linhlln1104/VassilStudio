"""Single-host durable dispatch, shared by the API and an optional worker process.

SQLite owns task claims; record JSON remains the portable v1 metadata format.
An OS lock permits one worker host per queue, released by the OS on process death.
This prevents two native inference attempts publishing the same job concurrently.
"""
from __future__ import annotations

import contextvars
import json
import logging
import os
from pathlib import Path
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime

logger = logging.getLogger(__name__)


class FileLock:
    def __init__(self, path: Path):
        self.path = path
        self._thread = threading.RLock()
        self._depth = 0
        self._file = None

    def acquire(self, blocking=True):
        if not self._thread.acquire(blocking=blocking):
            return False
        if self._depth:
            self._depth += 1
            return True
        self.path.parent.mkdir(parents=True, exist_ok=True)
        stream = self.path.open('a+b')
        if stream.seek(0, 2) == 0:
            stream.write(b'0')
            stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                while True:
                    try:
                        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                        break
                    except OSError:
                        if not blocking:
                            raise
                        time.sleep(.02)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        except OSError:
            stream.close()
            self._thread.release()
            return False
        self._file = stream
        self._depth = 1
        return True

    def release(self):
        self._depth -= 1
        if self._depth == 0:
            stream = self._file
            stream.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
            stream.close()
            self._file = None
        self._thread.release()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *_):
        self.release()


class DurableExecutor:
    def __init__(self, root: Path, callback, *, max_workers=1, enabled=True):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / 'queue.sqlite3'
        self.callback = callback
        self.enabled = enabled
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._threads = []
        self._start_lock = threading.Lock()
        self._workers = max(1, max_workers)
        self._contexts = {}
        with self.connection() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS tasks(
                    job_id TEXT PRIMARY KEY, state TEXT NOT NULL,
                    created REAL NOT NULL, heartbeat REAL, last_error TEXT);
                CREATE INDEX IF NOT EXISTS tasks_claim ON tasks(state,created);
                CREATE TABLE IF NOT EXISTS records(
                    job_id TEXT PRIMARY KEY, status TEXT NOT NULL, created TEXT NOT NULL,
                    model_id TEXT, key_hash TEXT, fingerprint TEXT, payload TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS records_status ON records(status,created);
                CREATE INDEX IF NOT EXISTS records_key ON records(key_hash);
                CREATE TABLE IF NOT EXISTS dedup(
                    key_hash TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, job_id TEXT NOT NULL,
                    expires REAL NOT NULL);
            ''')

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('PRAGMA busy_timeout=30000')
        try:
            with db:
                yield db
        finally:
            db.close()

    def record(self, value: dict):
        with self.connection() as db:
            db.execute('''INSERT INTO records VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(job_id) DO UPDATE SET status=excluded.status,created=excluded.created,
                model_id=excluded.model_id,key_hash=excluded.key_hash,
                fingerprint=excluded.fingerprint,payload=excluded.payload''',
                (value['job_id'], value['status'], value['created_at'], value.get('model_id'),
                 value.get('idempotency_key_hash'), value.get('request_fingerprint'),
                 json.dumps(value, ensure_ascii=False)))
            if value.get('idempotency_key_hash') and value.get('request_fingerprint'):
                expires = datetime.fromisoformat(value['created_at']).timestamp() + 30 * 86400
                db.execute('''INSERT INTO dedup VALUES(?,?,?,?)
                    ON CONFLICT(key_hash) DO UPDATE SET fingerprint=excluded.fingerprint,
                    job_id=excluded.job_id,expires=excluded.expires WHERE dedup.expires<=?''',
                           (value['idempotency_key_hash'], value['request_fingerprint'],
                            value['job_id'], expires, time.time()))

    def record_ids(self, *, status=None, model_id=None, limit=None, offset=0):
        clauses, args = [], []
        for column, value in [('status', status), ('model_id', model_id)]:
            if value is not None:
                clauses.append(f'{column}=?')
                args.append(value)
        query = 'SELECT job_id FROM records'
        if clauses:
            query += ' WHERE ' + ' AND '.join(clauses)
        query += ' ORDER BY created DESC,job_id LIMIT ? OFFSET ?'
        args += [-1 if limit is None else max(0, int(limit)), max(0, int(offset))]
        with self.connection() as db:
            return [r[0] for r in db.execute(query, args)]

    def key_record(self, key_hash):
        if not key_hash:
            return None
        with self.connection() as db:
            row = db.execute('SELECT * FROM dedup WHERE key_hash=? AND expires>?',
                             (key_hash, time.time())).fetchone()
            return dict(row) if row else None

    def remove_record(self, job_id):
        with self.connection() as db:
            db.execute('DELETE FROM records WHERE job_id=?', (job_id,))
            db.execute("DELETE FROM tasks WHERE job_id=? AND state='done'", (job_id,))

    def pending_ids(self):
        with self.connection() as db:
            return {r[0] for r in db.execute("SELECT job_id FROM tasks WHERE state!='done'")}

    def active_record_ids(self):
        with self.connection() as db:
            return {r[0] for r in db.execute(
                "SELECT job_id FROM records WHERE status IN ('queued','running','cancelling')")}

    def submit(self, fn, job_id):
        if self._stop.is_set():
            raise RuntimeError('The durable executor is stopping')
        if self.enabled:
            self._contexts[job_id] = contextvars.copy_context()
        with self.connection() as db:
            db.execute("""INSERT INTO tasks VALUES(?, 'pending', ?, NULL, NULL)
                       ON CONFLICT(job_id) DO UPDATE SET state='pending'
                       WHERE tasks.state='done'""",
                       (job_id, time.time()))
        self._wake.set()
        self.start()

    def start(self):
        if not self.enabled or self._stop.is_set():
            return
        with self._start_lock:
            if self._threads:
                return
            # One supervisor holds the OS lock on the same thread for its lifetime.
            supervisor = threading.Thread(target=self._supervise, daemon=True,
                                          name='vassil-durable-worker')
            self._threads.append(supervisor)
            supervisor.start()

    def _supervise(self):
        lock = FileLock(self.root / '.worker.lock')
        if not lock.acquire(blocking=False):
            logger.info('durable_worker_already_owned', extra={'queue': self.root.name})
            return
        try:
            with self.connection() as db:
                db.execute("UPDATE tasks SET state='pending',heartbeat=NULL WHERE state='running'")
            workers = [threading.Thread(target=self._work, daemon=True,
                       name=f'vassil-job-{n}') for n in range(self._workers)]
            for worker in workers:
                worker.start()
            for worker in workers:
                worker.join()
        finally:
            lock.release()

    def _claim(self):
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT job_id FROM tasks WHERE state='pending' ORDER BY created LIMIT 1").fetchone()
            if row:
                db.execute("UPDATE tasks SET state='running',heartbeat=? WHERE job_id=?",
                           (time.time(), row[0]))
            return row[0] if row else None

    def _work(self):
        while not self._stop.is_set():
            job_id = self._claim()
            if job_id is None:
                self._wake.wait(.2)
                self._wake.clear()
                continue
            finished = threading.Event()
            heartbeat = threading.Thread(target=self._heartbeat, args=(job_id, finished), daemon=True)
            heartbeat.start()
            error = None
            try:
                context = self._contexts.pop(job_id, contextvars.Context())
                context.run(self.callback, job_id)
            except Exception:
                logger.exception('durable_dispatch_failed', extra={'job_id': job_id})
                error = 'dispatch_failed'
            finally:
                finished.set()
                heartbeat.join(timeout=2)
                with self.connection() as db:
                    db.execute("UPDATE tasks SET state='done',last_error=?,heartbeat=? WHERE job_id=?",
                               (error, time.time(), job_id))

    def _heartbeat(self, job_id, finished):
        while not finished.wait(5):
            with self.connection() as db:
                db.execute('UPDATE tasks SET heartbeat=? WHERE job_id=?', (time.time(), job_id))

    def shutdown(self, wait=False, cancel_futures=False):
        # Pending work stays durable; shutdown must never cancel accepted queue records.
        self._stop.set()
        self._wake.set()
        if wait:
            for thread in self._threads:
                thread.join()
