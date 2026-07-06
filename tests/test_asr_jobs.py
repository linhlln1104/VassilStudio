import time

import numpy as np

from vvoice.domains.asr.jobs import AsrJobService
from vvoice.domains.asr.service import Transcription
from vvoice.shared.audio.io import encode_wav


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
    finally:
        recovered.shutdown()


def wait_for_job(jobs: AsrJobService, job_id: str):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        job = jobs.get(job_id)
        if job.status in {"succeeded", "failed"}:
            return job
        time.sleep(0.05)
    raise AssertionError("ASR job did not finish")
