"""Single-host API/worker separation using durable jobs and an explicit control channel.

No pickled objects, arbitrary method names, imports, or model inference are sent
through this channel. Both processes use the same local data directory.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
import logging
import os
from pathlib import Path
import sqlite3
import threading
import time
import uuid

import numpy as np

from vvoice.core.errors import JobQueueFullError, ModelConfigurationError, public_error_message
from vvoice.core.observability import get_request_id
from vvoice.domains.asr.service import Transcription
from vvoice.inference.tts.base import GeneratedSpeech
from vvoice.shared.audio.io import encode_wav, load_audio_bytes
from vvoice.shared.jobs.durable import FileLock
from vvoice.shared.security.principal import current_actor_id


logger = logging.getLogger("vvoice.worker.control")
CONTROL_ACTIONS = {
    "tts": {"warmup", "warmup_all", "unload", "set_enabled", "import_profile", "activate", "rollback"},
    "asr": {"warmup", "warmup_all"},
}


class WorkerControlStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS commands (
                    command_id TEXT PRIMARY KEY, domain TEXT NOT NULL, action TEXT NOT NULL,
                    payload TEXT NOT NULL, status TEXT NOT NULL, created REAL NOT NULL,
                    expires REAL NOT NULL, result TEXT, error TEXT,
                    actor_id TEXT, request_id TEXT
                );
                CREATE INDEX IF NOT EXISTS command_pending ON commands(status,created);
                CREATE TABLE IF NOT EXISTS runtime (id INTEGER PRIMARY KEY, payload TEXT NOT NULL);
            """)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA busy_timeout=30000")
        try:
            with db:
                yield db
        finally:
            db.close()

    def submit(self, domain, action, payload, *, timeout_seconds=180) -> str:
        if action not in CONTROL_ACTIONS.get(domain, ()):
            raise ModelConfigurationError("Unsupported worker control command")
        command_id, now = str(uuid.uuid4()), time.time()
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("UPDATE commands SET status='expired' WHERE status='pending' AND expires<?", (now,))
            count = db.execute("SELECT COUNT(*) FROM commands WHERE status IN ('pending','running')").fetchone()[0]
            if count >= 32:
                raise JobQueueFullError("Worker control queue is full")
            db.execute("INSERT INTO commands VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                       (command_id, domain, action, json.dumps(payload), "pending", now,
                        now + timeout_seconds, None, None, current_actor_id(), get_request_id()))
        return command_id

    def get(self, command_id) -> dict:
        with self.connection() as db:
            row = db.execute("SELECT * FROM commands WHERE command_id=?", (command_id,)).fetchone()
        if row is None:
            raise ModelConfigurationError("Worker command not found")
        result = dict(row)
        result["payload"] = json.loads(result["payload"])
        result["result"] = json.loads(result["result"]) if result["result"] else None
        return result

    def expire(self, command_id):
        with self.connection() as db:
            db.execute("UPDATE commands SET status='expired' WHERE command_id=? AND status='pending'",
                       (command_id,))

    def wait(self, command_id, *, timeout_seconds=180):
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            command = self.get(command_id)
            if command["status"] == "succeeded":
                return command["result"]
            if command["status"] in {"failed", "expired"}:
                raise ModelConfigurationError(command["error"] or "Worker command expired")
            time.sleep(min(0.1, max(0, deadline - time.monotonic())))
        self.expire(command_id)
        raise ModelConfigurationError("External worker command timed out; inspect worker status")

    def recover(self):
        with self.connection() as db:
            db.execute("UPDATE commands SET status='failed',error='Worker restarted during command; inspect model state' WHERE status='running'")
            db.execute("DELETE FROM commands WHERE status NOT IN ('pending','running') AND created<?",
                       (time.time() - 7 * 86400,))

    def claim(self):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("UPDATE commands SET status='expired' WHERE status='pending' AND expires<?", (time.time(),))
            row = db.execute("SELECT command_id FROM commands WHERE status='pending' ORDER BY created LIMIT 1").fetchone()
            if row is None:
                return None
            db.execute("UPDATE commands SET status='running' WHERE command_id=?", (row[0],))
        return self.get(row[0])

    def finish(self, command_id, result=None, error=None):
        with self.connection() as db:
            db.execute("UPDATE commands SET status=?,result=?,error=? WHERE command_id=? AND status='running'",
                       ("failed" if error else "succeeded", json.dumps(result), error, command_id))

    def publish(self, payload):
        with self.connection() as db:
            db.execute("INSERT INTO runtime VALUES(1,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                       (json.dumps({**payload, "updated_at": time.time()}),))

    def status(self, *, max_age_seconds=10) -> dict:
        with self.connection() as db:
            row = db.execute("SELECT payload FROM runtime WHERE id=1").fetchone()
        value = json.loads(row[0]) if row else {}
        fresh = time.time() - value.get("updated_at", 0) <= max_age_seconds
        return {**value, "online": bool(value.get("online")) and fresh}


class WorkerControlServer:
    def __init__(self, store: WorkerControlStore, tts, asr):
        self.store, self.tts, self.asr = store, tts, asr
        self._stop = threading.Event()
        self._thread = None
        self._ready = threading.Event()
        self._startup_error = None
        self._last = {"tts_catalog": {"models": [], "default_models": {}}, "asr_loaded_languages": []}

    def start(self):
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="worker-control", daemon=True)
        self._thread.start()
        if not self._ready.wait(10):
            raise RuntimeError("Worker control startup timed out")
        if self._startup_error:
            raise RuntimeError(self._startup_error)

    def publish_status(self):
        try:
            self._last = {"tts_catalog": self.tts.model_catalog(),
                          "asr_loaded_languages": list(self.asr.loaded_languages)}
        except Exception:
            logger.exception("worker_catalog_snapshot_failed")
        self.store.publish({**self._last, "online": True, "pid": os.getpid()})

    def _heartbeat(self):
        while not self._stop.wait(1):
            try:
                self.publish_status()
            except Exception:
                logger.exception("worker_heartbeat_failed")

    def _execute(self, command):
        domain, action, payload = command["domain"], command["action"], command["payload"]
        # Explicit dispatch prevents stored input from becoming arbitrary Python calls.
        if domain == "tts":
            if action == "warmup":
                return self.tts.warmup(payload.get("language"), payload.get("model_id"))
            if action == "warmup_all":
                return self.tts.warmup_all()
            if action == "unload":
                return self.tts.unload(payload["model_id"])
            if action == "set_enabled":
                return self.tts.set_enabled(payload["model_id"], payload["enabled"])
            if action == "import_profile":
                return self.tts.import_profile(payload["definition"])
            if action == "activate":
                return self.tts.activate(payload["model_id"])
            if action == "rollback":
                return self.tts.rollback(payload["model_id"], payload["version"])
        elif domain == "asr":
            if action == "warmup":
                return self.asr.warmup(payload.get("language"))
            if action == "warmup_all":
                return self.asr.warmup_all()
        raise ModelConfigurationError("Unsupported worker control command")

    def _run(self):
        lock = FileLock(self.store.path.with_suffix(".worker.lock"))
        if not lock.acquire(blocking=False):
            self._startup_error = "An inference control worker already owns this data directory"
            self._ready.set()
            return
        heartbeat = None
        try:
            self.store.recover()
            self.publish_status()
            heartbeat = threading.Thread(target=self._heartbeat, name="worker-heartbeat", daemon=True)
            heartbeat.start()
            self._ready.set()
            while not self._stop.is_set():
                command = self.store.claim()
                if command is None:
                    self._stop.wait(0.1)
                    continue
                try:
                    result = self._execute(command)
                    self.publish_status()
                    self.store.finish(command["command_id"], result=result)
                except Exception as exc:
                    logger.exception("worker_command_failed", extra={"command_id": command["command_id"]})
                    self.store.finish(command["command_id"], error=public_error_message(exc))
        except Exception as exc:
            self._startup_error = str(exc)
            self._ready.set()
            logger.exception("worker_control_failed")
        finally:
            self._stop.set()
            if heartbeat is not None:
                heartbeat.join(timeout=5)
            try:
                self.store.publish({**self._last, "online": False, "pid": os.getpid()})
            finally:
                lock.release()

    def shutdown(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=35)
            if self._thread.is_alive():
                raise RuntimeError("Worker control is still completing an active command")


