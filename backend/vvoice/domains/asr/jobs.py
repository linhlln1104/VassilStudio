from __future__ import annotations

import json
import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from vvoice.core.errors import AsrJobNotFoundError, VVoiceError
from vvoice.domains.asr.service import AsrService
from vvoice.shared.audio.io import duration_seconds, encode_wav, load_audio_bytes
from vvoice.shared.language import DEFAULT_LANGUAGE, normalize_language


TERMINAL_STATUSES = {"succeeded", "failed"}
logger = logging.getLogger("vvoice.jobs.asr")


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
    ) -> None:
        self._jobs_dir = jobs_dir
        self._asr = asr
        self._target_sample_rate = target_sample_rate
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
    ) -> AsrJob:
        normalized_language = normalize_language(language)
        target_sample_rate = self._sample_rate_for(normalized_language)
        samples, sample_rate = load_audio_bytes(audio_bytes, target_sample_rate=target_sample_rate)
        job_id = str(uuid.uuid4())
        now = _now()
        job_dir = self._job_dir(job_id)
        job_dir.mkdir(parents=True, exist_ok=False)
        input_path = job_dir / "input.wav"
        input_path.write_bytes(encode_wav(samples, sample_rate))
        job = AsrJob(
            job_id=job_id,
            status="queued",
            filename=filename or "audio",
            language=normalized_language,
            created_at=now,
            started_at=None,
            completed_at=None,
            error=None,
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
                "filename": job.filename,
                "duration_seconds": job.duration_seconds,
            },
        )
        self._executor.submit(self._run, job_id)
        return job

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
        try:
            job = self.get(job_id)
            self._save(_replace_job(job, status="running", started_at=_now(), error=None))
            logger.info("asr_job_started", extra={"job_id": job_id, "language": job.language})

            if not job.input_path or not job.input_path.exists():
                raise VVoiceError("ASR job input audio is missing")

            samples, sample_rate = load_audio_bytes(
                job.input_path.read_bytes(),
                target_sample_rate=self._sample_rate_for(job.language),
            )
            result = self._asr.transcribe(samples, sample_rate, job.language)
            self._save(
                _replace_job(
                    job,
                    status="succeeded",
                    completed_at=_now(),
                    error=None,
                    text=result.text,
                    sample_rate=result.sample_rate,
                    duration_seconds=duration_seconds(samples, sample_rate),
                )
            )
            logger.info(
                "asr_job_succeeded",
                extra={
                    "job_id": job_id,
                    "language": job.language,
                    "duration_seconds": duration_seconds(samples, sample_rate),
                },
            )
        except Exception as exc:  # pragma: no cover - exercised through smoke tests
            try:
                job = self.get(job_id)
                self._save(
                    _replace_job(
                        job,
                        status="failed",
                        completed_at=_now(),
                        error=str(exc),
                    )
                )
                logger.exception(
                    "asr_job_failed",
                    extra={"job_id": job_id, "language": job.language},
                )
            except AsrJobNotFoundError:
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
        raw = json.loads(metadata_path.read_text(encoding="utf-8"))
        input_path = raw.get("input_path")
        return AsrJob(
            job_id=raw["job_id"],
            status=raw["status"],
            filename=raw["filename"],
            language=normalize_language(raw.get("language", DEFAULT_LANGUAGE)),
            created_at=raw["created_at"],
            started_at=raw.get("started_at"),
            completed_at=raw.get("completed_at"),
            error=raw.get("error"),
            input_path=Path(input_path) if input_path else None,
            text=raw.get("text"),
            sample_rate=raw.get("sample_rate"),
            duration_seconds=raw.get("duration_seconds"),
        )

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
