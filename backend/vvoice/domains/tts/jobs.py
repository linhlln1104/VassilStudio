from __future__ import annotations

import logging
import os
import time
import uuid
from dataclasses import dataclass, replace, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from contextlib import nullcontext

from vvoice.core.observability import get_request_id, set_request_id, reset_request_id
from vvoice.shared.jobs.durable import DurableExecutor, FileLock
from vvoice.core.errors import (
    InferenceTransientError,
    IdempotencyConflictError,
    JobQueueFullError,
    TtsJobNotFoundError,
    VVoiceError,
    public_error_message,
)
from vvoice.domains.tts.parameters import validate_tts_parameters
from vvoice.shared.audio.io import encode_wav, load_audio_bytes
from vvoice.shared.language import DEFAULT_LANGUAGE, normalize_language
from vvoice.shared.jobs.integrity import (
    content_sha256,
    idempotency_key_hash,
    normalize_progress_stage,
    request_fingerprint,
)
from vvoice.shared.jobs.storage import (
    artifact_path,
    portable_artifact_path,
    atomic_write_bytes,
    atomic_write_metadata,
    count_quarantined_metadata,
    delete_record_files,
    quarantine_metadata,
    read_metadata,
    record_directory,
)
from vvoice.shared.validation import validate_text_field
from vvoice.domains.tts.service import TtsService
from vvoice.domains.voices.service import VoiceStore


TERMINAL_STATUSES = {"succeeded", "failed", "cancelled"}
CANCELLABLE_STATUSES = {"queued", "running", "cancelling"}
logger = logging.getLogger("vvoice.jobs.tts")


class _JobCancelled(Exception):
    pass


@dataclass(frozen=True)
class TtsJob:
    job_id: str
    status: str
    voice_id: str
    language: str
    model_id: str
    text: str
    num_steps: int | None
    speed: float | None
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
    output_path: Path | None
    sample_rate: int | None
    duration_seconds: float | None
    reference_text: str | None = None
    reference_audio_sha256: str | None = None
    request_id: str | None = None
    recovery_count: int = 0
    actor_id: str | None = None
    provenance: dict = field(default_factory=dict)


