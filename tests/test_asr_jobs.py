import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import numpy as np
import pytest

from vvoice.core.errors import (
    IdempotencyConflictError,
    PUBLIC_JOB_ERROR_MESSAGE,
    TranscriptRevisionConflictError,
    VVoiceError,
)
from vvoice.domains.asr.jobs import AsrJobService
from vvoice.domains.asr.router import _job_response
from vvoice.domains.asr.service import Transcription
from vvoice.domains.asr.transcript import TranscriptSegment
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


class FailingAsr(FakeAsr):
    def transcribe(
        self,
        samples: np.ndarray,
        sample_rate: int,
        language: str | None = None,
    ) -> Transcription:
        raise RuntimeError(r"decoder failed at C:\Users\private\models\encoder.onnx")


class TimedAsr(FakeAsr):
    def transcribe(
        self,
        samples: np.ndarray,
        sample_rate: int,
        language: str | None = None,
    ) -> Transcription:
        return Transcription(
            text="Raw first sentence. Raw second sentence.",
            sample_rate=sample_rate,
            segments=(
                TranscriptSegment("segment-0001", 0.1, 1.4, "Raw first sentence."),
                TranscriptSegment("segment-0002", 1.4, 2.8, "Raw second sentence."),
            ),
        )


def test_asr_job_service_runs_job_from_audio(tmp_path, caplog) -> None:
    caplog.set_level(logging.INFO, logger="vvoice.jobs.asr")
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
        assert completed.progress_stage == "succeeded"
        assert completed.stage_started_at
        assert completed.language == "en"
        assert completed.input_path is not None
        assert completed.input_path.exists()
        assert completed.text == "en-sample-count-1600"
        assert completed.sample_rate == 16000
        assert completed.duration_seconds == 0.1
        assert jobs.list()[0].job_id == job.job_id
        created_record = next(record for record in caplog.records if record.message == "asr_job_created")
        assert created_record.source_filename == "input.wav"

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


def test_asr_job_service_redacts_unexpected_failure_details(tmp_path) -> None:
    jobs = AsrJobService(
        tmp_path / "asr-jobs",
        FailingAsr(),
        target_sample_rate=16000,
    )
    try:
        audio = encode_wav(np.zeros(1600, dtype=np.float32), 16000)
        job = jobs.create_from_audio(audio_bytes=audio, filename="input.wav", language="en")
        completed = wait_for_job(jobs, job.job_id)

        assert completed.status == "failed"
        assert completed.error == PUBLIC_JOB_ERROR_MESSAGE
        assert "C:\\Users" not in completed.error
        legacy_payload = _job_response(
            replace(completed, error=r"legacy failure at C:\Users\private\models\encoder.onnx")
        )
        assert legacy_payload["error"] == PUBLIC_JOB_ERROR_MESSAGE
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
        assert cancelling.progress_stage == "running_model"

        fake_asr.release.set()
        completed = wait_for_job(jobs, job.job_id)

        assert completed.status == "cancelled"
        assert completed.cancel_requested is True
        assert completed.failed_reason == "cancelled"
        assert completed.progress_stage == "cancelled"
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
        assert job.progress_stage == "failed"
        assert job.stage_started_at == job.completed_at
    finally:
        recovered.shutdown()


def test_asr_job_service_deduplicates_concurrent_create_requests(tmp_path) -> None:
    fake_asr = BlockingAsr()
    jobs = AsrJobService(
        tmp_path / "asr-jobs",
        fake_asr,
        target_sample_rate=16000,
    )
    audio = encode_wav(np.zeros(1600, dtype=np.float32), 16000)
    try:
        with ThreadPoolExecutor(max_workers=2) as callers:
            futures = [
                callers.submit(
                    jobs.create_from_audio,
                    audio_bytes=audio,
                    filename="same.wav",
                    language="en",
                    idempotency_key="asr:create:request-1",
                )
                for _ in range(2)
            ]
            created = [future.result() for future in futures]

        assert created[0].job_id == created[1].job_id
        assert len(list((tmp_path / "asr-jobs").glob("*/metadata.json"))) == 1
        metadata = (tmp_path / "asr-jobs" / created[0].job_id / "metadata.json").read_text(
            encoding="utf-8"
        )
        assert "asr:create:request-1" not in metadata
        assert fake_asr.started.wait(timeout=ASYNC_TEST_TIMEOUT_SECONDS)

        with pytest.raises(IdempotencyConflictError, match="different ASR request"):
            jobs.create_from_audio(
                audio_bytes=audio,
                filename="renamed.wav",
                language="en",
                idempotency_key="asr:create:request-1",
            )

        fake_asr.release.set()
        assert wait_for_job(jobs, created[0].job_id).status == "succeeded"
    finally:
        fake_asr.release.set()
        jobs.shutdown()


