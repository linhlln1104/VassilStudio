from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from vvoice.core.errors import TranscriptRevisionConflictError
from vvoice.domains.asr.jobs import AsrJob
from vvoice.domains.asr.router import router
from vvoice.domains.asr.transcript import TranscriptSegment
from vvoice.main import register_exception_handlers


class TranscriptJobs:
    def __init__(self) -> None:
        self.job = _job()

    def get(self, job_id: str) -> AsrJob:
        assert job_id == self.job.job_id
        return self.job

    def revise_transcript(
        self,
        job_id: str,
        *,
        expected_revision: int,
        text: str | None,
        segment_edits: tuple[tuple[str, str], ...] | None,
    ) -> AsrJob:
        assert job_id == self.job.job_id
        assert text is None
        if expected_revision != self.job.transcript_revision:
            raise TranscriptRevisionConflictError("Transcript revision is stale")
        assert segment_edits is not None
        edited = dict(segment_edits)
        segments = tuple(replace(segment, text=edited[segment.segment_id]) for segment in self.job.segments)
        self.job = replace(
            self.job,
            text=" ".join(segment.text for segment in segments),
            segments=segments,
            transcript_revision=self.job.transcript_revision + 1,
            transcript_updated_at="2026-08-24T11:00:00+00:00",
        )
        return self.job


def test_transcript_revision_and_export_routes() -> None:
    jobs = TranscriptJobs()
    client = _client(jobs)

    revised = client.patch(
        f"/api/v1/asr/jobs/{jobs.job.job_id}/transcript",
        json={
            "expected_revision": 0,
            "segments": [
                {"segment_id": "segment-0001", "text": "Corrected line."},
                {"segment_id": "segment-0002", "text": "Second line."},
            ],
        },
    )

    assert revised.status_code == 200
    assert revised.json()["transcript_revision"] == 1
    assert revised.json()["raw_text"] == "Raw line. Second line."
    assert revised.json()["text"] == "Corrected line. Second line."

    exported = client.get(f"/api/v1/asr/jobs/{jobs.job.job_id}/exports/srt")
    assert exported.status_code == 200
    assert exported.headers["content-type"] == "application/x-subrip; charset=utf-8"
    assert exported.headers["content-disposition"] == 'attachment; filename="transcript-12345678.srt"'
    assert "00:00:00,100 --> 00:00:01,000" in exported.text

    stale = client.patch(
        f"/api/v1/asr/jobs/{jobs.job.job_id}/transcript",
        json={
            "expected_revision": 0,
            "segments": [
                {"segment_id": "segment-0001", "text": "Stale line."},
                {"segment_id": "segment-0002", "text": "Second line."},
            ],
        },
    )
    assert stale.status_code == 409
    assert stale.json()["error"] == "transcript_revision_conflict"


def _client(jobs: TranscriptJobs) -> TestClient:
    app = FastAPI()
    app.state.container = SimpleNamespace(asr_jobs=jobs)
    register_exception_handlers(app)
    app.include_router(router, prefix="/api/v1/asr")
    return TestClient(app)


def _job() -> AsrJob:
    segments = (
        TranscriptSegment("segment-0001", 0.1, 1.0, "Raw line."),
        TranscriptSegment("segment-0002", 1.0, 2.0, "Second line."),
    )
    return AsrJob(
        job_id="12345678-abcd-4000-9000-123456789abc",
        status="succeeded",
        filename="source.wav",
        language="en",
        created_at="2026-08-24T10:00:00+00:00",
        started_at="2026-08-24T10:00:01+00:00",
        completed_at="2026-08-24T10:00:03+00:00",
        error=None,
        attempt=1,
        max_attempts=1,
        cancel_requested=False,
        failed_reason=None,
        progress_stage="succeeded",
        stage_started_at="2026-08-24T10:00:03+00:00",
        idempotency_key_hash=None,
        request_fingerprint=None,
        input_path=Path("input.wav"),
        text="Raw line. Second line.",
        sample_rate=16000,
        duration_seconds=2.0,
        raw_text="Raw line. Second line.",
        raw_segments=segments,
        segments=segments,
        timing_status="available",
        transcript_revision=0,
        transcript_updated_at=None,
    )