class _RemoteBase:
    domain = ""

    def __init__(self, local, jobs, control: WorkerControlStore, *, timeout_seconds=600):
        self.local, self.jobs, self.control = local, jobs, control
        self.timeout_seconds = float(timeout_seconds)

    def __getattr__(self, name):
        # Only metadata/configuration methods remain on the API process. Inference
        # methods and model management operations are explicitly overridden below.
        return getattr(self.local, name)

    def _ensure_worker(self):
        if not self.control.status()["online"]:
            raise ModelConfigurationError("External inference worker is offline; start python -m vvoice.worker")

    def _command(self, action, **payload):
        self._ensure_worker()
        command_id = self.control.submit(self.domain, action, payload, timeout_seconds=self.timeout_seconds)
        return self.control.wait(command_id, timeout_seconds=self.timeout_seconds)

    def _wait_job(self, job):
        deadline = time.monotonic() + self.timeout_seconds
        while time.monotonic() < deadline:
            result = self.jobs.get(job.job_id)
            if result.status == "succeeded":
                return result
            if result.status in {"failed", "cancelled"}:
                raise ModelConfigurationError(f"External {self.domain.upper()} job {result.job_id} {result.status}")
            time.sleep(min(0.1, max(0, deadline - time.monotonic())))
        try:
            self.jobs.cancel(job.job_id)
        except Exception:
            logger.exception("timed_out_remote_job_cancel_failed", extra={"job_id": job.job_id})
        raise ModelConfigurationError(f"External inference timed out; cancellation requested for job {job.job_id}")

    def warmup_all(self):
        return self._command("warmup_all")

    def close(self):
        # API shutdown must not stop the separately owned worker process.
        close = getattr(self.local, "close", None)
        if close is not None:
            close()


