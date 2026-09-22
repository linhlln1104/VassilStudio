import time
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import numpy as np
import pytest

from vvoice.core.errors import (
    IdempotencyConflictError, JobQueueFullError, PUBLIC_JOB_ERROR_MESSAGE,
    TtsJobNotFoundError, VVoiceError,
)
from vvoice.shared.audio.io import encode_wav
from vvoice.domains.tts.jobs import TtsJobService
from vvoice.domains.tts.router import _job_response
from vvoice.domains.tts.service import GeneratedSpeech
from vvoice.domains.voices.service import VoiceStore


ASYNC_TEST_TIMEOUT_SECONDS = 10


class FakeTts:
    def __init__(self) -> None:
        self.last_kwargs = {}

    def synthesize(self, **kwargs) -> GeneratedSpeech:
        self.last_kwargs = kwargs
        samples = np.zeros(2400, dtype=np.float32)
        return GeneratedSpeech(samples=samples, sample_rate=24000, duration_seconds=0.1)

    def sample_rate_for(self, language: str | None = None) -> int:
        return 24000


class FlakyTts(FakeTts):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    def synthesize(self, **kwargs) -> GeneratedSpeech:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("transient TTS failure")
        return super().synthesize(**kwargs)


class BlockingTts(FakeTts):
    def __init__(self) -> None:
        super().__init__()
        self.started = threading.Event()
        self.release = threading.Event()

    def synthesize(self, **kwargs) -> GeneratedSpeech:
        self.started.set()
        if not self.release.wait(timeout=ASYNC_TEST_TIMEOUT_SECONDS):
            raise RuntimeError("test TTS did not release")
        return super().synthesize(**kwargs)


class FailingTts(FakeTts):
    def synthesize(self, **kwargs) -> GeneratedSpeech:
        raise RuntimeError(r"vocoder failed at C:\Users\private\models\vocoder.onnx")


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
        assert completed.attempt == 1
        assert completed.max_attempts == 1
        assert completed.cancel_requested is False
        assert completed.failed_reason is None
        assert completed.progress_stage == "succeeded"
        assert completed.stage_started_at
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


def test_tts_job_service_retries_transient_failures(tmp_path) -> None:
    voices = VoiceStore(tmp_path / "voices")
    profile = create_voice(voices)
    fake_tts = FlakyTts()
    jobs = TtsJobService(
        tmp_path / "tts-jobs",
        fake_tts,
        voices,
        max_attempts=2,
        retry_backoff_seconds=0,
    )
    try:
        job = jobs.create_from_voice(voice_id=profile.voice_id, text="xin chao moi")
        completed = wait_for_job(jobs, job.job_id)

        assert completed.status == "succeeded"
        assert completed.attempt == 2
        assert completed.max_attempts == 2
        assert fake_tts.calls == 2
    finally:
        jobs.shutdown()


def test_tts_job_service_redacts_unexpected_failure_details(tmp_path) -> None:
    voices = VoiceStore(tmp_path / "voices")
    profile = create_voice(voices)
    jobs = TtsJobService(tmp_path / "tts-jobs", FailingTts(), voices)
    try:
        job = jobs.create_from_voice(voice_id=profile.voice_id, text="xin chao moi")
        completed = wait_for_job(jobs, job.job_id)

        assert completed.status == "failed"
        assert completed.error == PUBLIC_JOB_ERROR_MESSAGE
        assert "C:\\Users" not in completed.error
        legacy_payload = _job_response(
            replace(completed, error=r"legacy failure at C:\Users\private\models\vocoder.onnx")
        )
        assert legacy_payload["error"] == PUBLIC_JOB_ERROR_MESSAGE
    finally:
        jobs.shutdown()


def test_tts_job_service_cancels_running_job_at_safe_point(tmp_path) -> None:
    voices = VoiceStore(tmp_path / "voices")
    profile = create_voice(voices)
    fake_tts = BlockingTts()
    jobs = TtsJobService(
        tmp_path / "tts-jobs",
        fake_tts,
        voices,
    )
    try:
        job = jobs.create_from_voice(voice_id=profile.voice_id, text="xin chao moi")
        assert fake_tts.started.wait(timeout=ASYNC_TEST_TIMEOUT_SECONDS)

        cancelling = jobs.cancel(job.job_id)
        assert cancelling.status == "cancelling"
        assert cancelling.cancel_requested is True
        assert cancelling.progress_stage == "running_model"

        fake_tts.release.set()
        completed = wait_for_job(jobs, job.job_id)

        assert completed.status == "cancelled"
        assert completed.cancel_requested is True
        assert completed.failed_reason == "cancelled"
        assert completed.progress_stage == "cancelled"
        assert completed.output_path is not None
        assert not completed.output_path.exists()
    finally:
        fake_tts.release.set()
        jobs.shutdown()


