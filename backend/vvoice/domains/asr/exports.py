from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from vvoice.core.errors import TranscriptNotReadyError
from vvoice.domains.asr.transcript import TranscriptSegment, segment_to_dict

if TYPE_CHECKING:
    from vvoice.domains.asr.jobs import AsrJob


TranscriptExportFormat = Literal["txt", "srt", "vtt", "json"]


@dataclass(frozen=True)
class TranscriptExport:
    content: str
    filename: str
    media_type: str


def render_transcript_export(job: AsrJob, export_format: TranscriptExportFormat) -> TranscriptExport:
    if job.status != "succeeded" or not job.text:
        raise TranscriptNotReadyError("Transcript is not ready for export")

    filename = f"transcript-{_compact_job_id(job.job_id)}.{export_format}"
    if export_format == "txt":
        return TranscriptExport(
            content=f"{job.text.rstrip()}\n",
            filename=filename,
            media_type="text/plain; charset=utf-8",
        )

    if export_format in {"srt", "vtt"} and not job.segments:
        raise TranscriptNotReadyError(
            "Timed segments are unavailable for this transcript; export TXT or JSON instead"
        )

    if export_format == "srt":
        return TranscriptExport(
            content=_render_srt(job.segments),
            filename=filename,
            media_type="application/x-subrip; charset=utf-8",
        )
    if export_format == "vtt":
        return TranscriptExport(
            content=_render_vtt(job.segments),
            filename=filename,
            media_type="text/vtt; charset=utf-8",
        )

    payload = {
        "schema_version": "vassil.transcript.v1",
        "job_id": job.job_id,
        "source": {
            "filename": job.filename,
            "language": job.language,
            "duration_seconds": job.duration_seconds,
            "sample_rate": job.sample_rate,
        },
        "transcript": {
            "text": job.text,
            "segments": [segment_to_dict(segment) for segment in job.segments],
            "timing_status": job.timing_status,
            "revision": job.transcript_revision,
            "edited": job.transcript_revision > 0,
            "updated_at": job.transcript_updated_at,
            "raw": {
                "text": job.raw_text,
                "segments": [segment_to_dict(segment) for segment in job.raw_segments],
            },
        },
    }
    return TranscriptExport(
        content=f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n",
        filename=filename,
        media_type="application/json; charset=utf-8",
    )


def _render_srt(segments: tuple[TranscriptSegment, ...]) -> str:
    blocks = [
        f"{index}\n{_timestamp(segment.start_seconds, ',')} --> "
        f"{_timestamp(segment.end_seconds, ',')}\n{segment.text}"
        for index, segment in enumerate(segments, start=1)
    ]
    return "\n\n".join(blocks) + "\n"


def _render_vtt(segments: tuple[TranscriptSegment, ...]) -> str:
    blocks = [
        f"{_timestamp(segment.start_seconds, '.')} --> "
        f"{_timestamp(segment.end_seconds, '.')}\n{segment.text}"
        for segment in segments
    ]
    return "WEBVTT\n\n" + "\n\n".join(blocks) + "\n"


def _timestamp(seconds: float, millisecond_separator: str) -> str:
    total_milliseconds = max(0, round(seconds * 1000))
    hours, remainder = divmod(total_milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, milliseconds = divmod(remainder, 1000)
    return (
        f"{hours:02d}:{minutes:02d}:{whole_seconds:02d}"
        f"{millisecond_separator}{milliseconds:03d}"
    )


def _compact_job_id(job_id: str) -> str:
    compact = re.sub(r"[^A-Za-z0-9]", "", job_id)[:8]
    return compact or "export"