class RemoteTtsService(_RemoteBase):
    domain = "tts"

    def synthesize(self, *, text, reference_audio, reference_sample_rate, reference_text,
                   language=None, model_id=None, num_steps=None, speed=None):
        self._ensure_worker()
        resolved = self.local.resolve_parameters(language, model_id, num_steps, speed)
        job = self.jobs.create_from_snapshot(
            voice_id="direct-" + uuid.uuid4().hex, text=text,
            reference_bytes=encode_wav(reference_audio, reference_sample_rate),
            reference_text=reference_text, language=resolved["language"],
            model_id=resolved["model_id"], num_steps=resolved.get("num_steps"), speed=resolved.get("speed"),
            provenance={**resolved, "source": "synchronous_api"},
            actor_id=current_actor_id(), request_id=get_request_id(),
        )
        completed = self._wait_job(job)
        samples, sample_rate = load_audio_bytes(completed.output_path.read_bytes())
        return GeneratedSpeech(np.asarray(samples, dtype=np.float32), sample_rate, len(samples) / sample_rate)

    def warmup(self, language=None, model_id=None):
        return self._command("warmup", language=language, model_id=model_id)

    def unload(self, model_id):
        return self._command("unload", model_id=model_id)

    def set_enabled(self, model_id, enabled):
        self._command("set_enabled", model_id=model_id, enabled=enabled)
        return self.local.set_enabled(model_id, enabled)

    def import_profile(self, definition):
        self._command("import_profile", definition=definition)
        self.local.import_profile(definition)
        return self.model_catalog()

    def activate(self, model_id):
        result = self._command("activate", model_id=model_id)
        self.local.activate(model_id)
        return result

    def rollback(self, model_id, version):
        self._command("rollback", model_id=model_id, version=version)
        self.local.rollback(model_id, version)
        return self.model_catalog()

    def model_catalog(self):
        catalog = self.local.model_catalog()
        status = self.control.status()
        worker_models = {model["model_id"]: model for model in status.get("tts_catalog", {}).get("models", [])}
        for model in catalog["models"]:
            remote = worker_models.get(model["model_id"], {}) if status["online"] else {}
            model["loaded"] = bool(remote.get("loaded"))
            if model["status"] in {"available", "loaded"}:
                if not status["online"]:
                    model.update(status="worker_offline", ready=False,
                                 message="External inference worker is offline.")
                elif remote.get("status") == "error":
                    model.update(status="error", ready=False, message=remote.get("message"))
                else:
                    model["status"] = "loaded" if model["loaded"] else "available"
        return {**catalog, "worker_online": status["online"]}

    @property
    def loaded_languages(self):
        return tuple(sorted({language for model in self.model_catalog()["models"]
                             if model["loaded"] for language in model["languages"]}))

    @property
    def is_loaded(self):
        return bool(self.loaded_languages)

    def readiness_checks(self):
        return {**self.local.readiness_checks(), "tts_worker_online": self.control.status()["online"]}


class RemoteAsrService(_RemoteBase):
    domain = "asr"

    def transcribe(self, samples, sample_rate, language=None):
        self._ensure_worker()
        normalized = language or self.local._settings.default_language
        self.local.sample_rate_for(normalized)
        job = self.jobs.create_from_audio(audio_bytes=encode_wav(samples, sample_rate),
                                          filename="direct-reference.wav", language=normalized)
        completed = self._wait_job(job)
        return Transcription(completed.text or "", completed.sample_rate or sample_rate,
                             tuple(completed.segments))

    def warmup(self, language=None):
        self.local.sample_rate_for(language)
        return self._command("warmup", language=language)

    @property
    def loaded_languages(self):
        status = self.control.status()
        return tuple(status.get("asr_loaded_languages", ())) if status["online"] else ()

    @property
    def is_loaded(self):
        return bool(self.loaded_languages)
