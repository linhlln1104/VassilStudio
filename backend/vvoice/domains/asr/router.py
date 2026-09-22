from __future__ import annotations

from fastapi import APIRouter, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, Response

from vvoice.core.errors import public_job_error
from vvoice.domains.asr.exports import TranscriptExportFormat, render_transcript_export
from vvoice.domains.asr.jobs import AsrJob
from vvoice.domains.asr.schemas import (
    AsrJobCleanupResponse,
    AsrJobDeleteResponse,
    AsrJobResponse,
    TranscriptRevisionRequest,
    TranscriptionResponse,
)
from vvoice.domains.asr.transcript import segment_to_dict
from vvoice.shared.audio.io import duration_seconds, load_audio_bytes
from vvoice.shared.language import DEFAULT_LANGUAGE, normalize_language
from vvoice.shared.jobs.integrity import CANCELLATION_MODE, IDEMPOTENCY_KEY_HEADER
from vvoice.shared.validation import read_audio_upload, safe_display_filename


router = APIRouter()


@router.post("/transcribe", response_model=TranscriptionResponse)
async def transcribe_audio(
    request: Request,
    audio: UploadFile = File(...),
    language: str = Form(default=DEFAULT_LANGUAGE),
):
    container = request.app.state.container
    normalized_language = normalize_language(language)
    data = await read_audio_upload(
        audio,
        max_bytes=container.settings.limits.max_upload_bytes,
        field_name="audio",
    )
    samples, sample_rate = await run_in_threadpool(
        load_audio_bytes,
        data,
        target_sample_rate=container.asr.sample_rate_for(normalized_language),
    )
    result = await run_in_threadpool(
        container.asr.transcribe,
        samples,
        sample_rate,
        normalized_language,
    )
    return {
        "text": result.text,
        "sample_rate": result.sample_rate,
        "duration_seconds": duration_seconds(samples, sample_rate),
        "timing_status": "available" if result.segments else "unavailable",
        "segments": [segment_to_dict(segment) for segment in result.segments],
    }


@router.post(
    "/jobs",
    response_model=AsrJobResponse,
    status_code=202,
    responses={
        409: {"description": "Idempotency key conflicts with an earlier request"},
        429: {"description": "Job queue is full"},
        413: {"description": "Decoded audio exceeds processing limits"},
    },
)
async def create_asr_job(
    request: Request,
    audio: UploadFile = File(...),
    language: str = Form(default=DEFAULT_LANGUAGE),
    idempotency_key: str | None = Header(default=None, alias=IDEMPOTENCY_KEY_HEADER),
):
    container = request.app.state.container
    data = await read_audio_upload(
        audio,
        max_bytes=container.settings.limits.max_upload_bytes,
        field_name="audio",
    )
    job = await run_in_threadpool(
        container.asr_jobs.create_from_audio,
        audio_bytes=data,
        filename=safe_display_filename(audio.filename),
        language=normalize_language(language),
        idempotency_key=idempotency_key,
    )
    return _job_response(job)


@router.get("/jobs", response_model=list[AsrJobResponse])
def list_asr_jobs(request: Request):
    container = request.app.state.container
    return [_job_response(job) for job in container.asr_jobs.list()]


@router.delete("/jobs", response_model=AsrJobCleanupResponse)
def cleanup_asr_jobs(
    request: Request,
    max_age_seconds: int | None = Query(default=None, ge=0),
):
    container = request.app.state.container
    deleted = container.asr_jobs.cleanup(max_age_seconds=max_age_seconds)
    return {"deleted": len(deleted), "job_ids": deleted}


@router.get("/jobs/{job_id}", response_model=AsrJobResponse)
def get_asr_job(request: Request, job_id: str):
    container = request.app.state.container
    return _job_response(container.asr_jobs.get(job_id))


@router.post("/jobs/{job_id}/cancel", response_model=AsrJobResponse)
def cancel_asr_job(request: Request, job_id: str):
    container = request.app.state.container
    return _job_response(container.asr_jobs.cancel(job_id))


@router.patch(
    "/jobs/{job_id}/transcript",
    response_model=AsrJobResponse,
    responses={409: {"description": "Transcript is not ready or the revision is stale"}},
)
def revise_asr_transcript(
    request: Request,
    job_id: str,
    revision: TranscriptRevisionRequest,
):
    container = request.app.state.container
    segment_edits = (
        tuple((segment.segment_id, segment.text) for segment in revision.segments)
        if revision.segments is not None
        else None
    )
    job = container.asr_jobs.revise_transcript(
        job_id,
        expected_revision=revision.expected_revision,
        text=revision.text,
        segment_edits=segment_edits,
    )
    return _job_response(job)


@router.get(
    "/jobs/{job_id}/exports/{export_format}",
    responses={409: {"description": "Transcript or timed segments are not ready"}},
)
def export_asr_transcript(
    request: Request,
    job_id: str,
    export_format: TranscriptExportFormat,
):
    container = request.app.state.container
    export = render_transcript_export(container.asr_jobs.get(job_id), export_format)
    return Response(
        content=export.content,
        media_type=export.media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{export.filename}"',
            "Cache-Control": "private, no-store",
        },
    )


@router.get("/jobs/{job_id}/audio")
def get_asr_job_audio(request: Request, job_id: str):
    container = request.app.state.container
    job = container.asr_jobs.get(job_id)
    if not job.input_path or not job.input_path.exists():
        raise HTTPException(status_code=409, detail="ASR job input audio is not available")

    return FileResponse(
        job.input_path,
        media_type="audio/wav",
        filename=f"{job.job_id}-input.wav",
    )


@router.delete("/jobs/{job_id}", response_model=AsrJobDeleteResponse)
def delete_asr_job(request: Request, job_id: str):
    container = request.app.state.container
    container.asr_jobs.delete(job_id)
    return {"deleted": True, "job_id": job_id}


def _job_response(job: AsrJob) -> dict:
    return {
        "job_id": job.job_id,
        "status": job.status,
        "filename": job.filename,
        "language": job.language,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
        "error": public_job_error(job.error, job.failed_reason),
        "attempt": job.attempt,
        "max_attempts": job.max_attempts,
        "cancel_requested": job.cancel_requested,
        "cancellation_mode": CANCELLATION_MODE,
        "failed_reason": job.failed_reason,
        "progress_stage": job.progress_stage,
        "stage_started_at": job.stage_started_at,
        "text": job.text,
        "sample_rate": job.sample_rate,
        "duration_seconds": job.duration_seconds,
        "audio_url": f"/api/v1/asr/jobs/{job.job_id}/audio" if job.input_path else None,
        "raw_text": job.raw_text,
        "raw_segments": [segment_to_dict(segment) for segment in job.raw_segments],
        "segments": [segment_to_dict(segment) for segment in job.segments],
        "timing_status": job.timing_status,
        "transcript_revision": job.transcript_revision,
        "transcript_edited": job.transcript_revision > 0,
        "transcript_updated_at": job.transcript_updated_at,
    }
