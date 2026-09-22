from __future__ import annotations

from fastapi import APIRouter, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, Response

from vvoice.core.errors import public_job_error
from vvoice.domains.tts.jobs import TtsJob
from vvoice.domains.tts.schemas import (
    TtsJobCleanupResponse,
    TtsJobDeleteResponse,
    TtsJobResponse,
)
from vvoice.domains.tts.parameters import validate_tts_parameters
from vvoice.domains.tts.service import GeneratedSpeech
from vvoice.shared.audio.io import encode_wav, load_audio_bytes
from vvoice.shared.language import DEFAULT_LANGUAGE, normalize_language
from vvoice.shared.jobs.integrity import CANCELLATION_MODE, IDEMPOTENCY_KEY_HEADER
from vvoice.shared.validation import read_audio_upload, validate_text_field


router = APIRouter()


@router.post("/synthesize")
async def synthesize(
    request: Request,
    text: str = Form(...),
    reference_text: str = Form(...),
    reference_audio: UploadFile = File(...),
    language: str = Form(default=DEFAULT_LANGUAGE),
    num_steps: int | None = Form(default=None),
    speed: float | None = Form(default=None),
):
    container = request.app.state.container
    validate_tts_parameters(num_steps, speed)
    normalized_text = validate_text_field(
        text,
        field_name="text",
        max_chars=container.settings.limits.max_tts_text_chars,
    )
    normalized_reference_text = validate_text_field(
        reference_text,
        field_name="reference_text",
        max_chars=container.settings.limits.max_reference_text_chars,
    )
    normalized_language = normalize_language(language)
    data = await read_audio_upload(
        reference_audio,
        max_bytes=container.settings.limits.max_upload_bytes,
        field_name="reference_audio",
    )
    samples, sample_rate = await run_in_threadpool(
        load_audio_bytes,
        data,
        target_sample_rate=container.tts.sample_rate_for(normalized_language),
    )
    speech = await run_in_threadpool(
        container.tts.synthesize,
        text=normalized_text,
        reference_audio=samples,
        reference_sample_rate=sample_rate,
        reference_text=normalized_reference_text,
        language=normalized_language,
        num_steps=num_steps,
        speed=speed,
    )
    return await run_in_threadpool(_wav_response, speech)


@router.post("/synthesize/voices/{voice_id}")
async def synthesize_with_voice(
    request: Request,
    voice_id: str,
    text: str = Form(...),
    language: str | None = Form(default=None),
    num_steps: int | None = Form(default=None),
    speed: float | None = Form(default=None),
):
    container = request.app.state.container
    validate_tts_parameters(num_steps, speed)
    normalized_text = validate_text_field(
        text,
        field_name="text",
        max_chars=container.settings.limits.max_tts_text_chars,
    )
    profile, audio_bytes = await run_in_threadpool(container.voices.snapshot, voice_id)
    normalized_language = normalize_language(language or profile.language)
    samples, sample_rate = await run_in_threadpool(
        load_audio_bytes,
        audio_bytes,
        target_sample_rate=container.tts.sample_rate_for(normalized_language),
    )
    speech = await run_in_threadpool(
        container.tts.synthesize,
        text=normalized_text,
        reference_audio=samples,
        reference_sample_rate=sample_rate,
        reference_text=profile.reference_text,
        language=normalized_language,
        num_steps=num_steps,
        speed=speed,
    )
    return await run_in_threadpool(_wav_response, speech)


@router.post(
    "/jobs/voices/{voice_id}",
    response_model=TtsJobResponse,
    status_code=202,
    responses={
        409: {"description": "Idempotency key conflicts with an earlier request"},
        429: {"description": "Job queue is full"},
    },
)
async def create_tts_job_with_voice(
    request: Request,
    voice_id: str,
    text: str = Form(...),
    language: str | None = Form(default=None),
    num_steps: int | None = Form(default=None),
    speed: float | None = Form(default=None),
    idempotency_key: str | None = Header(default=None, alias=IDEMPOTENCY_KEY_HEADER),
):
    container = request.app.state.container
    validate_tts_parameters(num_steps, speed)
    job = await run_in_threadpool(
        container.tts_jobs.create_from_voice,
        voice_id=voice_id,
        text=text,
        language=language,
        num_steps=num_steps,
        speed=speed,
        idempotency_key=idempotency_key,
    )
    return _job_response(job)


@router.get("/jobs", response_model=list[TtsJobResponse])
def list_tts_jobs(request: Request):
    container = request.app.state.container
    return [_job_response(job) for job in container.tts_jobs.list()]


@router.delete("/jobs", response_model=TtsJobCleanupResponse)
def cleanup_tts_jobs(
    request: Request,
    max_age_seconds: int | None = Query(default=None, ge=0),
):
    container = request.app.state.container
    deleted = container.tts_jobs.cleanup(max_age_seconds=max_age_seconds)
    return {"deleted": len(deleted), "job_ids": deleted}


@router.get("/jobs/{job_id}", response_model=TtsJobResponse)
def get_tts_job(request: Request, job_id: str):
    container = request.app.state.container
    return _job_response(container.tts_jobs.get(job_id))


@router.post("/jobs/{job_id}/cancel", response_model=TtsJobResponse)
def cancel_tts_job(request: Request, job_id: str):
    container = request.app.state.container
    return _job_response(container.tts_jobs.cancel(job_id))


@router.get("/jobs/{job_id}/audio")
def get_tts_job_audio(request: Request, job_id: str):
    container = request.app.state.container
    job = container.tts_jobs.get(job_id)
    if job.status != "succeeded" or not job.output_path or not job.output_path.exists():
        raise HTTPException(status_code=409, detail=f"TTS job is not ready: {job.status}")

    return FileResponse(
        job.output_path,
        media_type="audio/wav",
        filename=f"{job.job_id}.wav",
    )


@router.delete("/jobs/{job_id}", response_model=TtsJobDeleteResponse)
def delete_tts_job(request: Request, job_id: str):
    container = request.app.state.container
    container.tts_jobs.delete(job_id)
    return {"deleted": True, "job_id": job_id}


def _wav_response(speech: GeneratedSpeech) -> Response:
    wav = encode_wav(speech.samples, speech.sample_rate)
    return Response(
        content=wav,
        media_type="audio/wav",
        headers={
            "X-Vassil-Sample-Rate": str(speech.sample_rate),
            "X-Vassil-Duration-Seconds": f"{speech.duration_seconds:.3f}",
            "X-VVoice-Sample-Rate": str(speech.sample_rate),
            "X-VVoice-Duration-Seconds": f"{speech.duration_seconds:.3f}",
        },
    )


def _job_response(job: TtsJob) -> dict:
    audio_url = f"/api/v1/tts/jobs/{job.job_id}/audio" if job.status == "succeeded" else None
    return {
        "job_id": job.job_id,
        "status": job.status,
        "voice_id": job.voice_id,
        "language": normalize_language(job.language),
        "text": job.text,
        "num_steps": job.num_steps,
        "speed": job.speed,
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
        "sample_rate": job.sample_rate,
        "duration_seconds": job.duration_seconds,
        "audio_url": audio_url,
    }