def test_tts_job_service_cancels_queued_job(tmp_path) -> None:
    voices = VoiceStore(tmp_path / "voices")
    profile = create_voice(voices)
    fake_tts = BlockingTts()
    jobs = TtsJobService(
        tmp_path / "tts-jobs",
        fake_tts,
        voices,
        max_workers=1,
    )
    try:
        first = jobs.create_from_voice(voice_id=profile.voice_id, text="first")
        assert fake_tts.started.wait(timeout=ASYNC_TEST_TIMEOUT_SECONDS)
        second = jobs.create_from_voice(voice_id=profile.voice_id, text="second")

        cancelled = jobs.cancel(second.job_id)
        assert cancelled.status == "cancelled"
        assert cancelled.failed_reason == "cancelled"

        fake_tts.release.set()
        assert wait_for_job(jobs, first.job_id).status == "succeeded"
        assert jobs.get(second.job_id).status == "cancelled"
        assert jobs.cleanup() == [second.job_id, first.job_id]
    finally:
        fake_tts.release.set()
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
        assert job.failed_reason == "interrupted"
        assert job.progress_stage == "failed"
        assert job.stage_started_at == job.completed_at
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


def test_tts_job_service_rejects_text_over_limit(tmp_path) -> None:
    jobs = TtsJobService(
        tmp_path / "tts-jobs",
        FakeTts(),
        VoiceStore(tmp_path / "voices"),
        max_text_chars=4,
    )
    try:
        with pytest.raises(VVoiceError, match="text must be 4 characters or fewer"):
            jobs.create_from_voice(voice_id="missing", text="hello")
    finally:
        jobs.shutdown()


def test_tts_job_service_deduplicates_concurrent_create_requests(tmp_path) -> None:
    voices = VoiceStore(tmp_path / "voices")
    profile = create_voice(voices)
    fake_tts = BlockingTts()
    jobs = TtsJobService(tmp_path / "tts-jobs", fake_tts, voices)
    try:
        with ThreadPoolExecutor(max_workers=2) as callers:
            futures = [
                callers.submit(
                    jobs.create_from_voice,
                    voice_id=profile.voice_id,
                    text="same render",
                    language="en",
                    num_steps=4,
                    speed=1.0,
                    idempotency_key="tts:create:request-1",
                )
                for _ in range(2)
            ]
            created = [future.result() for future in futures]

        assert created[0].job_id == created[1].job_id
        assert len(list((tmp_path / "tts-jobs").glob("*/metadata.json"))) == 1
        metadata = (tmp_path / "tts-jobs" / created[0].job_id / "metadata.json").read_text(
            encoding="utf-8"
        )
        assert "tts:create:request-1" not in metadata
        assert fake_tts.started.wait(timeout=ASYNC_TEST_TIMEOUT_SECONDS)

        with pytest.raises(IdempotencyConflictError, match="different TTS request"):
            jobs.create_from_voice(
                voice_id=profile.voice_id,
                text="different render",
                language="en",
                idempotency_key="tts:create:request-1",
            )

        fake_tts.release.set()
        assert wait_for_job(jobs, created[0].job_id).status == "succeeded"
    finally:
        fake_tts.release.set()
        jobs.shutdown()


def test_tts_job_service_rejects_invalid_idempotency_key(tmp_path) -> None:
    jobs = TtsJobService(
        tmp_path / "tts-jobs",
        FakeTts(),
        VoiceStore(tmp_path / "voices"),
    )
    try:
        with pytest.raises(VVoiceError, match="Idempotency-Key"):
            jobs.create_from_voice(
                voice_id="missing",
                text="hello",
                idempotency_key="contains spaces",
            )
    finally:
        jobs.shutdown()


def test_tts_queued_job_uses_accepted_reference_after_voice_edit_and_delete(tmp_path):
    voices = VoiceStore(tmp_path / "voices")
    profile = create_voice(voices)
    original_audio = profile.audio_path.read_bytes()
    tts = BlockingTts()
    jobs = TtsJobService(tmp_path / "jobs", tts, voices)
    try:
        first = jobs.create_from_voice(voice_id=profile.voice_id, text="first")
        assert tts.started.wait(timeout=ASYNC_TEST_TIMEOUT_SECONDS)
        queued = jobs.create_from_voice(
            voice_id=profile.voice_id, text="second", idempotency_key="snapshot-replay",
        )
        voices.update(profile.voice_id, reference_text="changed reference")
        voices.delete(profile.voice_id)
        replay = jobs.create_from_voice(
            voice_id=profile.voice_id, text="second", idempotency_key="snapshot-replay",
        )
        assert replay.job_id == queued.job_id
        tts.release.set()
        assert wait_for_job(jobs, first.job_id).status == "succeeded"
        completed = wait_for_job(jobs, queued.job_id)
        assert completed.status == "succeeded"
        assert completed.reference_text == profile.reference_text
        assert tts.last_kwargs["reference_text"] == profile.reference_text
        assert (tmp_path / "jobs" / queued.job_id / "reference.wav").read_bytes() == original_audio
        assert completed.reference_audio_sha256 == profile.audio_sha256
    finally:
        tts.release.set()
        jobs.shutdown()


