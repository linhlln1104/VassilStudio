from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from vvoice.domains.asr.jobs import AsrJob
from vvoice.domains.asr.schemas import (
    AsrJobCleanupResponse,
    AsrJobDeleteResponse,
    AsrJobResponse,
    TranscriptionResponse,
)
from vvoice.shared.audio.io import duration_seconds, load_audio_bytes
from vvoice.shared.language import DEFAULT_LANGUAGE, normalize_language
from vvoice.shared.validation import read_upload_file, safe_display_filename


router = APIRouter()


@router.post("/transcribe", response_model=TranscriptionResponse)
async def transcribe_audio(
    request: Request,
    audio: UploadFile = File(...),
    language: str = Form(default=DEFAULT_LANGUAGE),
):
    container = request.app.state.container
    normalized_language = normalize_language(language)
    data = await read_upload_file(
        audio,
        max_bytes=container.settings.limits.max_upload_bytes,
        field_name="audio",
    )
    samples, sample_rate = load_audio_bytes(
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
    }


@router.post("/jobs", response_model=AsrJobResponse, status_code=202)
async def create_asr_job(
    request: Request,
    audio: UploadFile = File(...),
    language: str = Form(default=DEFAULT_LANGUAGE),
):
    container = request.app.state.container
    data = await read_upload_file(
        audio,
        max_bytes=container.settings.limits.max_upload_bytes,
        field_name="audio",
    )
    job = container.asr_jobs.create_from_audio(
        audio_bytes=data,
        filename=safe_display_filename(audio.filename),
        language=normalize_language(language),
    )
    return _job_response(job)


@router.get("/jobs", response_model=list[AsrJobResponse])
async def list_asr_jobs(request: Request):
    container = request.app.state.container
    return [_job_response(job) for job in container.asr_jobs.list()]


@router.delete("/jobs", response_model=AsrJobCleanupResponse)
async def cleanup_asr_jobs(
    request: Request,
    max_age_seconds: int | None = Query(default=None, ge=0),
):
    container = request.app.state.container
    deleted = container.asr_jobs.cleanup(max_age_seconds=max_age_seconds)
    return {"deleted": len(deleted), "job_ids": deleted}


@router.get("/jobs/{job_id}", response_model=AsrJobResponse)
async def get_asr_job(request: Request, job_id: str):
    container = request.app.state.container
    return _job_response(container.asr_jobs.get(job_id))


@router.post("/jobs/{job_id}/cancel", response_model=AsrJobResponse)
async def cancel_asr_job(request: Request, job_id: str):
    container = request.app.state.container
    return _job_response(container.asr_jobs.cancel(job_id))


@router.get("/jobs/{job_id}/audio")
async def get_asr_job_audio(request: Request, job_id: str):
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
async def delete_asr_job(request: Request, job_id: str):
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
        "error": job.error,
        "attempt": job.attempt,
        "max_attempts": job.max_attempts,
        "cancel_requested": job.cancel_requested,
        "failed_reason": job.failed_reason,
        "text": job.text,
        "sample_rate": job.sample_rate,
        "duration_seconds": job.duration_seconds,
        "audio_url": f"/api/v1/asr/jobs/{job.job_id}/audio" if job.input_path else None,
    }
