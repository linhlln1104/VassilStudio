import time

import numpy as np
import pytest

from vvoice.core.errors import VVoiceError
from vvoice.shared.audio.io import encode_wav
from vvoice.domains.tts.jobs import TtsJobService
from vvoice.domains.tts.service import GeneratedSpeech
from vvoice.domains.voices.service import VoiceStore


class FakeTts:
    def __init__(self) -> None:
        self.last_kwargs = {}

    def synthesize(self, **kwargs) -> GeneratedSpeech:
        self.last_kwargs = kwargs
        samples = np.zeros(2400, dtype=np.float32)
        return GeneratedSpeech(samples=samples, sample_rate=24000, duration_seconds=0.1)

    def sample_rate_for(self, language: str | None = None) -> int:
        return 24000


def test_tts_job_service_runs_job_from_voice(tmp_path) -> None:
    voices = VoiceStore(tmp_path / "voices")
    reference = np.zeros(24000, dtype=np.float32)
    profile = voices.create(
        name="demo",
        language="en",
        reference_text="xin chao",
        reference_text_source="user",
        audio_bytes=encode_wav(reference, 24000),
        sample_rate=24000,
        duration_seconds=1.0,
    )
    fake_tts = FakeTts()
    jobs = TtsJobService(
        tmp_path / "tts-jobs",
        fake_tts,
        voices,
    )

    try:
        job = jobs.create_from_voice(voice_id=profile.voice_id, text="xin chao moi")
        completed = wait_for_job(jobs, job.job_id)

        assert completed.status == "succeeded"
        assert completed.language == "en"
        assert fake_tts.last_kwargs["language"] == "en"
        assert completed.output_path is not None
        assert completed.output_path.exists()
        assert completed.sample_rate == 24000
        assert completed.duration_seconds == 0.1
        assert jobs.list()[0].job_id == job.job_id

        assert jobs.cleanup(max_age_seconds=999999) == []
        assert jobs.cleanup() == [job.job_id]
        assert jobs.list() == []
    finally:
        jobs.shutdown()


def test_tts_job_service_marks_interrupted_jobs_failed(tmp_path) -> None:
    voices = VoiceStore(tmp_path / "voices")
    jobs = TtsJobService(
        tmp_path / "tts-jobs",
        FakeTts(),
        voices,
    )
    jobs.shutdown()

    job_dir = tmp_path / "tts-jobs" / "interrupted"
    job_dir.mkdir(parents=True)
    (job_dir / "metadata.json").write_text(
        """
        {
          "job_id": "interrupted",
          "status": "running",
          "voice_id": "voice-1",
          "language": "vi",
          "text": "xin chao",
          "num_steps": null,
          "speed": null,
          "created_at": "2026-06-30T00:00:00+00:00",
          "started_at": "2026-06-30T00:00:01+00:00",
          "completed_at": null,
          "error": null,
          "output_path": null,
          "sample_rate": null,
          "duration_seconds": null
        }
        """,
        encoding="utf-8",
    )

    recovered = TtsJobService(
        tmp_path / "tts-jobs",
        FakeTts(),
        voices,
    )
    try:
        job = recovered.get("interrupted")

        assert job.status == "failed"
        assert job.error == "Job was interrupted by server restart"
    finally:
        recovered.shutdown()


def test_tts_job_service_rejects_invalid_generation_parameters(tmp_path) -> None:
    jobs = TtsJobService(
        tmp_path / "tts-jobs",
        FakeTts(),
        VoiceStore(tmp_path / "voices"),
    )
    try:
        with pytest.raises(VVoiceError, match="num_steps"):
            jobs.create_from_voice(voice_id="missing", text="hello", num_steps=0)

        with pytest.raises(VVoiceError, match="speed"):
            jobs.create_from_voice(voice_id="missing", text="hello", speed=3.0)
    finally:
        jobs.shutdown()


def wait_for_job(jobs: TtsJobService, job_id: str):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        job = jobs.get(job_id)
        if job.status in {"succeeded", "failed"}:
            return job
        time.sleep(0.05)
    raise AssertionError("TTS job did not finish")
