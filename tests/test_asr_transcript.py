import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from vvoice.core.errors import TranscriptNotReadyError
from vvoice.domains.asr.exports import render_transcript_export
from vvoice.domains.asr.jobs import AsrJob
from vvoice.domains.asr.transcript import TranscriptSegment, timed_segments_from_result


def test_token_timestamps_create_real_review_segments() -> None:
    result = SimpleNamespace(
        text="HELLO WORLD. NEXT TAKE",
        tokens=["▁HELLO", "▁WORLD", ".", "▁NEXT", "▁TAKE"],
        timestamps=[0.2, 0.5, 0.7, 2.0, 2.3],
        segment_texts=[],
        segment_timestamps=[],
        segment_durations=[],
    )

    segments = timed_segments_from_result(
        result,
        text=result.text,
        audio_duration_seconds=3.0,
    )

    assert segments == (
        TranscriptSegment("segment-0001", 0.2, 2.0, "HELLO WORLD."),
        TranscriptSegment("segment-0002", 2.0, 3.0, "NEXT TAKE"),
    )


def test_missing_or_invalid_timestamps_stay_unavailable() -> None:
    missing = SimpleNamespace(
        tokens=["▁HELLO"],
        timestamps=[],
        segment_texts=[],
        segment_timestamps=[],
        segment_durations=[],
    )
    invalid = SimpleNamespace(
        tokens=["▁HELLO"],
        timestamps=[2.0],
        segment_texts=[],
        segment_timestamps=[],
        segment_durations=[],
    )

    assert timed_segments_from_result(missing, text="HELLO", audio_duration_seconds=1.0) == ()
    assert timed_segments_from_result(invalid, text="HELLO", audio_duration_seconds=1.0) == ()


def test_transcript_exports_are_deterministic_and_preserve_raw_output() -> None:
    job = _completed_job()

    txt = render_transcript_export(job, "txt")
    srt = render_transcript_export(job, "srt")
    vtt = render_transcript_export(job, "vtt")
    structured = render_transcript_export(job, "json")

    assert txt.filename == "transcript-12345678.txt"
    assert txt.content == "Corrected line. Next line.\n"
    assert srt.content == (
        "1\n00:00:00,125 --> 00:00:01,500\nCorrected line.\n\n"
        "2\n00:00:01,500 --> 00:00:02,750\nNext line.\n"
    )
    assert vtt.content.startswith("WEBVTT\n\n00:00:00.125 --> 00:00:01.500")
    payload = json.loads(structured.content)
    assert payload["schema_version"] == "vassil.transcript.v1"
    assert payload["transcript"]["revision"] == 1
    assert payload["transcript"]["text"] == "Corrected line. Next line."
    assert payload["transcript"]["raw"]["text"] == "Raw line. Next line."


def test_subtitle_export_requires_model_timing() -> None:
    job = replace(_completed_job(), segments=(), timing_status="unavailable")

    with pytest.raises(TranscriptNotReadyError, match="Timed segments"):
        render_transcript_export(job, "srt")


def _completed_job() -> AsrJob:
    raw_segments = (
        TranscriptSegment("segment-0001", 0.125, 1.5, "Raw line."),
        TranscriptSegment("segment-0002", 1.5, 2.75, "Next line."),
    )
    return AsrJob(
        job_id="12345678-abcd-4000-9000-123456789abc",
        status="succeeded",
        filename="interview.wav",
        language="en",
        created_at="2026-08-24T10:00:00+00:00",
        started_at="2026-08-24T10:00:01+00:00",
        completed_at="2026-08-24T10:00:04+00:00",
        error=None,
        attempt=1,
        max_attempts=1,
        cancel_requested=False,
        failed_reason=None,
        progress_stage="succeeded",
        stage_started_at="2026-08-24T10:00:04+00:00",
        idempotency_key_hash=None,
        request_fingerprint=None,
        input_path=Path("input.wav"),
        text="Corrected line. Next line.",
        sample_rate=16000,
        duration_seconds=2.75,
        raw_text="Raw line. Next line.",
        raw_segments=raw_segments,
        segments=(
            replace(raw_segments[0], text="Corrected line."),
            raw_segments[1],
        ),
        timing_status="available",
        transcript_revision=1,
        transcript_updated_at="2026-08-24T10:05:00+00:00",
    )
