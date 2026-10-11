from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
from io import StringIO
import json
import logging
import math
from pathlib import Path
import re
import threading
import uuid
import zipfile

from vvoice.core.errors import JobQueueFullError, VVoiceError, public_error_message
from vvoice.core.observability import get_request_id
from vvoice.domains.production.store import ProductionStore
from vvoice.shared.jobs.integrity import idempotency_key_hash, request_fingerprint
from vvoice.shared.jobs.storage import atomic_write_bytes, contained_path
from vvoice.shared.language import normalize_language


logger = logging.getLogger("vvoice.production")
TERMINAL = {"succeeded", "failed", "cancelled"}
ROW_FIELDS = {"external_id", "text", "language", "voice_id", "model_id", "num_steps", "speed"}


class ProductionError(VVoiceError):
    def __init__(self, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.status_code = status_code


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _id() -> str:
    return str(uuid.uuid4())


def _check_revision(record: dict, expected: int) -> None:
    if record["revision"] != expected:
        raise ProductionError(
            f"Revision changed: expected {expected}, current {record['revision']}. Reload and retry.",
            409,
        )


def _page(items: list, limit: int = 100, offset: int = 0) -> dict:
    return {"items": items[offset:offset + limit], "total": len(items)}


class ProductionService:
    """Durable authoring and batch orchestration; inference stays in TtsJobService."""

    def __init__(self, directory: Path, tts_jobs, tts, voices, *, max_text_chars: int = 5000):
        self.store = ProductionStore(directory)
        self.directory = self.store.directory
        self.jobs, self.tts, self.voices = tts_jobs, tts, voices
        self.max_text_chars = max_text_chars
        for name in ("references", "audio", "exports"):
            (self.directory / name).mkdir(exist_ok=True)
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="production-dispatch", daemon=True)
        self._thread.start()

    def shutdown(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=35)
            if self._thread.is_alive():
                raise RuntimeError("Production dispatcher did not stop within its shutdown deadline")

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:
                logger.exception("production_dispatch_failed")
            self._wake.wait(0.5)
            self._wake.clear()

    def _project(self, db, project_id: str, principal, action: str = "read") -> dict:
        project = self.store.get(db, "project", project_id)
        if project is None:
            raise ProductionError("Project not found", 404)
        if principal is None:
            raise ProductionError("Authentication required", 401)
        if principal.is_admin or principal.principal_id == project["owner_id"]:
            return project
        role = next((m["role"] for m in project["members"]
                     if m["principal_id"] == principal.principal_id), None)
        if role is None:
            raise ProductionError("Project not found", 404)
        if action == "manage" or (action == "write" and role != "editor") or (
            action == "review" and role not in {"editor", "reviewer"}
        ):
            raise ProductionError("Project permission denied", 403)
        return project

    def _record(self, db, kind: str, record_id: str, project_id: str) -> dict:
        record = self.store.get(db, kind, record_id)
        if record is None or record["project_id"] != project_id:
            raise ProductionError(f"{kind.title()} not found", 404)
        return record

    def _save(self, db, kind: str, record_id: str, record: dict) -> dict:
        record["revision"] += 1
        record["updated_at"] = _now()
        self.store.put(db, kind, record_id, record)
        return record

    def create_project(self, data: dict, principal) -> dict:
        if principal is None:
            raise ProductionError("Authentication required", 401)
        project_id, now = _id(), _now()
        project = {"project_id": project_id, "name": data["name"],
                   "description": data.get("description", ""), "owner_id": principal.principal_id,
                   "members": [], "revision": 1, "created_at": now, "updated_at": now}
        with self.store.transaction() as db:
            self.store.put(db, "project", project_id, project)
            self.store.put(db, "dictionary", project_id,
                           {"project_id": project_id, "revision": 1, "entries": [],
                            "created_at": now, "updated_at": now})
        return project

    def list_projects(self, principal, *, limit=100, offset=0) -> dict:
        with self.store.transaction() as db:
            visible = []
            for item in self.store.list(db, "project"):
                try:
                    visible.append(self._project(db, item["project_id"], principal))
                except ProductionError as exc:
                    if exc.status_code != 404:
                        raise
            return _page(sorted(visible, key=lambda x: x["created_at"], reverse=True), limit, offset)

    def get_project(self, project_id, principal) -> dict:
        with self.store.transaction() as db:
            return self._project(db, project_id, principal)

    def assert_project_access(self, project_id, principal, action="read") -> dict:
        """Shared ACL boundary for legacy jobs carrying production provenance."""
        with self.store.transaction() as db:
            return self._project(db, project_id, principal, action)

    def update_project(self, project_id, data, principal) -> dict:
        with self.store.transaction() as db:
            project = self._project(db, project_id, principal, "write")
            _check_revision(project, data["expected_revision"])
            project.update({key: value for key, value in data.items()
                            if key in {"name", "description"} and value is not None})
            return self._save(db, "project", project_id, project)

    def update_members(self, project_id, data, principal) -> dict:
        with self.store.transaction() as db:
            project = self._project(db, project_id, principal, "manage")
            _check_revision(project, data["expected_revision"])
            ids = [member["principal_id"] for member in data["members"]]
            if len(ids) != len(set(ids)) or project["owner_id"] in ids:
                raise ProductionError("Members must be unique and exclude the project owner")
            project["members"] = data["members"]
            return self._save(db, "project", project_id, project)

    def _new_segment(self, db, project_id, data, *, check_duplicate=True) -> dict:
        external_id = data.get("external_id") or _id()
        if check_duplicate and any(s["external_id"] == external_id
                                   for s in self.store.list(db, "segment", project_id)):
            raise ProductionError(f"Segment external_id already exists: {external_id}", 409)
        segment_id, now = _id(), _now()
        segment = {"segment_id": segment_id, "project_id": project_id,
                   "external_id": external_id, "text": data["text"],
                   "language": normalize_language(data.get("language")),
                   "voice_id": data.get("voice_id"), "model_id": data.get("model_id"),
                   "position": data.get("position", 0), "revision": 1, "script_revision": 1,
                   "selected_take_id": None, "created_at": now, "updated_at": now}
        self.store.put(db, "segment", segment_id, segment)
        self.store.put(db, "script", f"{segment_id}:1", segment)
        return segment

    def create_segment(self, project_id, data, principal) -> dict:
        with self.store.transaction() as db:
            self._project(db, project_id, principal, "write")
            return self._new_segment(db, project_id, data)

    def get_segment(self, project_id, segment_id, principal) -> dict:
        with self.store.transaction() as db:
            self._project(db, project_id, principal)
            return self._record(db, "segment", segment_id, project_id)

    def list_segments(self, project_id, principal, *, limit=100, offset=0) -> dict:
        with self.store.transaction() as db:
            self._project(db, project_id, principal)
            items = sorted(self.store.list(db, "segment", project_id),
                           key=lambda s: (s["position"], s["created_at"]))
            return _page(items, limit, offset)

    def update_segment(self, project_id, segment_id, data, principal) -> dict:
        with self.store.transaction() as db:
            self._project(db, project_id, principal, "write")
            segment = self._record(db, "segment", segment_id, project_id)
            _check_revision(segment, data["expected_revision"])
            changes = {key: value for key, value in data.items() if key != "expected_revision"}
            if changes.get("language") is not None:
                changes["language"] = normalize_language(changes["language"])
            changes = {key: value for key, value in changes.items()
                       if value is not None or key in {"voice_id", "model_id"}}
            segment.update(changes)
            segment["script_revision"] = segment["revision"] + 1
            # A selection from an older script must be explicitly selected again.
            segment["selected_take_id"] = None
            self._save(db, "segment", segment_id, segment)
            self.store.put(db, "script", f"{segment_id}:{segment['script_revision']}", segment)
            return segment

    def segment_revisions(self, project_id, segment_id, principal) -> dict:
        with self.store.transaction() as db:
            self._project(db, project_id, principal)
            self._record(db, "segment", segment_id, project_id)
            return {"items": sorted((s for s in self.store.list(db, "script", project_id)
                                     if s["segment_id"] == segment_id),
                                    key=lambda s: s["script_revision"], reverse=True)}

    def dictionary(self, project_id, principal) -> dict:
        with self.store.transaction() as db:
            self._project(db, project_id, principal)
            return self.store.get(db, "dictionary", project_id)

    def update_dictionary(self, project_id, data, principal) -> dict:
        with self.store.transaction() as db:
            self._project(db, project_id, principal, "write")
            record = self.store.get(db, "dictionary", project_id)
            _check_revision(record, data["expected_revision"])
            keys = [(e["source"], e.get("language")) for e in data["entries"]]
            if len(keys) != len(set(keys)):
                raise ProductionError("Dictionary source/language pairs must be unique")
            self.store.put(db, "dictionary_revision", f"{project_id}:{record['revision']}", record)
            record["entries"] = data["entries"]
            return self._save(db, "dictionary", project_id, record)

    def dictionary_revisions(self, project_id, principal) -> dict:
        with self.store.transaction() as db:
            self._project(db, project_id, principal)
            versions = self.store.list(db, "dictionary_revision", project_id)
            versions.append(self.store.get(db, "dictionary", project_id))
            return {"items": sorted(versions, key=lambda item: item["revision"], reverse=True)}

    @staticmethod
    def apply_dictionary(text: str, language: str, dictionary: dict) -> str:
        # Literal, case-sensitive, single-pass substitution. Localized entries win.
        mapping = {e["source"]: e["replacement"] for e in dictionary["entries"]
                   if e.get("language") is None}
        mapping.update({e["source"]: e["replacement"] for e in dictionary["entries"]
                        if e.get("language") == language})
        if not mapping:
            return text
        pattern = "|".join(re.escape(source) for source in sorted(mapping, key=len, reverse=True))
        return re.sub(r"(?<!\w)(?:" + pattern + r")(?!\w)",
                      lambda match: mapping[match.group()], text)

    def preview_dictionary(self, project_id, data, principal) -> dict:
        dictionary = self.dictionary(project_id, principal)
        language = normalize_language(data["language"])
        return {"text": data["text"], "normalized_text": self.apply_dictionary(
            data["text"], language, dictionary), "dictionary_revision": dictionary["revision"]}

    def _replay(self, db, scope, key, fingerprint, kind):
        key_hash = idempotency_key_hash(key)
        if not key_hash:
            return None
        row = db.execute("SELECT * FROM idempotency WHERE scope=? AND key_hash=?",
                         (scope, key_hash)).fetchone()
        if row is None:
            return None
        if row["fingerprint"] != fingerprint:
            raise ProductionError("Idempotency-Key conflicts with an earlier request", 409)
        return self.store.get(db, kind, row["record_id"])

    @staticmethod
    def _remember(db, scope, key, fingerprint, record_id):
        key_hash = idempotency_key_hash(key)
        if key_hash:
            db.execute("INSERT INTO idempotency VALUES(?,?,?,?)",
                       (scope, key_hash, fingerprint, record_id))

    def _new_take(self, db, segment, data, principal, *, snapshots=None) -> dict:
        project_id = segment["project_id"]
        voice_id = data.get("voice_id") or segment.get("voice_id")
        if not voice_id:
            raise ProductionError("A saved voice_id is required to render this segment")
        language = segment["language"]
        resolved = self.tts.resolve_parameters(
            language=language, model_id=data.get("model_id") or segment.get("model_id"),
            num_steps=data.get("num_steps"), speed=data.get("speed"),
        )
        dictionary = self.store.get(db, "dictionary", project_id)
        normalized = self.apply_dictionary(segment["text"], language, dictionary)
        if not normalized.strip() or len(normalized) > self.max_text_chars:
            raise ProductionError(f"Rendered text must contain 1–{self.max_text_chars} characters")
        snapshots = snapshots if snapshots is not None else {}
        if voice_id not in snapshots:
            snapshots[voice_id] = self.jobs.snapshot_voice(voice_id)
        snapshot = snapshots[voice_id]
        reference = snapshot["reference_wav"]
        digest = hashlib.sha256(reference).hexdigest()
        if digest != snapshot["reference_audio_sha256"]:
            raise ProductionError("Voice snapshot checksum mismatch", 409)
        reference_path = self._asset_path("references", digest + ".wav")
        if not reference_path.exists():
            atomic_write_bytes(reference_path, reference)
        take_id, now = _id(), _now()
        take = {"take_id": take_id, "project_id": project_id,
                "segment_id": segment["segment_id"], "segment_revision": segment["script_revision"],
                "external_id": segment["external_id"], "text": segment["text"],
                "normalized_text": normalized, "voice_id": voice_id,
                "language": language, "model_id": resolved["model_id"],
                "num_steps": resolved.get("num_steps"), "speed": resolved.get("speed"),
                "provenance": {**resolved, "production": {
                    "project_id": project_id, "segment_id": segment["segment_id"],
                    "script_revision": segment["script_revision"],
                    "dictionary_revision": dictionary["revision"],
                    "dictionary_sha256": request_fingerprint(dictionary["entries"]),
                    "original_text": segment["text"], "normalized_text": normalized}},
                "reference_audio_sha256": digest, "reference_text": snapshot["reference_text"],
                "status": "pending", "job_id": None, "review_status": "pending",
                "review_note": "", "reviewed_by": None, "reviewed_at": None,
                "revision": 1, "attempt": 1, "error": None, "audio_url": None,
                "actor_id": principal.principal_id, "request_id": get_request_id(),
                "created_at": now, "updated_at": now}
        self.store.put(db, "take", take_id, take)
        return take

    def create_take(self, project_id, segment_id, data, principal, *, idempotency_key=None) -> dict:
        with self.store.transaction() as db:
            self._project(db, project_id, principal, "write")
            scope = f"take:{principal.principal_id}:{project_id}:{segment_id}"
            fingerprint = request_fingerprint(data)
            replay = self._replay(db, scope, idempotency_key, fingerprint, "take")
            if replay:
                return self._public_take(replay)
            segment = self._record(db, "segment", segment_id, project_id)
            _check_revision(segment, data["expected_revision"])
            take = self._new_take(db, segment, data, principal)
            self._remember(db, scope, idempotency_key, fingerprint, take["take_id"])
        self._wake.set()
        return self._public_take(take)

    @staticmethod
    def _public_take(take):
        # The frozen reference transcript belongs to the voice record, not this API.
        return {key: value for key, value in take.items() if key != "reference_text"}

    def list_takes(self, project_id, segment_id, principal, *, limit=100, offset=0):
        with self.store.transaction() as db:
            self._project(db, project_id, principal)
            self._record(db, "segment", segment_id, project_id)
            items = [self._public_take(t) for t in self.store.list(db, "take", project_id)
                     if t["segment_id"] == segment_id]
            return _page(sorted(items, key=lambda t: t["created_at"], reverse=True), limit, offset)

    def review_take(self, project_id, take_id, data, principal):
        with self.store.transaction() as db:
            self._project(db, project_id, principal, "review")
            take = self._record(db, "take", take_id, project_id)
            _check_revision(take, data["expected_revision"])
            if take["status"] != "succeeded" or not self._take_audio(take).is_file():
                raise ProductionError("Only a completed take with retained audio can be reviewed", 409)
            take.update(review_status=data["status"], review_note=data.get("note", ""),
                        reviewed_by=principal.principal_id, reviewed_at=_now())
            self.store.put(db, "review", _id(), {"project_id": project_id, "take_id": take_id,
                           "status": data["status"], "note": data.get("note", ""),
                           "actor_id": principal.principal_id, "created_at": _now()})
            return self._public_take(self._save(db, "take", take_id, take))

    def select_take(self, project_id, segment_id, data, principal):
        with self.store.transaction() as db:
            self._project(db, project_id, principal, "review")
            segment = self._record(db, "segment", segment_id, project_id)
            _check_revision(segment, data["expected_revision"])
            take = self._record(db, "take", data["take_id"], project_id)
            if take["segment_id"] != segment_id or take["status"] != "succeeded":
                raise ProductionError("Select a completed take belonging to this segment", 409)
            if take["segment_revision"] != segment["script_revision"]:
                raise ProductionError("This take belongs to an older script revision", 409)
            segment["selected_take_id"] = take["take_id"]
            return self._save(db, "segment", segment_id, segment)

    def _asset_path(self, kind: str, filename: str) -> Path:
        return contained_path(self.directory, self.directory / kind / filename)

    def _take_audio(self, take: dict) -> Path:
        return self._asset_path("audio", take["take_id"] + ".wav")

    def take_audio(self, project_id, take_id, principal) -> Path:
        with self.store.transaction() as db:
            self._project(db, project_id, principal)
            take = self._record(db, "take", take_id, project_id)
            path = self._take_audio(take)
            if take["status"] != "succeeded" or not path.is_file():
                raise ProductionError("Take audio is not ready", 409)
            return path

    def _parse_rows(self, payload: dict) -> list[dict]:
        if payload.get("rows") is not None:
            return payload["rows"]
        try:
            reader = csv.DictReader(StringIO(payload["csv_text"].lstrip("\ufeff")), strict=True)
            columns = reader.fieldnames or []
            if len(columns) != len(set(columns)) or not {"external_id", "text"} <= set(columns):
                raise ProductionError("CSV requires unique headers including external_id and text")
            rows = []
            for row in reader:
                if len(rows) >= 10_000:
                    raise ProductionError("A batch can contain at most 10000 rows")
                if None in row:
                    raise ProductionError("CSV row has more values than headers")
                rows.append(row)
            return rows
        except csv.Error as exc:
            raise ProductionError("Invalid CSV input") from exc

    def _analyze(self, db, payload: dict) -> dict:
        dictionary = self.store.get(db, "dictionary", payload["project_id"])
        rows = self._parse_rows(payload)
        defaults, seen, reports = payload.get("defaults", {}), set(), []
        existing = {s["external_id"] for s in self.store.list(db, "segment", payload["project_id"])}
        voice_cache = {}
        catalog = {m["model_id"]: m for m in self.tts.model_catalog()["models"]}
        for number, raw in enumerate(rows, 1):
            errors, warnings = [], []
            values = {**defaults, **{k: v for k, v in raw.items() if v not in (None, "")}}
            external_id = str(values.get("external_id", "")).strip()
            text = values.get("text", "")
            if not isinstance(text, str):
                text = ""
                errors.append("text must be a string")
            text = text.strip()
            if set(raw) - ROW_FIELDS:
                errors.append("Unknown columns: " + ", ".join(sorted(set(raw) - ROW_FIELDS)))
            if not external_id or len(external_id) > 200:
                errors.append("external_id requires 1–200 characters")
            if external_id in seen:
                errors.append("Duplicate external_id in this batch")
            if external_id in existing:
                errors.append("external_id already exists in this project")
            seen.add(external_id)
            normalized, language, resolved = text, values.get("language", "vi"), {}
            voice_id = values.get("voice_id")
            try:
                language = normalize_language(language)
                normalized = self.apply_dictionary(text, language, dictionary)
                if not normalized or len(normalized) > self.max_text_chars:
                    errors.append(f"Text requires 1–{self.max_text_chars} characters after dictionary")
                num_steps = None
                if values.get("num_steps") is not None:
                    numeric_steps = float(values["num_steps"])
                    if isinstance(values["num_steps"], bool) or not math.isfinite(numeric_steps) or not numeric_steps.is_integer():
                        raise ValueError("num_steps must be an integer")
                    num_steps = int(numeric_steps)
                speed = float(values["speed"]) if values.get("speed") is not None else None
                resolved = self.tts.resolve_parameters(
                    language=language, model_id=values.get("model_id"),
                    num_steps=num_steps, speed=speed,
                )
                model = catalog.get(resolved["model_id"])
                if model is None or not model["ready"]:
                    errors.append("Selected model is not available; check model setup")
                if not voice_id:
                    errors.append("voice_id is required")
                else:
                    if voice_id not in voice_cache:
                        voice_cache[voice_id] = self.voices.get(voice_id)
                    if voice_cache[voice_id].language != language:
                        warnings.append("Reference voice language differs from generation language")
            except (VVoiceError, TypeError, ValueError) as exc:
                errors.append(public_error_message(exc) if isinstance(exc, VVoiceError)
                              else "Invalid language or generation options")
            if normalized != text:
                warnings.append("Pronunciation dictionary changes the spoken text")
            reports.append({"row_number": number, "external_id": external_id,
                            "text": text, "normalized_text": normalized, "language": language,
                            "voice_id": voice_id, "model_id": resolved.get("model_id"),
                            "deployment_version": resolved.get("deployment_version"),
                            "num_steps": resolved.get("num_steps"), "speed": resolved.get("speed"),
                            "errors": errors, "warnings": warnings})
        errors = [] if rows else ["The batch has no rows"]
        token = request_fingerprint({"project_id": payload["project_id"], "rows": reports,
                                     "dictionary_revision": dictionary["revision"]})
        return {"can_submit": bool(rows) and not any(r["errors"] for r in reports),
                "row_count": len(reports), "rows": reports, "errors": errors,
                "dictionary_revision": dictionary["revision"], "preflight_token": token}

    def analyze_batch(self, payload, principal):
        with self.store.transaction() as db:
            self._project(db, payload["project_id"], principal, "write")
            return self._analyze(db, payload)

    def create_batch(self, payload, principal, *, idempotency_key=None):
        project_id = payload["project_id"]
        with self.store.transaction() as db:
            self._project(db, project_id, principal, "write")
            scope = f"batch:{principal.principal_id}:{project_id}"
            fingerprint = request_fingerprint(payload)
            replay = self._replay(db, scope, idempotency_key, fingerprint, "batch")
            if replay:
                return self._batch_view(db, replay)
            analysis = self._analyze(db, payload)
            if payload.get("preflight_token") and payload["preflight_token"] != analysis["preflight_token"]:
                raise ProductionError("Preflight changed; analyze the batch again before submitting", 409)
            if not analysis["can_submit"]:
                raise ProductionError("Batch preflight failed; analyze and correct invalid rows", 422)
            batch_id, now, snapshots = _id(), _now(), {}
            batch = {"batch_id": batch_id, "project_id": project_id, "name": payload.get("name", "Batch"),
                     "item_count": len(analysis["rows"]), "cancel_requested": False,
                     "created_at": now, "updated_at": now, "actor_id": principal.principal_id,
                     "request_id": get_request_id(),
                     "revision": 1}
            for row in analysis["rows"]:
                segment = self._new_segment(db, project_id, {**row, "position": row["row_number"]},
                                            check_duplicate=False)
                take = self._new_take(db, segment, row, principal, snapshots=snapshots)
                item_id = _id()
                self.store.put(db, "item", item_id, {
                    "item_id": item_id, "project_id": project_id, "batch_id": batch_id,
                    "row_number": row["row_number"], "external_id": row["external_id"],
                    "segment_id": segment["segment_id"], "take_id": take["take_id"],
                    "take_ids": [take["take_id"]], "created_at": now})
            self.store.put(db, "batch", batch_id, batch)
            self._remember(db, scope, idempotency_key, fingerprint, batch_id)
            response = self._batch_view(db, batch)
        self._wake.set()
        return response

    def _batch_items(self, db, batch_id):
        batch = self.store.get(db, "batch", batch_id)
        return sorted((item for item in self.store.list(db, "item", batch["project_id"])
                       if item["batch_id"] == batch_id), key=lambda item: item["row_number"])

    def _batch_view(self, db, batch):
        counts = dict.fromkeys(("pending", "queued", "running", "succeeded", "failed", "cancelled"), 0)
        for item in self._batch_items(db, batch["batch_id"]):
            status = self.store.get(db, "take", item["take_id"])["status"]
            counts["running" if status == "cancelling" else status] += 1
        if counts["pending"] or counts["queued"] or counts["running"]:
            status = "cancelling" if batch["cancel_requested"] else "running"
        elif counts["failed"]:
            status = "completed_with_errors"
        elif counts["cancelled"]:
            status = "cancelled"
        else:
            status = "succeeded"
        return {**batch, "counts": counts, "status": status}

    def get_batch(self, batch_id, principal):
        with self.store.transaction() as db:
            batch = self.store.get(db, "batch", batch_id)
            if batch is None:
                raise ProductionError("Batch not found", 404)
            self._project(db, batch["project_id"], principal)
            return self._batch_view(db, batch)

    def list_batches(self, principal, *, project_id=None, limit=100, offset=0):
        with self.store.transaction() as db:
            if project_id:
                self._project(db, project_id, principal)
            visible = []
            for batch in self.store.list(db, "batch", project_id):
                try:
                    self._project(db, batch["project_id"], principal)
                    visible.append(self._batch_view(db, batch))
                except ProductionError as exc:
                    if exc.status_code != 404:
                        raise
            return _page(sorted(visible, key=lambda b: b["created_at"], reverse=True), limit, offset)

    def batch_items(self, batch_id, principal, *, limit=100, offset=0):
        batch = self.get_batch(batch_id, principal)
        with self.store.transaction() as db:
            self._project(db, batch["project_id"], principal)
            items = []
            for item in self._batch_items(db, batch_id):
                take = self._public_take(self.store.get(db, "take", item["take_id"]))
                items.append({**take, **item})
            return _page(items, limit, offset)

    def cancel_batch(self, batch_id, principal):
        with self.store.transaction() as db:
            batch = self.store.get(db, "batch", batch_id)
            if batch is None:
                raise ProductionError("Batch not found", 404)
            self._project(db, batch["project_id"], principal, "write")
            batch["cancel_requested"] = True
            self._save(db, "batch", batch_id, batch)
            for item in self._batch_items(db, batch_id):
                take = self.store.get(db, "take", item["take_id"])
                if take["status"] == "pending":
                    take["status"] = "cancelled"
                    self._save(db, "take", take["take_id"], take)
                elif take["status"] not in TERMINAL and take["job_id"]:
                    self.jobs.cancel(take["job_id"])
                    take["status"] = "cancelling"
                    self._save(db, "take", take["take_id"], take)
            return self._batch_view(db, batch)

    def retry_failed(self, batch_id, principal, *, item_ids=None):
        with self.store.transaction() as db:
            batch = self.store.get(db, "batch", batch_id)
            if batch is None:
                raise ProductionError("Batch not found", 404)
            self._project(db, batch["project_id"], principal, "write")
            items = self._batch_items(db, batch_id)
            if item_ids is not None and set(item_ids) - {item["item_id"] for item in items}:
                raise ProductionError("Retry item_ids must belong to this batch")
            for item in items:
                old = self.store.get(db, "take", item["take_id"])
                if old["status"] != "failed" or (item_ids is not None and item["item_id"] not in item_ids):
                    continue
                new_id, now = _id(), _now()
                take = {**old, "take_id": new_id, "status": "pending", "job_id": None,
                        "error": None, "revision": 1, "audio_url": None,
                        "review_status": "pending", "review_note": "", "reviewed_at": None,
                        "reviewed_by": None, "attempt": old["attempt"] + 1,
                        "created_at": now, "updated_at": now, "actor_id": principal.principal_id}
                take.update(request_id=get_request_id() or old.get("request_id"),
                            source_request_id=old.get("request_id"), retry_of_take_id=old["take_id"])
                self.store.put(db, "take", new_id, take)
                item["take_id"] = new_id
                item["take_ids"].append(new_id)
                self.store.put(db, "item", item["item_id"], item)
            batch["cancel_requested"] = False
            self._save(db, "batch", batch_id, batch)
            response = self._batch_view(db, batch)
        self._wake.set()
        return response

    def tick(self, *, dispatch_limit=4) -> None:
        """One bounded dispatch/reconcile pass, serialized across processes by SQLite.

        Stable per-take idempotency keys close the crash window between queue
        acceptance and saving job_id. Queue saturation leaves durable pending rows.
        """
        with self.store.transaction() as db:
            takes = self.store.active_takes(db)
            dispatched = 0
            for take in takes:
                if self._stop.is_set():
                    break
                old_status = take["status"]
                if old_status in TERMINAL:
                    continue
                try:
                    if old_status == "pending":
                        if dispatched >= dispatch_limit:
                            continue
                        reference = self._asset_path(
                            "references", take["reference_audio_sha256"] + ".wav",
                        ).read_bytes()
                        if hashlib.sha256(reference).hexdigest() != take["reference_audio_sha256"]:
                            raise ProductionError("Frozen voice reference checksum mismatch", 409)
                        job = self.jobs.create_from_snapshot(
                            voice_id=take["voice_id"], text=take["normalized_text"],
                            reference_bytes=reference, reference_text=take["reference_text"],
                            language=take["language"], model_id=take["model_id"],
                            num_steps=take["num_steps"], speed=take["speed"],
                            idempotency_key="production:" + take["take_id"],
                            provenance=take["provenance"], actor_id=take["actor_id"],
                            request_id=take.get("request_id"),
                        )
                        dispatched += 1
                        take["job_id"] = job.job_id
                    else:
                        job = self.jobs.get(take["job_id"])
                    take["status"] = job.status
                    if job.status == "succeeded":
                        output = job.output_path.read_bytes()
                        digest = hashlib.sha256(output).hexdigest()
                        atomic_write_bytes(self._take_audio(take), output)
                        take.update(sample_rate=job.sample_rate, duration_seconds=job.duration_seconds,
                                    output_sha256=digest, audio_size_bytes=len(output),
                                    audio_url=f"/api/v1/projects/{take['project_id']}/takes/{take['take_id']}/audio")
                        take["provenance"] = {**take["provenance"],
                                              **getattr(job, "provenance", {}), "output_sha256": digest}
                    elif job.status in {"failed", "cancelled"}:
                        take["error"] = ("Generation cancelled" if job.status == "cancelled"
                                         else "Generation failed; inspect the TTS job and retry the failed item")
                except JobQueueFullError:
                    # Reconcile existing jobs even when this pass cannot submit more.
                    dispatched = dispatch_limit
                    continue
                except Exception as exc:
                    logger.warning("production_take_failed", extra={"take_id": take["take_id"]}, exc_info=True)
                    take["status"] = "failed"
                    take["error"] = public_error_message(exc)
                if take["status"] != old_status or take.get("job_id"):
                    self._save(db, "take", take["take_id"], take)

    def export(self, principal, *, project_id=None, batch_id=None, approved_only=True) -> Path:
        with self.store.transaction() as db:
            if batch_id:
                batch = self.store.get(db, "batch", batch_id)
                if batch is None:
                    raise ProductionError("Batch not found", 404)
                project_id = batch["project_id"]
                ids = [item["take_id"] for item in self._batch_items(db, batch_id)]
            else:
                ids = [segment["selected_take_id"] for segment in self.store.list(db, "segment", project_id)
                       if segment["selected_take_id"]]
            self._project(db, project_id, principal)
            candidates = [self.store.get(db, "take", take_id) for take_id in ids]
            takes = [take for take in candidates if take["status"] == "succeeded"
                     and (not approved_only or take["review_status"] == "approved")]
            if not takes:
                raise ProductionError("No eligible audio. Complete and approve takes; select takes for project export.", 409)
            archive_path = self._asset_path("exports", _id() + ".zip")
            manifest = {"schema_version": 1, "project_id": project_id, "batch_id": batch_id,
                        "created_at": _now(), "approved_only": approved_only, "items": [],
                        "excluded_take_ids": [take["take_id"] for take in candidates if take not in takes]}
            try:
                with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                    for number, take in enumerate(takes, 1):
                        path = self._take_audio(take)
                        if not path.is_file():
                            raise ProductionError("Retained take audio is missing; restore the production backup", 409)
                        audio = path.read_bytes()
                        if hashlib.sha256(audio).hexdigest() != take["output_sha256"]:
                            raise ProductionError("Retained take audio checksum mismatch", 409)
                        slug = re.sub(r"[^A-Za-z0-9_-]+", "_", take["external_id"]).strip("_")[:60] or "segment"
                        filename = f"audio/{number:05d}-{slug}-{take['take_id'][:8]}.wav"
                        archive.writestr(filename, audio)
                        manifest["items"].append({**self._public_take(take), "file": filename})
                    archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
                return archive_path
            except BaseException:
                archive_path.unlink(missing_ok=True)
                raise
