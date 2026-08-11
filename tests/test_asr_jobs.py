import time
import threading

import numpy as np

from vvoice.domains.asr.jobs import AsrJobService
from vvoice.domains.asr.service import Transcription
from vvoice.shared.audio.io import encode_wav


ASYNC_TEST_TIMEOUT_SECONDS = 10


class FakeAsr:
    def sample_rate_for(self, language: str | None = None) -> int:
        return 16000

    def transcribe(
        self,
        samples: np.ndarray,
        sample_rate: int,
        language: str | None = None,
    ) -> Transcription:
        return Transcription(text=f"{language or 'vi'}-sample-count-{len(samples)}", sample_rate=sample_rate)


class FlakyAsr(FakeAsr):
    def __init__(self) -> None:
        self.calls = 0

    def transcribe(
        self,
        samples: np.ndarray,
        sample_rate: int,
        language: str | None = None,
    ) -> Transcription:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("transient ASR failure")
        return Transcription(text="retry-ok", sample_rate=sample_rate)


class BlockingAsr(FakeAsr):
    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()

    def transcribe(
        self,
        samples: np.ndarray,
        sample_rate: int,
        language: str | None = None,
    ) -> Transcription:
        self.started.set()
        if not self.release.wait(timeout=ASYNC_TEST_TIMEOUT_SECONDS):
            raise RuntimeError("test ASR did not release")
        return Transcription(text="released", sample_rate=sample_rate)


def test_asr_job_service_runs_job_from_audio(tmp_path) -> None:
    jobs = AsrJobService(
        tmp_path / "asr-jobs",
        FakeAsr(),
        target_sample_rate=16000,
    )
    try:
        audio = encode_wav(np.zeros(1600, dtype=np.float32), 16000)
        job = jobs.create_from_audio(audio_bytes=audio, filename="input.wav", language="en")
        completed = wait_for_job(jobs, job.job_id)

        assert completed.status == "succeeded"
        assert completed.attempt == 1
        assert completed.max_attempts == 1
        assert completed.cancel_requested is False
        assert completed.failed_reason is None
        assert completed.language == "en"
        assert completed.input_path is not None
        assert completed.input_path.exists()
        assert completed.text == "en-sample-count-1600"
        assert completed.sample_rate == 16000
        assert completed.duration_seconds == 0.1
        assert jobs.list()[0].job_id == job.job_id

        assert jobs.cleanup(max_age_seconds=999999) == []
        assert jobs.cleanup() == [job.job_id]
        assert jobs.list() == []
    finally:
        jobs.shutdown()


def test_asr_job_service_retries_transient_failures(tmp_path) -> None:
    fake_asr = FlakyAsr()
    jobs = AsrJobService(
        tmp_path / "asr-jobs",
        fake_asr,
        target_sample_rate=16000,
        max_attempts=2,
        retry_backoff_seconds=0,
    )
    try:
        audio = encode_wav(np.zeros(1600, dtype=np.float32), 16000)
        job = jobs.create_from_audio(audio_bytes=audio, filename="input.wav", language="en")
        completed = wait_for_job(jobs, job.job_id)

        assert completed.status == "succeeded"
        assert completed.attempt == 2
        assert completed.max_attempts == 2
        assert completed.text == "retry-ok"
        assert fake_asr.calls == 2
    finally:
        jobs.shutdown()


def test_asr_job_service_cancels_running_job_at_safe_point(tmp_path) -> None:
    fake_asr = BlockingAsr()
    jobs = AsrJobService(
        tmp_path / "asr-jobs",
        fake_asr,
        target_sample_rate=16000,
    )
    try:
        audio = encode_wav(np.zeros(1600, dtype=np.float32), 16000)
        job = jobs.create_from_audio(audio_bytes=audio, filename="input.wav", language="en")
        assert fake_asr.started.wait(timeout=ASYNC_TEST_TIMEOUT_SECONDS)

        cancelling = jobs.cancel(job.job_id)
        assert cancelling.status == "cancelling"
        assert cancelling.cancel_requested is True

        fake_asr.release.set()
        completed = wait_for_job(jobs, job.job_id)

        assert completed.status == "cancelled"
        assert completed.cancel_requested is True
        assert completed.failed_reason == "cancelled"
        assert completed.text is None
    finally:
        fake_asr.release.set()
        jobs.shutdown()


def test_asr_job_service_cancels_queued_job(tmp_path) -> None:
    fake_asr = BlockingAsr()
    jobs = AsrJobService(
        tmp_path / "asr-jobs",
        fake_asr,
        target_sample_rate=16000,
        max_workers=1,
    )
    try:
        audio = encode_wav(np.zeros(1600, dtype=np.float32), 16000)
        first = jobs.create_from_audio(audio_bytes=audio, filename="first.wav", language="en")
        assert fake_asr.started.wait(timeout=ASYNC_TEST_TIMEOUT_SECONDS)
        second = jobs.create_from_audio(audio_bytes=audio, filename="second.wav", language="en")

        cancelled = jobs.cancel(second.job_id)
        assert cancelled.status == "cancelled"
        assert cancelled.failed_reason == "cancelled"

        fake_asr.release.set()
        assert wait_for_job(jobs, first.job_id).status == "succeeded"
        assert jobs.get(second.job_id).status == "cancelled"
        assert jobs.cleanup() == [second.job_id, first.job_id]
    finally:
        fake_asr.release.set()
        jobs.shutdown()


def test_asr_job_service_marks_interrupted_jobs_failed(tmp_path) -> None:
    jobs = AsrJobService(
        tmp_path / "asr-jobs",
        FakeAsr(),
        target_sample_rate=16000,
    )
    jobs.shutdown()

    job_dir = tmp_path / "asr-jobs" / "interrupted"
    job_dir.mkdir(parents=True)
    (job_dir / "metadata.json").write_text(
        """
        {
          "job_id": "interrupted",
          "status": "running",
          "filename": "input.wav",
          "created_at": "2026-06-30T00:00:00+00:00",
          "started_at": "2026-06-30T00:00:01+00:00",
          "completed_at": null,
          "error": null,
          "input_path": null,
          "text": null,
          "sample_rate": null,
          "duration_seconds": null
        }
        """,
        encoding="utf-8",
    )

    recovered = AsrJobService(
        tmp_path / "asr-jobs",
        FakeAsr(),
        target_sample_rate=16000,
    )
    try:
        job = recovered.get("interrupted")

        assert job.status == "failed"
        assert job.language == "vi"
        assert job.error == "Job was interrupted by server restart"
        assert job.failed_reason == "interrupted"
    finally:
        recovered.shutdown()


def wait_for_job(jobs: AsrJobService, job_id: str):
    deadline = time.monotonic() + ASYNC_TEST_TIMEOUT_SECONDS
    job = jobs.get(job_id)
    while time.monotonic() < deadline:
        job = jobs.get(job_id)
        if job.status in {"succeeded", "failed", "cancelled"}:
            return job
        time.sleep(0.05)
    raise AssertionError(f"ASR job did not finish; last status was {job.status!r}")