def test_asr_job_service_rejects_invalid_idempotency_key(tmp_path) -> None:
    jobs = AsrJobService(
        tmp_path / "asr-jobs",
        FakeAsr(),
        target_sample_rate=16000,
    )
    try:
        with pytest.raises(VVoiceError, match="Idempotency-Key"):
            jobs.create_from_audio(
                audio_bytes=b"not decoded",
                filename="input.wav",
                idempotency_key="contains spaces",
            )
    finally:
        jobs.shutdown()


def test_asr_job_service_preserves_raw_transcript_across_revisions(tmp_path) -> None:
    jobs = AsrJobService(
        tmp_path / "asr-jobs",
        TimedAsr(),
        target_sample_rate=16000,
    )
    try:
        audio = encode_wav(np.zeros(48_000, dtype=np.float32), 16000)
        created = jobs.create_from_audio(
            audio_bytes=audio,
            filename="interview.wav",
            language="en",
        )
        completed = wait_for_job(jobs, created.job_id)

        assert completed.timing_status == "available"
        assert completed.text == completed.raw_text
        assert completed.segments == completed.raw_segments
        assert completed.transcript_revision == 0

        revised = jobs.revise_transcript(
            completed.job_id,
            expected_revision=0,
            segment_edits=(
                ("segment-0001", "Corrected first sentence."),
                ("segment-0002", "Corrected second sentence."),
            ),
        )

        assert revised.text == "Corrected first sentence. Corrected second sentence."
        assert revised.raw_text == "Raw first sentence. Raw second sentence."
        assert revised.raw_segments[0].text == "Raw first sentence."
        assert revised.segments[0].text == "Corrected first sentence."
        assert revised.segments[0].start_seconds == 0.1
        assert revised.transcript_revision == 1
        assert revised.transcript_updated_at
        assert jobs.get(completed.job_id) == revised

        with pytest.raises(TranscriptRevisionConflictError, match="reload"):
            jobs.revise_transcript(
                completed.job_id,
                expected_revision=0,
                segment_edits=(
                    ("segment-0001", "Stale edit."),
                    ("segment-0002", "Stale edit."),
                ),
            )
    finally:
        jobs.shutdown()


def test_asr_job_service_revises_legacy_untimed_transcript(tmp_path) -> None:
    jobs_dir = tmp_path / "asr-jobs"
    job_dir = jobs_dir / "legacy"
    job_dir.mkdir(parents=True)
    (job_dir / "metadata.json").write_text(
        """
        {
          "job_id": "legacy",
          "status": "succeeded",
          "filename": "legacy.wav",
          "language": "vi",
          "created_at": "2026-06-30T00:00:00+00:00",
          "started_at": "2026-06-30T00:00:01+00:00",
          "completed_at": "2026-06-30T00:00:02+00:00",
          "error": null,
          "input_path": null,
          "text": "Ban goc",
          "sample_rate": 16000,
          "duration_seconds": 1.0
        }
        """,
        encoding="utf-8",
    )
    jobs = AsrJobService(jobs_dir, FakeAsr(), target_sample_rate=16000)
    try:
        legacy = jobs.get("legacy")
        assert legacy.raw_text == "Ban goc"
        assert legacy.timing_status == "unavailable"
        assert legacy.segments == ()

        revised = jobs.revise_transcript(
            "legacy",
            expected_revision=0,
            text="Ban da sua",
        )
        assert revised.text == "Ban da sua"
        assert revised.raw_text == "Ban goc"
        assert revised.transcript_revision == 1
    finally:
        jobs.shutdown()


def wait_for_job(jobs: AsrJobService, job_id: str):
    deadline = time.monotonic() + ASYNC_TEST_TIMEOUT_SECONDS
    job = jobs.get(job_id)
    while time.monotonic() < deadline:
        job = jobs.get(job_id)
        if job.status in {"succeeded", "failed", "cancelled"}:
            return job
        time.sleep(0.05)
    raise AssertionError(f"ASR job did not finish; last status was {job.status!r}")
