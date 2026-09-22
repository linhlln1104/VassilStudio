from __future__ import annotations

import json
import logging
import math
import re
import uuid
from datetime import datetime
from pathlib import Path


_RECORD_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def record_directory(root: Path, record_id: str) -> Path:
    """Resolve an untrusted record ID without following directory links."""
    if not _RECORD_ID.fullmatch(record_id) or record_id.endswith("."):
        raise ValueError("Invalid record ID")
    directory = root / record_id
    contained_path(root, directory)
    if directory.is_symlink() or _is_junction(directory):
        raise ValueError("Record directories must not be links")
    return directory


def contained_path(directory: Path, path: Path) -> Path:
    """Accept legacy absolute paths only when they remain inside this record."""
    resolved_root = directory.resolve()
    resolved = path.resolve()
    if resolved == resolved_root or not resolved.is_relative_to(resolved_root):
        raise ValueError("Stored file is outside its record directory")
    relative = path.absolute().relative_to(directory.absolute())
    current = directory
    for part in relative.parts:
        current = current / part
        if current.is_symlink() or _is_junction(current):
            raise ValueError("Stored files must not be links")
    return path


def artifact_path(directory: Path, value: str) -> Path:
    path = Path(value)
    return contained_path(directory, path if path.is_absolute() else directory / path)


def read_metadata(path: Path) -> dict:
    contained_path(path.parent, path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Record metadata must be an object")
    if raw.get("job_id", raw.get("voice_id")) != path.parent.name:
        raise ValueError("Record ID does not match its directory")
    required_strings = (
        ("job_id", "created_at", "status", "voice_id", "text")
        if "job_id" in raw and "voice_id" in raw
        else ("job_id", "created_at", "status", "filename")
        if "job_id" in raw
        else ("voice_id", "name", "reference_text", "audio_path")
    )
    for field in required_strings:
        if not isinstance(raw.get(field), str):
            raise ValueError(f"Invalid metadata field: {field}")
    for field in (
        "created_at", "completed_at", "started_at", "updated_at", "language",
        "name", "filename", "text", "reference_text", "reference_audio_sha256",
        "input_path", "output_path", "audio_path",
    ):
        value = raw.get(field)
        if value is not None and not isinstance(value, str):
            raise ValueError(f"Invalid metadata field: {field}")
        if value and field.endswith("_at"):
            datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    if "job_id" in raw and not raw["created_at"]:
        raise ValueError("Job creation time is missing")
    for field in (
        "sample_rate", "duration_seconds", "audio_size_bytes", "attempt", "max_attempts",
        "transcript_revision", "num_steps", "speed",
    ):
        value = raw.get(field)
        if value is None:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"Invalid numeric metadata field: {field}") from exc
        if isinstance(value, bool) or not math.isfinite(number) or number < 0:
            raise ValueError(f"Invalid numeric metadata field: {field}")
        if field not in {"duration_seconds", "speed"} and not number.is_integer():
            raise ValueError(f"Invalid numeric metadata field: {field}")
    if "job_id" in raw and raw.get("status") not in {
        "queued", "running", "cancelling", "succeeded", "failed", "cancelled",
    }:
        raise ValueError("Unknown job status")
    return raw


def atomic_write_metadata(path: Path, metadata: dict) -> None:
    contained_path(path.parent, path)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump(metadata, stream, ensure_ascii=False, indent=2)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_write_bytes(path: Path, content: bytes) -> None:
    contained_path(path.parent, path)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(content)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def quarantine_metadata(path: Path, logger: logging.Logger) -> None:
    """Preserve a damaged record for inspection, without taking down its store."""
    try:
        contained_path(path.parent, path)
        destination = path.with_name(f"metadata.corrupt-{uuid.uuid4().hex}.json")
        path.rename(destination)
        logger.warning("record_metadata_quarantined", extra={"metadata_path": str(destination)})
    except (OSError, ValueError):
        logger.warning("record_metadata_unavailable", extra={"metadata_path": str(path)})


def count_quarantined_metadata(root: Path) -> int:
    count = 0
    for path in root.glob("*/metadata.corrupt-*.json"):
        try:
            record_directory(root, path.parent.name)
            contained_path(path.parent, path)
            count += int(path.is_file())
        except (OSError, ValueError):
            continue
    return count


def delete_record_files(directory: Path) -> None:
    """Validate every entry before deleting anything; never follow directory links."""
    files = list(directory.iterdir())
    for path in files:
        contained_path(directory, path)
        if not path.is_file():
            raise ValueError("Record directory contains an unexpected entry")
    for path in files:
        path.unlink()
    directory.rmdir()


def _is_junction(path: Path) -> bool:
    # Reparse-point detection also covers Windows junctions on Python 3.10/3.11.
    try:
        return bool(getattr(path.lstat(), "st_file_attributes", 0) & 0x400)
    except FileNotFoundError:
        return False
