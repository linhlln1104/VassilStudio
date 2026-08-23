from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any

from vvoice.core.errors import VVoiceError


IDEMPOTENCY_KEY_HEADER = "Idempotency-Key"
IDEMPOTENCY_KEY_MAX_LENGTH = 128
CANCELLATION_MODE = "safe_point"
PROGRESS_STAGES = {
    "queued",
    "preparing_input",
    "running_model",
    "finalizing",
    "retry_wait",
    "succeeded",
    "failed",
    "cancelled",
}

_IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def validate_idempotency_key(value: str | None) -> str | None:
    if value is None:
        return None

    key = value.strip()
    if not key:
        raise VVoiceError("Idempotency-Key must not be empty")
    if len(key) > IDEMPOTENCY_KEY_MAX_LENGTH or not _IDEMPOTENCY_KEY_PATTERN.fullmatch(key):
        raise VVoiceError(
            "Idempotency-Key must be 1-128 characters using letters, numbers, '.', '_', ':', or '-'"
        )
    return key


def idempotency_key_hash(value: str | None) -> str | None:
    key = validate_idempotency_key(value)
    if key is None:
        return None
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def request_fingerprint(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def content_sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def progress_stage_for_legacy_job(status: str, failed_reason: str | None) -> str:
    if status == "queued":
        return "retry_wait" if failed_reason == "retry_pending" else "queued"
    if status in {"running", "cancelling"}:
        return "running_model"
    if status in {"succeeded", "failed", "cancelled"}:
        return status
    return "queued"


def normalize_progress_stage(value: object, status: str, failed_reason: str | None) -> str:
    if isinstance(value, str) and value in PROGRESS_STAGES:
        return value
    return progress_stage_for_legacy_job(status, failed_reason)
