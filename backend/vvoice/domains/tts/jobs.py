from __future__ import annotations

import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from vvoice.core.errors import TtsJobNotFoundError, VVoiceError
from vvoice.shared.audio.io import encode_wav, load_audio_bytes
from vvoice.shared.language import DEFAULT_LANGUAGE, normalize_language
from vvoice.domains.tts.service import ZipVoiceService
from vvoice.domains.voices.service import VoiceStore


TERMINAL_STATUSES = {"succeeded", "failed"}


@dataclass(frozen=True)
class TtsJob:
    job_id: str
    status: str
    voice_id: str
    language: str
    text: str
    num_steps: int | None
    speed: float | None
    created_at: str
    started_at: str | None
    completed_at: str | None
    error: str | None
    output_path: Path | None
    sample_rate: int | None
    duration_seconds: float | None


class TtsJobService:
    def __init__(
        self,
        jobs_dir: Path,
        tts: ZipVoiceService,
        voices: VoiceStore,
        *,
        max_workers: int = 1,
    ) -> None:
        self._jobs_dir = jobs_dir
        self._tts = tts
        self._voices = voices
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="vvoice-tts-job",
        )
        self._jobs_dir.mkdir(parents=True, exist_ok=True)
        self._mark_interrupted_jobs()

    def create_from_voice(
        self,
        *,
        voice_id: str,
        text: str,
        language: str | None = None,
        num_steps: int | None = None,
        speed: float | None = None,
    ) -> TtsJob:
        text = text.strip()
        if not text:
            raise VVoiceError("text cannot be empty")

        profile = self._voices.get(voice_id)
        language = normalize_language(language or profile.language)
        self._tts.sample_rate_for(language)
        job_id = str(uuid.uuid4())
        now = _now()
        job_dir = self._job_dir(job_id)
        job_dir.mkdir(parents=True, exist_ok=False)
        job = TtsJob(
            job_id=job_id,
            status="queued",
            voice_id=voice_id,
            language=language,
            text=text,
            num_steps=num_steps,
            speed=speed,
            created_at=now,
            started_at=None,
            completed_at=None,
            error=None,
            output_path=job_dir / "output.wav",
            sample_rate=None,
            duration_seconds=None,
        )
        self._save(job)
        self._executor.submit(self._run, job_id)
        return job

    def list(self) -> list[TtsJob]:
        if not self._jobs_dir.exists():
            return []

        jobs = [
            self._load(metadata_path)
            for metadata_path in self._jobs_dir.glob("*/metadata.json")
        ]
        return sorted(jobs, key=lambda item: item.created_at, reverse=True)

    def get(self, job_id: str) -> TtsJob:
        metadata_path = self._metadata_path(job_id)
        if not metadata_path.exists():
            raise TtsJobNotFoundError(f"TTS job not found: {job_id}")
        return self._load(metadata_path)

    def delete(self, job_id: str) -> None:
        job = self.get(job_id)
        if job.status not in TERMINAL_STATUSES:
            raise VVoiceError(f"Cannot delete TTS job while it is {job.status}")

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

            profile = self._voices.get(job.voice_id)
            reference_audio, reference_sample_rate = load_audio_bytes(
                profile.audio_path.read_bytes(),
                target_sample_rate=self._tts.sample_rate_for(job.language),
            )
            speech = self._tts.synthesize(
                text=job.text,
                reference_audio=reference_audio,
                reference_sample_rate=reference_sample_rate,
                reference_text=profile.reference_text,
                language=job.language,
                num_steps=job.num_steps,
                speed=job.speed,
            )

            output_path = self._job_dir(job_id) / "output.wav"
            output_path.write_bytes(encode_wav(speech.samples, speech.sample_rate))
            self._save(
                _replace_job(
                    job,
                    status="succeeded",
                    completed_at=_now(),
                    error=None,
                    output_path=output_path,
                    sample_rate=speech.sample_rate,
                    duration_seconds=speech.duration_seconds,
                )
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
            except TtsJobNotFoundError:
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

    def _save(self, job: TtsJob) -> None:
        with self._lock:
            self._job_dir(job.job_id).mkdir(parents=True, exist_ok=True)
            metadata_path = self._metadata_path(job.job_id)
            tmp_path = metadata_path.with_suffix(".json.tmp")
            tmp_path.write_text(
                json.dumps(_job_to_metadata(job), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp_path.replace(metadata_path)

    def _load(self, metadata_path: Path) -> TtsJob:
        raw = json.loads(metadata_path.read_text(encoding="utf-8"))
        output_path = raw.get("output_path")
        return TtsJob(
            job_id=raw["job_id"],
            status=raw["status"],
            voice_id=raw["voice_id"],
            language=normalize_language(raw.get("language", DEFAULT_LANGUAGE)),
            text=raw["text"],
            num_steps=raw.get("num_steps"),
            speed=raw.get("speed"),
            created_at=raw["created_at"],
            started_at=raw.get("started_at"),
            completed_at=raw.get("completed_at"),
            error=raw.get("error"),
            output_path=Path(output_path) if output_path else None,
            sample_rate=raw.get("sample_rate"),
            duration_seconds=raw.get("duration_seconds"),
        )

    def _job_dir(self, job_id: str) -> Path:
        if "/" in job_id or "\\" in job_id or job_id in {"", ".", ".."}:
            raise TtsJobNotFoundError(f"TTS job not found: {job_id}")
        return self._jobs_dir / job_id

    def _metadata_path(self, job_id: str) -> Path:
        return self._job_dir(job_id) / "metadata.json"


def _job_to_metadata(job: TtsJob) -> dict:
    return {
        "job_id": job.job_id,
        "status": job.status,
        "voice_id": job.voice_id,
        "language": job.language,
        "text": job.text,
        "num_steps": job.num_steps,
        "speed": job.speed,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
        "error": job.error,
        "output_path": str(job.output_path) if job.output_path else None,
        "sample_rate": job.sample_rate,
        "duration_seconds": job.duration_seconds,
    }


def _replace_job(job: TtsJob, **changes) -> TtsJob:
    values = _job_to_metadata(job)
    values.update(changes)
    output_path = values.get("output_path")
    return TtsJob(
        job_id=values["job_id"],
        status=values["status"],
        voice_id=values["voice_id"],
        language=normalize_language(values.get("language", DEFAULT_LANGUAGE)),
        text=values["text"],
        num_steps=values.get("num_steps"),
        speed=values.get("speed"),
        created_at=values["created_at"],
        started_at=values.get("started_at"),
        completed_at=values.get("completed_at"),
        error=values.get("error"),
        output_path=Path(output_path) if output_path else None,
        sample_rate=values.get("sample_rate"),
        duration_seconds=values.get("duration_seconds"),
    )


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _cutoff(max_age_seconds: int | None) -> datetime | None:
    if max_age_seconds is None or max_age_seconds <= 0:
        return None
    return datetime.now(tz=timezone.utc) - timedelta(seconds=max_age_seconds)


def _job_age_anchor(job: TtsJob) -> datetime:
    value = job.completed_at or job.created_at
    return datetime.fromisoformat(value)
