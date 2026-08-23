from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from vvoice.core.errors import (
    AsrJobNotFoundError,
    IdempotencyConflictError,
    VVoiceError,
    public_error_message,
)
from vvoice.domains.asr.service import AsrService
from vvoice.shared.audio.io import duration_seconds, encode_wav, load_audio_bytes
from vvoice.shared.language import DEFAULT_LANGUAGE, normalize_language
from vvoice.shared.jobs.integrity import (
    content_sha256,
    idempotency_key_hash,
    normalize_progress_stage,
    request_fingerprint,
)


TERMINAL_STATUSES = {"succeeded", "failed", "cancelled"}
CANCELLABLE_STATUSES = {"queued", "running", "cancelling"}
logger = logging.getLogger("vvoice.jobs.asr")


class _JobCancelled(Exception):
    pass


@dataclass(frozen=True)
class AsrJob:
    job_id: str
    status: str
    filename: str
    language: str
    created_at: str
    started_at: str | None
    completed_at: str | None
    error: str | None
    attempt: int
    max_attempts: int
    cancel_requested: bool
    failed_reason: str | None
    progress_stage: str
    stage_started_at: str
    idempotency_key_hash: str | None
    request_fingerprint: str | None
    input_path: Path | None
    text: str | None
    sample_rate: int | None
    duration_seconds: float | None