class TtsJobService:
    def __init__(
        self,
        jobs_dir: Path,
        tts: TtsService,
        voices: VoiceStore,
        *,
        max_workers: int = 1,
        max_pending_jobs: int = 32,
        max_attempts: int = 1,
        retry_backoff_seconds: float = 0.5,
        worker_enabled: bool | None = None,
        max_text_chars: int = 5000,
    ) -> None:
        self._jobs_dir = jobs_dir
        self._tts = tts
        self._voices = voices
        self._max_attempts = max(1, int(max_attempts))
        self._max_pending_jobs = max(1, int(max_pending_jobs))
        self._retry_backoff_seconds = max(0.0, float(retry_backoff_seconds))
        self._max_text_chars = max_text_chars
        self._jobs_dir.mkdir(parents=True, exist_ok=True)
        self._lock = FileLock(self._jobs_dir / ".metadata.lock")
        self._accepting = True
        self._pending_job_ids: set[str] = set()
        self._executor = DurableExecutor(
            jobs_dir, self._run_queued, max_workers=max_workers,
            enabled=(os.getenv("VASSIL_WORKER_MODE", "embedded") != "external"
                     if worker_enabled is None else worker_enabled),
        )
        self._mark_interrupted_jobs()
        self._executor.start()

    @property
    def quarantined_count(self) -> int:
        return count_quarantined_metadata(self._jobs_dir)

    def create_from_voice(
        self,
        *,
        voice_id: str,
        text: str,
        language: str | None = None,
        model_id: str | None = None,
        num_steps: int | None = None,
        speed: float | None = None,
        idempotency_key: str | None = None,
    ) -> TtsJob:
        return self.create_from_snapshot(
            voice_id=voice_id, text=text, language=language, model_id=model_id,
            num_steps=num_steps, speed=speed, idempotency_key=idempotency_key,
        )

    def snapshot_voice(self, voice_id: str) -> dict:
        profile, data = self._voices.snapshot(voice_id)
        return {
            "voice_id": voice_id, "reference_text": profile.reference_text,
            "reference_audio_sha256": content_sha256(data),
            "reference_wav": data, "language": profile.language,
        }

    def retry(self, job_id: str, *, idempotency_key: str | None = None) -> TtsJob:
        with self._lock:
            original = self.get(job_id)
            if original.status not in TERMINAL_STATUSES:
                raise VVoiceError("Wait for this job to finish before retrying its snapshot")
            original, data = self._reference_snapshot(original)
            return self.create_from_snapshot(
                voice_id=original.voice_id, text=original.text, language=original.language,
                model_id=original.model_id, num_steps=original.num_steps, speed=original.speed,
                reference_bytes=data, reference_text=original.reference_text,
                provenance={**original.provenance, "retry_of": original.job_id},
                idempotency_key=idempotency_key,
            )

    def create_from_snapshot(
        self, *, voice_id: str, text: str, language: str | None = None,
        model_id: str | None = None, num_steps: int | None = None,
        speed: float | None = None, idempotency_key: str | None = None,
        reference_bytes: bytes | None = None, reference_text: str | None = None,
        provenance: dict | None = None,
        actor_id: str | None = None, request_id: str | None = None,
    ) -> TtsJob:
        text = validate_text_field(
            text,
            field_name="text",
            max_chars=self._max_text_chars,
        )
        assert text is not None
        validate_tts_parameters(num_steps, speed)
        from vvoice.shared.security.auth import current_actor_id
        actor_id = actor_id or current_actor_id()
        key_hash = idempotency_key_hash(
            f"{actor_id}:{idempotency_key}" if actor_id and idempotency_key else idempotency_key
        )

        with self._lock:
            # Replays remain usable after the original profile has been edited or deleted.
            previous = self._executor.key_record(key_hash)
            replay = None
            if previous:
                try:
                    replay = self.get(previous['job_id'])
                except TtsJobNotFoundError as exc:
                    raise IdempotencyConflictError(
                        "This request was already processed; its job was removed. "
                        "Use a new Idempotency-Key for an intentional new render."
                    ) from exc
            if replay is not None:
                effective_language = normalize_language(language or replay.language)
                # A replay refers to the accepted model even if the configured default changed.
                effective_model_id = replay.model_id if model_id is None else model_id.strip()
                if not effective_model_id:
                    raise VVoiceError("model_id must not be empty")
            else:
                self._check_queue_capacity()
                if reference_bytes is None:
                    profile, reference_bytes = self._voices.snapshot(voice_id)
                else:
                    if not reference_bytes or reference_text is None:
                        raise VVoiceError("A reference snapshot requires audio and transcript")
                    profile = SimpleNamespace(reference_text=reference_text, language=language)
                effective_language = normalize_language(language or profile.language)
                effective_model_id = self._tts.validate_request(
                    language=effective_language,
                    model_id=model_id,
                    num_steps=num_steps,
                    speed=speed,
                )
            fingerprint = _tts_request_fingerprint(
                language=effective_language,
                model_id=effective_model_id,
                num_steps=num_steps,
                speed=speed,
                text=text,
                voice_id=voice_id,
            )
            if provenance and provenance.get('retry_of'):
                # A retry key identifies the frozen source job, not just its text
                # and mutable voice ID. Reusing it for another take must conflict.
                fingerprint = request_fingerprint({
                    'request': fingerprint, 'retry_of': provenance['retry_of'],
                    'reference_audio_sha256': content_sha256(reference_bytes),
                    'reference_text': reference_text,
                    'deployment_version': provenance.get('deployment_version'),
                })
            existing = self._find_idempotent_job(key_hash, fingerprint)
            if existing is not None:
                return existing

            resolved = (self._tts.resolve_parameters(
                language=effective_language, model_id=effective_model_id,
                num_steps=num_steps, speed=speed,
            ) if hasattr(self._tts, 'resolve_parameters') else {})
            if (provenance and provenance.get('deployment_version')
                    and provenance['deployment_version'] != resolved.get('deployment_version')):
                raise VVoiceError("The accepted model version changed; select and review a new take")
            frozen_provenance = {**resolved, **(provenance or {})}
            frozen_provenance.pop('output_sha256', None)

            language = effective_language
            job_id = str(uuid.uuid4())
            now = _now()
            job_dir = self._job_dir(job_id)
            job_dir.mkdir(parents=True, exist_ok=False)
            atomic_write_bytes(job_dir / "reference.wav", reference_bytes)
            job = TtsJob(
                job_id=job_id,
                request_id=request_id or get_request_id(),
                actor_id=actor_id,
                provenance=frozen_provenance,
                status="queued",
                voice_id=voice_id,
                language=language,
                model_id=effective_model_id,
                text=text,
                num_steps=resolved.get('num_steps', num_steps),
                speed=resolved.get('speed', speed),
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
                output_path=job_dir / "output.wav",
                sample_rate=None,
                duration_seconds=None,
                reference_text=profile.reference_text,
                reference_audio_sha256=content_sha256(reference_bytes),
            )
            self._save(job)
            self._pending_job_ids.add(job_id)
            self._executor.submit(self._run_queued, job_id)
        logger.info(
            "tts_job_created",
            extra={
                "job_id": job_id,
                "voice_id": voice_id,
                "language": language,
                "model_id": effective_model_id,
                "num_steps": num_steps,
                "speed": speed,
            },
        )
        return job

    def _find_idempotent_job(
        self,
        key_hash: str | None,
        fingerprint: str,
    ) -> TtsJob | None:
        if key_hash is None:
            return None

        previous = self._executor.key_record(key_hash)
        if previous:
            job = self.get(previous['job_id'])
            if job.request_fingerprint != fingerprint:
                raise IdempotencyConflictError(
                    "Idempotency-Key was already used for a different TTS request"
                )
            logger.info(
                "tts_job_idempotent_replay",
                extra={"job_id": job.job_id, "voice_id": job.voice_id},
            )
            return job
        return None

    def list(self, *, limit=None, offset=0, status=None, model_id=None) -> list[TtsJob]:
        jobs = []
        for job_id in self._executor.record_ids(
                limit=limit, offset=offset, status=status, model_id=model_id):
            try:
                jobs.append(self.get(job_id))
            except TtsJobNotFoundError:
                self._executor.remove_record(job_id)
        return jobs

    def get(self, job_id: str) -> TtsJob:
        metadata_path = self._metadata_path(job_id)
        if not metadata_path.exists():
            raise TtsJobNotFoundError(f"TTS job not found: {job_id}")
        try:
            return self._load(metadata_path)
        except (OSError, ValueError, KeyError, TypeError, AttributeError, VVoiceError) as exc:
            quarantine_metadata(metadata_path, logger)
            raise TtsJobNotFoundError("TTS job metadata is unavailable") from exc

    def _check_queue_capacity(self) -> None:
        if not self._accepting:
            raise VVoiceError("The TTS job service is shutting down")
        pending = self._executor.pending_ids() | self._executor.active_record_ids()
        if len(pending) >= self._max_pending_jobs:
            raise JobQueueFullError("The TTS job queue is full. Wait for a job to finish and retry.")

    def delete(self, job_id: str) -> None:
        with self._lock:
            job = self.get(job_id)
            if job.status not in TERMINAL_STATUSES:
                raise VVoiceError(f"Cannot delete TTS job while it is {job.status}")
            try:
                delete_record_files(self._job_dir(job_id))
                self._executor.remove_record(job_id)
            except ValueError as exc:
                raise VVoiceError("TTS job contains an unexpected file or directory") from exc

    def cancel(self, job_id: str) -> TtsJob:
        with self._lock:
            job = self.get(job_id)
            if job.status in TERMINAL_STATUSES:
                raise VVoiceError(f"Cannot cancel TTS job while it is {job.status}")
            if job.status not in CANCELLABLE_STATUSES:
                raise VVoiceError(f"Cannot cancel TTS job while it is {job.status}")

            if job.status == "queued":
                completed_at = _now()
                cancelled = _replace_job(
                    job,
                    status="cancelled",
                    completed_at=completed_at,
                    error="Job was cancelled before it started",
                    cancel_requested=True,
                    failed_reason="cancelled",
                    progress_stage="cancelled",
                    stage_started_at=completed_at,
                )
                self._save(cancelled)
                logger.info(
                    "tts_job_cancelled",
                    extra={"job_id": job_id, "voice_id": job.voice_id, "status": "queued"},
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
                "tts_job_cancel_requested",
                extra={"job_id": job_id, "voice_id": job.voice_id, "status": job.status},
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
        with self._lock:
            self._accepting = False
            self._executor.shutdown(wait=False, cancel_futures=True)

    def _run_queued(self, job_id: str) -> None:
        token = None
        try:
            with self._lock:
                job = self.get(job_id)
                if job.status == "running":
                    # A prior owner died. Bound repeated crash recovery separately from retries.
                    recoveries = getattr(job, "recovery_count", 0)
                    if recoveries >= 3:
                        self._mark_failed(job_id, VVoiceError("Crash recovery limit reached"))
                        return
                    job = _replace_job(job, status="queued", recovery_count=recoveries + 1,
                                       max_attempts=max(job.max_attempts, job.attempt + 1))
                    self._save(job)
            token = set_request_id(getattr(job, "request_id", None) or job_id)
            self._run(job_id)
        finally:
            if token is not None:
                reset_request_id(token)
            with self._lock:
                self._pending_job_ids.discard(job_id)

    def _run(self, job_id: str) -> None:
        while True:
            try:
                job = self._start_attempt(job_id)
                if job is None:
                    return

                logger.info(
                    "tts_job_started",
                    extra={
                        "job_id": job_id,
                        "voice_id": job.voice_id,
                        "language": job.language,
                        "attempt": job.attempt,
                        "max_attempts": job.max_attempts,
                    },
                )

                self._raise_if_cancel_requested(job_id)
                job, reference_bytes = self._reference_snapshot(job)
                if job.provenance.get('deployment_version') and hasattr(self._tts, 'assert_deployment'):
                    self._tts.assert_deployment(job.model_id, job.provenance['deployment_version'])
                reference_audio, reference_sample_rate = load_audio_bytes(
                    reference_bytes,
                    target_sample_rate=self._tts.sample_rate_for(
                        job.language, model_id=job.model_id,
                    ),
                )
                self._raise_if_cancel_requested(job_id)
                job = self._set_progress_stage(job_id, "running_model")
                guard = (self._tts.deployment_guard(job.model_id, job.provenance.get("deployment_version"))
                         if hasattr(self._tts, "deployment_guard") else nullcontext())
                with guard:
                    speech = self._tts.synthesize(
                        text=job.text,
                        reference_audio=reference_audio,
                        reference_sample_rate=reference_sample_rate,
                        reference_text=job.reference_text,
                        language=job.language,
                        model_id=job.model_id,
                        num_steps=job.num_steps,
                        speed=job.speed,
                    )
                self._raise_if_cancel_requested(job_id)
                job = self._set_progress_stage(job_id, "finalizing")

                output_path = self._job_dir(job_id) / "output.wav"
                temporary_output_path = output_path.with_suffix(".wav.tmp")
                atomic_write_bytes(temporary_output_path, encode_wav(speech.samples, speech.sample_rate))
                self._complete_successfully(
                    job_id,
                    temporary_output_path=temporary_output_path,
                    output_path=output_path,
                    sample_rate=speech.sample_rate,
                    duration_seconds=speech.duration_seconds,
                )
                logger.info(
                    "tts_job_succeeded",
                    extra={
                        "job_id": job_id,
                        "voice_id": job.voice_id,
                        "language": job.language,
                        "attempt": job.attempt,
                        "duration_seconds": speech.duration_seconds,
                    },
                )
                return
            except TtsJobNotFoundError:
                return  # A queued cancellation may have been deleted before the worker reached it.
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
        # Import/reconcile v1 records once. Never mutate a live worker's job here.
        # Only the OS-lock owner executes recovered work; API-only processes just enqueue.
        with self._lock:
            for path in self._jobs_dir.glob("*/metadata.json"):
                try:
                    job = self.get(path.parent.name)
                except TtsJobNotFoundError:
                    continue
                self._save(job)
                if job.status not in TERMINAL_STATUSES:
                    self._executor.submit(self._run_queued, job.job_id)

    def _reference_snapshot(self, job: TtsJob) -> tuple[TtsJob, bytes]:
        with self._lock:
            reference_path = artifact_path(self._job_dir(job.job_id), "reference.wav")
            if job.reference_text is None and job.reference_audio_sha256 is None:
                # Legacy records had only a voice ID. Freeze their reference on first use.
                profile, reference_bytes = self._voices.snapshot(job.voice_id)
                atomic_write_bytes(reference_path, reference_bytes)
                current = self.get(job.job_id)
                job = _replace_job(
                    current,
                    reference_text=profile.reference_text,
                    reference_audio_sha256=content_sha256(reference_bytes),
                )
                self._save(job)
            else:
                if not reference_path.is_file():
                    raise VVoiceError("TTS job reference audio is missing")
                reference_bytes = reference_path.read_bytes()
            if content_sha256(reference_bytes) != job.reference_audio_sha256:
                raise VVoiceError("TTS job reference audio integrity check failed")
            return job, reference_bytes

    def _save(self, job: TtsJob) -> None:
        with self._lock:
            self._job_dir(job.job_id).mkdir(parents=True, exist_ok=True)
            metadata_path = self._metadata_path(job.job_id)
            atomic_write_metadata(metadata_path, _job_to_metadata(job))
            self._executor.record(_job_to_metadata(job))

    def _load(self, metadata_path: Path) -> TtsJob:
        with self._lock:
            raw = read_metadata(metadata_path)
        output_path = raw.get("output_path")
        status = raw["status"]
        failed_reason = raw.get("failed_reason")
        max_attempts = int(raw.get("max_attempts") or self._max_attempts)
        if (raw.get("reference_text") is None) != (raw.get("reference_audio_sha256") is None):
            raise ValueError("TTS job reference snapshot metadata is incomplete")
        language = normalize_language(raw.get("language", DEFAULT_LANGUAGE))
        model_id = raw.get("model_id", f"zipvoice-{language}")
        if not isinstance(model_id, str) or not model_id.strip():
            raise ValueError("TTS job model_id must be a nonempty string")
        fingerprint = raw.get("request_fingerprint")
        if "model_id" not in raw and fingerprint:
            # Old hashes omitted model_id. Upgrade only hashes that match the original payload.
            payload = {
                "language": language,
                "num_steps": raw.get("num_steps"),
                "speed": raw.get("speed"),
                "text": raw["text"],
                "voice_id": raw["voice_id"],
            }
            if fingerprint == _tts_request_fingerprint(**payload):
                fingerprint = _tts_request_fingerprint(**payload, model_id=model_id)
        return TtsJob(
            job_id=raw["job_id"],
            request_id=raw.get("request_id"),
            actor_id=raw.get("actor_id"),
            provenance=raw.get("provenance", {}),
            recovery_count=int(raw.get("recovery_count", 0)),
            status=status,
            voice_id=raw["voice_id"],
            language=language,
            model_id=model_id,
            text=raw["text"],
            num_steps=raw.get("num_steps"),
            speed=raw.get("speed"),
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
            request_fingerprint=fingerprint,
            output_path=portable_artifact_path(metadata_path.parent, output_path, "output.wav") if output_path else None,
            sample_rate=raw.get("sample_rate"),
            duration_seconds=raw.get("duration_seconds"),
            reference_text=raw.get("reference_text"),
            reference_audio_sha256=raw.get("reference_audio_sha256"),
        )

    def _start_attempt(self, job_id: str) -> TtsJob | None:
        with self._lock:
            job = self.get(job_id)
            if job.status in TERMINAL_STATUSES:
                return None
            if job.cancel_requested or job.status == "cancelling":
                completed_at = _now()
                self._save(
                    _replace_job(
                        job,
                        status="cancelled",
                        completed_at=completed_at,
                        error="Job was cancelled before the next attempt",
                        cancel_requested=True,
                        failed_reason="cancelled",
                        progress_stage="cancelled",
                        stage_started_at=completed_at,
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
            except TtsJobNotFoundError:
                return
            if job.status in TERMINAL_STATUSES:
                return

            completed_at = _now()
            cancelled = _replace_job(
                job,
                status="cancelled",
                completed_at=completed_at,
                error=message,
                cancel_requested=True,
                failed_reason="cancelled",
                progress_stage="cancelled",
                stage_started_at=completed_at,
            )
            if cancelled.output_path and cancelled.output_path.exists():
                cancelled.output_path.unlink()
            temporary_output_path = self._job_dir(job_id) / "output.wav.tmp"
            if temporary_output_path.exists():
                temporary_output_path.unlink()
            self._save(cancelled)
        logger.info(
            "tts_job_cancelled",
            extra={"job_id": job_id, "voice_id": job.voice_id, "attempt": job.attempt},
        )

    def _queue_retry(self, job_id: str, exc: Exception) -> bool:
        with self._lock:
            try:
                job = self.get(job_id)
            except TtsJobNotFoundError:
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
            "tts_job_retrying",
            extra={
                "job_id": job_id,
                "voice_id": job.voice_id,
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
            except TtsJobNotFoundError:
                return
            if job.status in TERMINAL_STATUSES:
                return
            if job.cancel_requested or job.status == "cancelling":
                self._mark_cancelled(job_id, "Job was cancelled")
                return

            completed_at = _now()
            self._save(
                _replace_job(
                    job,
                    status="failed",
                    completed_at=completed_at,
                    error=public_error_message(exc),
                    failed_reason=_failed_reason_for(exc),
                    progress_stage="failed",
                    stage_started_at=completed_at,
                )
            )
        logger.exception(
            "tts_job_failed",
            extra={
                "job_id": job_id,
                "voice_id": job.voice_id,
                "language": job.language,
                "attempt": job.attempt,
                "max_attempts": job.max_attempts,
            },
        )

    def _set_progress_stage(self, job_id: str, stage: str) -> TtsJob:
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
        temporary_output_path: Path,
        output_path: Path,
        sample_rate: int,
        duration_seconds: float,
    ) -> TtsJob:
        try:
            with self._lock:
                job = self.get(job_id)
                if job.cancel_requested or job.status == "cancelling":
                    raise _JobCancelled("Job was cancelled")
                temporary_output_path.replace(output_path)
                completed_at = _now()
                completed = _replace_job(
                    job,
                    status="succeeded",
                    completed_at=completed_at,
                    error=None,
                    failed_reason=None,
                    progress_stage="succeeded",
                    stage_started_at=completed_at,
                    output_path=output_path,
                    sample_rate=sample_rate,
                    duration_seconds=duration_seconds,
                    provenance={**job.provenance, "output_sha256": content_sha256(output_path.read_bytes())},
                )
                self._save(completed)
                return completed
        finally:
            if temporary_output_path.exists():
                temporary_output_path.unlink()

    def _job_dir(self, job_id: str) -> Path:
        try:
            return record_directory(self._jobs_dir, job_id)
        except (ValueError, OSError) as exc:
            raise TtsJobNotFoundError(f"TTS job not found: {job_id}") from exc

    def _metadata_path(self, job_id: str) -> Path:
        return self._job_dir(job_id) / "metadata.json"


def _job_to_metadata(job: TtsJob) -> dict:
    return {
        "job_id": job.job_id,
        "request_id": job.request_id,
        "actor_id": job.actor_id,
        "provenance": job.provenance,
        "recovery_count": job.recovery_count,
        "status": job.status,
        "voice_id": job.voice_id,
        "language": job.language,
        "model_id": job.model_id,
        "text": job.text,
        "num_steps": job.num_steps,
        "speed": job.speed,
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
        "output_path": job.output_path.name if job.output_path else None,
        "sample_rate": job.sample_rate,
        "duration_seconds": job.duration_seconds,
        "reference_text": job.reference_text,
        "reference_audio_sha256": job.reference_audio_sha256,
    }


def _replace_job(job: TtsJob, **changes) -> TtsJob:
    return replace(job, **changes)


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _tts_request_fingerprint(
    *,
    language: str,
    text: str,
    voice_id: str,
    num_steps: int | None,
    speed: float | None,
    model_id: str | None = None,
) -> str:
    payload = {
        "language": language,
        "num_steps": num_steps,
        "speed": speed,
        "text": text,
        "voice_id": voice_id,
    }
    if model_id is not None:
        payload["model_id"] = model_id
    return request_fingerprint(payload)


def _cutoff(max_age_seconds: int | None) -> datetime | None:
    if max_age_seconds is None or max_age_seconds <= 0:
        return None
    return datetime.now(tz=timezone.utc) - timedelta(seconds=max_age_seconds)


def _job_age_anchor(job: TtsJob) -> datetime:
    value = job.completed_at or job.created_at
    timestamp = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    return timestamp if timestamp.tzinfo else timestamp.replace(tzinfo=timezone.utc)


def _is_retryable_exception(exc: Exception) -> bool:
    return isinstance(exc, InferenceTransientError) or not isinstance(exc, VVoiceError)


def _failed_reason_for(exc: Exception) -> str:
    return "runtime_error" if _is_retryable_exception(exc) else "application_error"
