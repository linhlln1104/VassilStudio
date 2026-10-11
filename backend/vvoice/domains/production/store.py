from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3


class ProductionStore:
    """Small transactional document store with indexed project boundaries.

    A connection is local to one operation/thread; writes use BEGIN IMMEDIATE so
    revision checks and related records commit together, including after restart.
    """

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "production.sqlite3"
        with self.transaction() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS records (
                    kind TEXT NOT NULL,
                    id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY(kind, id)
                );
                CREATE INDEX IF NOT EXISTS records_project ON records(kind, project_id);
                CREATE INDEX IF NOT EXISTS records_status ON records(kind, json_extract(payload, '$.status'));
                CREATE TABLE IF NOT EXISTS idempotency (
                    scope TEXT NOT NULL,
                    key_hash TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    record_id TEXT NOT NULL,
                    PRIMARY KEY(scope, key_hash)
                );
            """)

    @contextmanager
    def transaction(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA busy_timeout=30000")
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def get(db, kind: str, record_id: str) -> dict | None:
        row = db.execute(
            "SELECT payload FROM records WHERE kind=? AND id=?", (kind, record_id),
        ).fetchone()
        return json.loads(row["payload"]) if row else None

    @staticmethod
    def list(db, kind: str, project_id: str | None = None) -> list[dict]:
        query = "SELECT payload FROM records WHERE kind=?"
        parameters = [kind]
        if project_id is not None:
            query += " AND project_id=?"
            parameters.append(project_id)
        return [json.loads(row["payload"]) for row in db.execute(query, parameters)]

    @staticmethod
    def put(db, kind: str, record_id: str, data: dict) -> None:
        db.execute(
            "INSERT INTO records(kind,id,project_id,payload) VALUES(?,?,?,?) "
            "ON CONFLICT(kind,id) DO UPDATE SET payload=excluded.payload",
            (kind, record_id, data.get("project_id", ""),
             json.dumps(data, ensure_ascii=False, allow_nan=False)),
        )

    @staticmethod
    def active_takes(db) -> list[dict]:
        rows = db.execute(
            "SELECT payload FROM records WHERE kind='take' AND "
            "json_extract(payload,'$.status') IN ('pending','queued','running','cancelling') "
            "ORDER BY CASE json_extract(payload,'$.status') WHEN 'pending' THEN 1 ELSE 0 END, "
            "json_extract(payload,'$.created_at') LIMIT 256"
        )
        return [json.loads(row["payload"]) for row in rows]