class AsrJobService:
    def __init__(
        self,
        jobs_dir: Path,
        asr: AsrService,
        *,
        target_sample_rate: int,
        max_workers: int = 1,
        max_attempts: int = 1,
        retry_backoff_seconds: float = 0.5,
    ) -> None:
        self._jobs_dir = jobs_dir
        self._asr = asr
        self._target_sample_rate = target_sample_rate
        self._max_attempts = max(1, int(max_attempts))
        self._retry_backoff_seconds = max(0.0, float(retry_backoff_seconds))
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="vvoice-asr-job",
        )
        self._jobs_dir.mkdir(parents=True, exist_ok=True)
        self._mark_interrupted_jobs()

    def create_from_audio(
        self,
        *,
        audio_bytes: bytes,
        filename: str,
        language: str = DEFAULT_LANGUAGE,
        idempotency_key: str | None = None,
    ) -> AsrJob:
        normalized_language = normalize_language(language)
        display_filename = filename or "audio"
        key_hash = idempotency_key_hash(idempotency_key)
        fingerprint = request_fingerprint(
            {
                "audio_sha256": content_sha256(audio_bytes),
                "filename": display_filename,
                "language": normalized_language,
            }
        )
        target_sample_rate = self._sample_rate_for(normalized_language)
        samples, sample_rate = load_audio_bytes(audio_bytes, target_sample_rate=target_sample_rate)

        with self._lock:
            existing = self._find_idempotent_job(key_hash, fingerprint)
            if existing is not None:
                return existing

            job_id = str(uuid.uuid4())
            now = _now()
            job_dir = self._job_dir(job_id)
            job_dir.mkdir(parents=True, exist_ok=False)
            input_path = job_dir / "input.wav"
            input_path.write_bytes(encode_wav(samples, sample_rate))
            job = AsrJob(
                job_id=job_id,
                status="queued",
                filename=display_filename,
                language=normalized_language,
                created_at=now,
                started_at=None,
                completed_at=None,
                error=None,
                attempt=0,
                max_attempts=self._max_attempts,
                cancel_requested=False,
                failed_reason=None,
                progress_stage="queued",
                stage_started_at=now,
                idempotency_key_hash=key_hash,
                request_fingerprint=fingerprint if key_hash else None,
                input_path=input_path,
                text=None,
                sample_rate=sample_rate,
                duration_seconds=duration_seconds(samples, sample_rate),
            )
            self._save(job)
        logger.info(
            "asr_job_created",
            extra={
                "job_id": job_id,
                "language": normalized_language,
                "source_filename": job.filename,
                "duration_seconds": job.duration_seconds,
            },
        )
        self._executor.submit(self._run, job_id)
        return job

    def _find_idempotent_job(
        self,
        key_hash: str | None,
        fingerprint: str,
    ) -> AsrJob | None:
        if key_hash is None:
            return None

        for metadata_path in self._jobs_dir.glob("*/metadata.json"):
            job = self._load(metadata_path)
            if job.idempotency_key_hash != key_hash:
                continue
            if job.request_fingerprint != fingerprint:
                raise IdempotencyConflictError(
                    "Idempotency-Key was already used for a different ASR request"
                )
            logger.info(
                "asr_job_idempotent_replay",
                extra={"job_id": job.job_id, "language": job.language},
            )
            return job
        return None

    def list(self) -> list[AsrJob]:
        if not self._jobs_dir.exists():
            return []

        jobs = [
            self._load(metadata_path)
            for metadata_path in self._jobs_dir.glob("*/metadata.json")
        ]
        return sorted(jobs, key=lambda item: item.created_at, reverse=True)

    def get(self, job_id: str) -> AsrJob:
        metadata_path = self._metadata_path(job_id)
        if not metadata_path.exists():
            raise AsrJobNotFoundError(f"ASR job not found: {job_id}")
        return self._load(metadata_path)

    def delete(self, job_id: str) -> None:
        job = self.get(job_id)
        if job.status not in TERMINAL_STATUSES:
            raise VVoiceError(f"Cannot delete ASR job while it is {job.status}")

        job_dir = self._job_dir(job_id)
        for path in job_dir.glob("*"):
            if path.is_file():
                path.unlink()
        job_dir.rmdir()

    def cancel(self, job_id: str) -> AsrJob:
        with self._lock:
            job = self.get(job_id)
            if job.status in TERMINAL_STATUSES:
                raise VVoiceError(f"Cannot cancel ASR job while it is {job.status}")
            if job.status not in CANCELLABLE_STATUSES:
                raise VVoiceError(f"Cannot cancel ASR job while it is {job.status}")

            if job.status == "queued":
                cancelled = _replace_job(
                    job,
                    status="cancelled",
                    completed_at=_now(),
                    error="Job was cancelled before it started",
                    cancel_requested=True,
                    failed_reason="cancelled",
                    progress_stage="cancelled",
                    stage_started_at=_now(),
                )
                self._save(cancelled)
                logger.info(
                    "asr_job_cancelled",
                    extra={"job_id": job_id, "language": job.language, "status": "queued"},
                )
                return cancelled

            cancelling = _replace_job(
                job,
                status="cancelling",
                error="Cancellation requested",
                cancel_requested=True,
                failed_reason=None,
            )
            self._save(cancelling)
            logger.info(
                "asr_job_cancel_requested",
                extra={"job_id": job_id, "language": job.language, "status": job.status},
            )
            return cancelling

    def cleanup(self, *, max_age_seconds: int | None = None) -> list[str]:
        cutoff = _cutoff(max_age_seconds)
        deleted: list[str] = []
        for job in self.list():
            if job.status not in TERMINAL_STATUSES:
                continue
            if cutoff and _job_age_anchor(job) > cutoff:
                continue
            self.delete(job.job_id)
            deleted.append(job.job_id)
        return deleted

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _run(self, job_id: str) -> None:
        while True:
            try:
                job = self._start_attempt(job_id)
                if job is None:
                    return

                logger.info(
                    "asr_job_started",
                    extra={
                        "job_id": job_id,
                        "language": job.language,
                        "attempt": job.attempt,
                        "max_attempts": job.max_attempts,
                    },
                )

                if not job.input_path or not job.input_path.exists():
                    raise VVoiceError("ASR job input audio is missing")

                self._raise_if_cancel_requested(job_id)
                samples, sample_rate = load_audio_bytes(
                    job.input_path.read_bytes(),
                    target_sample_rate=self._sample_rate_for(job.language),
                )
                self._raise_if_cancel_requested(job_id)
                job = self._set_progress_stage(job_id, "running_model")
                result = self._asr.transcribe(samples, sample_rate, job.language)
                self._raise_if_cancel_requested(job_id)
                job = self._set_progress_stage(job_id, "finalizing")

                self._complete_successfully(
                    job_id,
                    text=result.text,
                    sample_rate=result.sample_rate,
                    audio_duration_seconds=duration_seconds(samples, sample_rate),
                )
                logger.info(
                    "asr_job_succeeded",
                    extra={
                        "job_id": job_id,
                        "language": job.language,
                        "attempt": job.attempt,
                        "duration_seconds": duration_seconds(samples, sample_rate),
                    },
                )
                return
            except _JobCancelled as exc:
                self._mark_cancelled(job_id, str(exc))
                return
            except Exception as exc:  # pragma: no cover - exercised through smoke tests
                if self._queue_retry(job_id, exc):
                    time.sleep(self._retry_backoff_seconds)
                    continue

                self._mark_failed(job_id, exc)
                return

    def _mark_interrupted_jobs(self) -> None:
        for job in self.list():
            if job.status in TERMINAL_STATUSES:
                continue
            self._save(
                _replace_job(
                    job,
                    status="failed",
                    completed_at=_now(),
                    error="Job was interrupted by server restart",
                    failed_reason="interrupted",
                    progress_stage="failed",
                    stage_started_at=_now(),
                )
            )

    def _save(self, job: AsrJob) -> None:
        with self._lock:
            self._job_dir(job.job_id).mkdir(parents=True, exist_ok=True)
            metadata_path = self._metadata_path(job.job_id)
            tmp_path = metadata_path.with_suffix(".json.tmp")
            tmp_path.write_text(
                json.dumps(_job_to_metadata(job), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp_path.replace(metadata_path)

    def _load(self, metadata_path: Path) -> AsrJob:
        with self._lock:
            raw = json.loads(metadata_path.read_text(encoding="utf-8"))
        input_path = raw.get("input_path")
        status = raw["status"]
        failed_reason = raw.get("failed_reason")
        max_attempts = int(raw.get("max_attempts") or self._max_attempts)
        return AsrJob(
            job_id=raw["job_id"],
            status=status,
            filename=raw["filename"],
            language=normalize_language(raw.get("language", DEFAULT_LANGUAGE)),
            created_at=raw["created_at"],
            started_at=raw.get("started_at"),
            completed_at=raw.get("completed_at"),
            error=raw.get("error"),
            attempt=int(raw.get("attempt") or 0),
            max_attempts=max(1, max_attempts),
            cancel_requested=bool(raw.get("cancel_requested", False)),
            failed_reason=failed_reason,
            progress_stage=normalize_progress_stage(
                raw.get("progress_stage"),
                status,
                failed_reason,
            ),
            stage_started_at=(
                raw.get("stage_started_at")
                or raw.get("completed_at")
                or raw.get("started_at")
                or raw["created_at"]
            ),
            idempotency_key_hash=raw.get("idempotency_key_hash"),
            request_fingerprint=raw.get("request_fingerprint"),
            input_path=Path(input_path) if input_path else None,
            text=raw.get("text"),
            sample_rate=raw.get("sample_rate"),
            duration_seconds=raw.get("duration_seconds"),
        )

    def _start_attempt(self, job_id: str) -> AsrJob | None:
        with self._lock:
            job = self.get(job_id)
            if job.status in TERMINAL_STATUSES:
                return None
            if job.cancel_requested or job.status == "cancelling":
                self._save(
                    _replace_job(
                        job,
                        status="cancelled",
                        completed_at=_now(),
                        error="Job was cancelled before the next attempt",
                        cancel_requested=True,
                        failed_reason="cancelled",
                        progress_stage="cancelled",
                        stage_started_at=_now(),
                    )
                )
                return None

            attempt = job.attempt + 1
            running = _replace_job(
                job,
                status="running",
                started_at=job.started_at or _now(),
                completed_at=None,
                error=None,
                failed_reason=None,
                attempt=attempt,
                max_attempts=job.max_attempts,
                progress_stage="preparing_input",
                stage_started_at=_now(),
            )
            self._save(running)
            return running

    def _raise_if_cancel_requested(self, job_id: str) -> None:
        job = self.get(job_id)
        if job.cancel_requested or job.status == "cancelling":
            raise _JobCancelled("Job was cancelled")

    def _mark_cancelled(self, job_id: str, message: str) -> None:
        with self._lock:
            try:
                job = self.get(job_id)
            except AsrJobNotFoundError:
                return
            if job.status in TERMINAL_STATUSES:
                return

            cancelled = _replace_job(
                job,
                status="cancelled",
                completed_at=_now(),
                error=message,
                cancel_requested=True,
                failed_reason="cancelled",
                progress_stage="cancelled",
                stage_started_at=_now(),
            )
            self._save(cancelled)
        logger.info(
            "asr_job_cancelled",
            extra={"job_id": job_id, "language": job.language, "attempt": job.attempt},
        )

    def _queue_retry(self, job_id: str, exc: Exception) -> bool:
        with self._lock:
            try:
                job = self.get(job_id)
            except AsrJobNotFoundError:
                return False
            if job.status in TERMINAL_STATUSES:
                return False
            if job.cancel_requested or job.status == "cancelling":
                self._mark_cancelled(job_id, "Job was cancelled")
                return True
            if not _is_retryable_exception(exc) or job.attempt >= job.max_attempts:
                return False

            retrying = _replace_job(
                job,
                status="queued",
                completed_at=None,
                error=public_error_message(exc),
                failed_reason="retry_pending",
                progress_stage="retry_wait",
                stage_started_at=_now(),
            )
            self._save(retrying)
        logger.warning(
            "asr_job_retrying",
            extra={
                "job_id": job_id,
                "language": job.language,
                "attempt": job.attempt,
                "max_attempts": job.max_attempts,
            },
        )
        return True

    def _mark_failed(self, job_id: str, exc: Exception) -> None:
        with self._lock:
            try:
                job = self.get(job_id)
            except AsrJobNotFoundError:
                return
            if job.status in TERMINAL_STATUSES:
                return
            if job.cancel_requested or job.status == "cancelling":
                self._mark_cancelled(job_id, "Job was cancelled")
                return

            self._save(
                _replace_job(
                    job,
                    status="failed",
                    completed_at=_now(),
                    error=public_error_message(exc),
                    failed_reason=_failed_reason_for(exc),
                    progress_stage="failed",
                    stage_started_at=_now(),
                )
            )
        logger.exception(
            "asr_job_failed",
            extra={
                "job_id": job_id,
                "language": job.language,
                "attempt": job.attempt,
                "max_attempts": job.max_attempts,
            },
        )

    def _set_progress_stage(self, job_id: str, stage: str) -> AsrJob:
        with self._lock:
            job = self.get(job_id)
            if job.cancel_requested or job.status == "cancelling":
                raise _JobCancelled("Job was cancelled")
            updated = _replace_job(job, progress_stage=stage, stage_started_at=_now())
            self._save(updated)
            return updated

    def _complete_successfully(
        self,
        job_id: str,
        *,
        text: str,
        sample_rate: int,
        audio_duration_seconds: float,
    ) -> AsrJob:
        with self._lock:
            job = self.get(job_id)
            if job.cancel_requested or job.status == "cancelling":
                raise _JobCancelled("Job was cancelled")
            completed = _replace_job(
                job,
                status="succeeded",
                completed_at=_now(),
                error=None,
                failed_reason=None,
                progress_stage="succeeded",
                stage_started_at=_now(),
                text=text,
                sample_rate=sample_rate,
                duration_seconds=audio_duration_seconds,
            )
            self._save(completed)
            return completed

    def _job_dir(self, job_id: str) -> Path:
        if "/" in job_id or "\\" in job_id or job_id in {"", ".", ".."}:
            raise AsrJobNotFoundError(f"ASR job not found: {job_id}")
        return self._jobs_dir / job_id

    def _metadata_path(self, job_id: str) -> Path:
        return self._job_dir(job_id) / "metadata.json"

    def _sample_rate_for(self, language: str) -> int:
        sample_rate_for = getattr(self._asr, "sample_rate_for", None)
        if callable(sample_rate_for):
            return int(sample_rate_for(language))
        return self._target_sample_rate


def _job_to_metadata(job: AsrJob) -> dict:
    return {
        "job_id": job.job_id,
        "status": job.status,
        "filename": job.filename,
        "language": job.language,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
        "error": job.error,
        "attempt": job.attempt,
        "max_attempts": job.max_attempts,
        "cancel_requested": job.cancel_requested,
        "failed_reason": job.failed_reason,
        "progress_stage": job.progress_stage,
        "stage_started_at": job.stage_started_at,
        "idempotency_key_hash": job.idempotency_key_hash,
        "request_fingerprint": job.request_fingerprint,
        "input_path": str(job.input_path) if job.input_path else None,
        "text": job.text,
        "sample_rate": job.sample_rate,
        "duration_seconds": job.duration_seconds,
    }


def _replace_job(job: AsrJob, **changes) -> AsrJob:
    values = _job_to_metadata(job)
    values.update(changes)
    input_path = values.get("input_path")
    return AsrJob(
        job_id=values["job_id"],
        status=values["status"],
        filename=values["filename"],
        language=normalize_language(values.get("language", DEFAULT_LANGUAGE)),
        created_at=values["created_at"],
        started_at=values.get("started_at"),
        completed_at=values.get("completed_at"),
        error=values.get("error"),
        attempt=int(values.get("attempt") or 0),
        max_attempts=max(1, int(values.get("max_attempts") or 1)),
        cancel_requested=bool(values.get("cancel_requested", False)),
        failed_reason=values.get("failed_reason"),
        progress_stage=values["progress_stage"],
        stage_started_at=values["stage_started_at"],
        idempotency_key_hash=values.get("idempotency_key_hash"),
        request_fingerprint=values.get("request_fingerprint"),
        input_path=Path(input_path) if input_path else None,
        text=values.get("text"),
        sample_rate=values.get("sample_rate"),
        duration_seconds=values.get("duration_seconds"),
    )


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _cutoff(max_age_seconds: int | None) -> datetime | None:
    if max_age_seconds is None or max_age_seconds <= 0:
        return None
    return datetime.now(tz=timezone.utc) - timedelta(seconds=max_age_seconds)


def _job_age_anchor(job: AsrJob) -> datetime:
    value = job.completed_at or job.created_at
    return datetime.fromisoformat(value)


def _is_retryable_exception(exc: Exception) -> bool:
    return not isinstance(exc, VVoiceError)


def _failed_reason_for(exc: Exception) -> str:
    return "application_error" if isinstance(exc, VVoiceError) else "runtime_error"