def test_tts_retry_keeps_snapshot_when_voice_is_deleted_during_first_attempt(tmp_path):
    voices = VoiceStore(tmp_path / "voices")
    profile = create_voice(voices)

    class DeleteVoiceTts(FakeTts):
        calls = 0

        def synthesize(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                voices.update(profile.voice_id, reference_text="edited")
                voices.delete(profile.voice_id)
                raise RuntimeError("retry after profile removal")
            return super().synthesize(**kwargs)

    tts = DeleteVoiceTts()
    jobs = TtsJobService(
        tmp_path / "jobs", tts, voices, max_attempts=2, retry_backoff_seconds=0,
    )
    try:
        job = jobs.create_from_voice(voice_id=profile.voice_id, text="hello")
        completed = wait_for_job(jobs, job.job_id)
        assert completed.status == "succeeded"
        assert completed.attempt == 2
        assert tts.last_kwargs["reference_text"] == profile.reference_text
    finally:
        jobs.shutdown()


def test_tts_rejects_changed_snapshot_audio_before_inference(tmp_path):
    voices = VoiceStore(tmp_path / "voices")
    profile = create_voice(voices)
    tts = BlockingTts()
    directory = tmp_path / "jobs"
    jobs = TtsJobService(directory, tts, voices)
    try:
        first = jobs.create_from_voice(voice_id=profile.voice_id, text="first")
        assert tts.started.wait(timeout=ASYNC_TEST_TIMEOUT_SECONDS)
        queued = jobs.create_from_voice(voice_id=profile.voice_id, text="second")
        (directory / queued.job_id / "reference.wav").write_bytes(b"changed after acceptance")
        tts.release.set()
        assert wait_for_job(jobs, first.job_id).status == "succeeded"
        completed = wait_for_job(jobs, queued.job_id)
        assert completed.status == "failed"
        assert completed.failed_reason == "application_error"
        assert tts.last_kwargs["text"] == "first"
    finally:
        tts.release.set()
        jobs.shutdown()


@pytest.mark.parametrize("content", ["{", "[]", '{"job_id":"broken","status":[]}'])
def test_tts_jobs_preserve_corrupt_records_and_start_with_healthy_jobs(tmp_path, content):
    voices = VoiceStore(tmp_path / "voices")
    profile = create_voice(voices)
    directory = tmp_path / "jobs"
    jobs = TtsJobService(directory, FakeTts(), voices)
    job = jobs.create_from_voice(voice_id=profile.voice_id, text="hello")
    assert wait_for_job(jobs, job.job_id).status == "succeeded"
    jobs.shutdown()
    broken = directory / "broken"
    broken.mkdir()
    (broken / "metadata.json").write_text(content, encoding="utf-8")

    recovered = TtsJobService(directory, FakeTts(), voices)
    try:
        assert [item.job_id for item in recovered.list()] == [job.job_id]
        assert recovered.quarantined_count == 1
        assert next(broken.glob("metadata.corrupt-*.json")).read_text(encoding="utf-8") == content
        with pytest.raises(TtsJobNotFoundError):
            recovered.get("broken")
    finally:
        recovered.shutdown()


def test_tts_queue_rejects_excess_work_but_allows_idempotent_replay(tmp_path):
    voices = VoiceStore(tmp_path / "voices")
    profile = create_voice(voices)
    tts = BlockingTts()
    jobs = TtsJobService(tmp_path / "jobs", tts, voices, max_pending_jobs=1)
    try:
        first = jobs.create_from_voice(voice_id=profile.voice_id, text="first", idempotency_key="one")
        assert tts.started.wait(timeout=ASYNC_TEST_TIMEOUT_SECONDS)
        replay = jobs.create_from_voice(voice_id=profile.voice_id, text="first", idempotency_key="one")
        assert replay.job_id == first.job_id
        with pytest.raises(JobQueueFullError):
            jobs.create_from_voice(voice_id=profile.voice_id, text="second")
        assert len(jobs.list()) == 1
        tts.release.set()
        assert wait_for_job(jobs, first.job_id).status == "succeeded"
        second = jobs.create_from_voice(voice_id=profile.voice_id, text="second")
        assert wait_for_job(jobs, second.job_id).status == "succeeded"
    finally:
        tts.release.set()
        jobs.shutdown()


def wait_for_job(jobs: TtsJobService, job_id: str):
    deadline = time.monotonic() + ASYNC_TEST_TIMEOUT_SECONDS
    job = jobs.get(job_id)
    while time.monotonic() < deadline:
        job = jobs.get(job_id)
        if job.status in {"succeeded", "failed", "cancelled"}:
            return job
        time.sleep(0.05)
    raise AssertionError(f"TTS job did not finish; last status was {job.status!r}")


def create_voice(voices: VoiceStore):
    reference = np.zeros(24000, dtype=np.float32)
    return voices.create(
        name="demo",
        language="en",
        reference_text="xin chao",
        reference_text_source="user",
        audio_bytes=encode_wav(reference, 24000),
        sample_rate=24000,
        duration_seconds=1.0,
    )
