from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from vvoice.core.errors import VVoiceError, public_job_error
from vvoice.domains.tts.jobs import TtsJob
from vvoice.domains.tts.schemas import (
    TtsJobCleanupResponse,
    TtsJobDeleteResponse,
    TtsJobResponse,
    TtsModelCatalogResponse,
)
from vvoice.domains.tts.parameters import validate_tts_parameters
from vvoice.domains.tts.service import GeneratedSpeech
from vvoice.shared.audio.io import encode_wav, load_audio_bytes
from vvoice.shared.language import DEFAULT_LANGUAGE, normalize_language
from vvoice.shared.jobs.integrity import CANCELLATION_MODE, IDEMPOTENCY_KEY_HEADER
from vvoice.shared.validation import read_audio_upload, validate_text_field
from vvoice.shared.security.auth import require_domain_scope, require_scope


router = APIRouter(dependencies=[Depends(require_domain_scope("tts"))])
_WAV_RESPONSES = {200: {"content": {"audio/wav": {"schema": {"type": "string", "format": "binary"}}}}}


class ModelImportRequest(BaseModel):
    model_id: str = Field(min_length=1, max_length=120)
    engine: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=200)
    languages: list[str] = Field(min_length=1)
    sample_rate: int = Field(gt=0)
    options: dict = Field(default_factory=dict)


class ModelRollbackRequest(BaseModel):
    version: str = Field(min_length=1, max_length=128)


@router.get("/models", response_model=TtsModelCatalogResponse)
def list_tts_models(request: Request):
    return request.app.state.container.tts.model_catalog()


@router.post("/synthesize", response_class=Response, responses=_WAV_RESPONSES)
async def synthesize(
    request: Request,
    text: str = Form(...),
    reference_text: str = Form(...),
    reference_audio: UploadFile = File(...),
    language: str = Form(default=DEFAULT_LANGUAGE),
    model_id: str | None = Form(default=None),
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
    resolved_model_id = container.tts.validate_request(
        language=normalized_language, model_id=model_id, num_steps=num_steps, speed=speed,
    )
    data = await read_audio_upload(
        reference_audio,
        max_bytes=container.settings.limits.max_upload_bytes,
        field_name="reference_audio",
    )
    samples, sample_rate = await run_in_threadpool(
        load_audio_bytes,
        data,
        target_sample_rate=container.tts.sample_rate_for(
            normalized_language, model_id=resolved_model_id,
        ),
    )
    speech = await run_in_threadpool(
        container.tts.synthesize,
        text=normalized_text,
        reference_audio=samples,
        reference_sample_rate=sample_rate,
        reference_text=normalized_reference_text,
        language=normalized_language,
        model_id=resolved_model_id,
        num_steps=num_steps,
        speed=speed,
    )
    return await run_in_threadpool(_wav_response, speech)


@router.post("/synthesize/voices/{voice_id}", response_class=Response, responses=_WAV_RESPONSES)
async def synthesize_with_voice(
    request: Request,
    voice_id: str,
    text: str = Form(...),
    language: str | None = Form(default=None),
    model_id: str | None = Form(default=None),
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
    resolved_model_id = container.tts.validate_request(
        language=normalized_language, model_id=model_id, num_steps=num_steps, speed=speed,
    )
    samples, sample_rate = await run_in_threadpool(
        load_audio_bytes,
        audio_bytes,
        target_sample_rate=container.tts.sample_rate_for(
            normalized_language, model_id=resolved_model_id,
        ),
    )
    speech = await run_in_threadpool(
        container.tts.synthesize,
        text=normalized_text,
        reference_audio=samples,
        reference_sample_rate=sample_rate,
        reference_text=profile.reference_text,
        language=normalized_language,
        model_id=resolved_model_id,
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
    model_id: str | None = Form(default=None),
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
        model_id=model_id,
        num_steps=num_steps,
        speed=speed,
        idempotency_key=idempotency_key,
    )
    return _job_response(job)


@router.get("/jobs", response_model=list[TtsJobResponse])
def list_tts_jobs(
    request: Request, limit: int | None = Query(default=None, ge=1, le=500),
    offset: int = Query(default=0, ge=0), status: str | None = None, model_id: str | None = None,
):
    container = request.app.state.container
    principal = request.state.principal
    if not principal.is_admin:
        # Apply ownership and project ACL before pagination, including imported
        # legacy records with no actor (those are visible to administrators only).
        jobs = [job for job in container.tts_jobs.list()
                if (status is None or job.status == status)
                and (model_id is None or job.model_id == model_id)
                and _job_is_visible(request, job)]
        jobs = jobs[offset:offset + limit] if limit is not None else jobs[offset:]
    elif limit is None and offset == 0 and status is None and model_id is None:
        jobs = container.tts_jobs.list()
    else:
        jobs = container.tts_jobs.list(limit=limit, offset=offset, status=status, model_id=model_id)
    return [_job_response(job) for job in jobs]


@router.delete("/jobs", response_model=TtsJobCleanupResponse)
def cleanup_tts_jobs(
    request: Request,
    max_age_seconds: int | None = Query(default=None, ge=0),
):
    container = request.app.state.container
    if request.state.principal.is_admin:
        deleted = container.tts_jobs.cleanup(max_age_seconds=max_age_seconds)
    else:
        cutoff = (datetime.now(UTC) - timedelta(seconds=max_age_seconds)
                  if max_age_seconds is not None else None)
        deleted = []
        for job in container.tts_jobs.list():
            if job.status not in {"succeeded", "failed", "cancelled"} or not _job_is_visible(request, job, write=True):
                continue
            if cutoff and datetime.fromisoformat((job.completed_at or job.created_at).replace("Z", "+00:00")) > cutoff:
                continue
            container.tts_jobs.delete(job.job_id)
            deleted.append(job.job_id)
    return {"deleted": len(deleted), "job_ids": deleted}


@router.get("/jobs/{job_id}", response_model=TtsJobResponse)
def get_tts_job(request: Request, job_id: str):
    container = request.app.state.container
    job = container.tts_jobs.get(job_id)
    _assert_job_access(request, job)
    return _job_response(job)


@router.post("/jobs/{job_id}/cancel", response_model=TtsJobResponse)
def cancel_tts_job(request: Request, job_id: str):
    container = request.app.state.container
    _assert_job_access(request, container.tts_jobs.get(job_id), write=True)
    return _job_response(container.tts_jobs.cancel(job_id))


@router.get("/jobs/{job_id}/audio", response_class=FileResponse, responses=_WAV_RESPONSES)
def get_tts_job_audio(request: Request, job_id: str):
    container = request.app.state.container
    job = container.tts_jobs.get(job_id)
    _assert_job_access(request, job)
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
    _assert_job_access(request, container.tts_jobs.get(job_id), write=True)
    container.tts_jobs.delete(job_id)
    return {"deleted": True, "job_id": job_id}


@router.post("/jobs/{job_id}/retry", response_model=TtsJobResponse, status_code=202,
             responses={409: {"description": "Job is not terminal or idempotency key conflicts"},
                        429: {"description": "Job queue is full"}})
def retry_tts_job(request: Request, job_id: str,
                  idempotency_key: str | None = Header(default=None, alias=IDEMPOTENCY_KEY_HEADER)):
    job = request.app.state.container.tts_jobs.get(job_id)
    _assert_job_access(request, job, write=True)
    if _project_id(job):
        raise HTTPException(409, "This job belongs to a project. Create a new take or retry its batch to preserve production history.")
    return _job_response(request.app.state.container.tts_jobs.retry(job_id, idempotency_key=idempotency_key))


@router.get("/models/deployments", dependencies=[Depends(require_scope("models:read"))])
def model_deployments(request: Request):
    return request.app.state.container.tts.deployment_versions()


@router.post("/models/import", response_model=TtsModelCatalogResponse,
             dependencies=[Depends(require_scope("models:manage"))])
def import_model_profile(request: Request, payload: ModelImportRequest):
    tts = request.app.state.container.tts
    tts.import_profile(payload.model_dump())
    return tts.model_catalog()


@router.post("/models/{model_id}/rollback", response_model=TtsModelCatalogResponse,
             dependencies=[Depends(require_scope("models:manage"))])
def rollback_model(request: Request, model_id: str, payload: ModelRollbackRequest):
    tts = request.app.state.container.tts
    tts.rollback(model_id, payload.version)
    return tts.model_catalog()


@router.post("/models/{model_id}/warmup", response_model=TtsModelCatalogResponse,
             dependencies=[Depends(require_scope("models:manage"))])
def warm_model(request: Request, model_id: str):
    tts = request.app.state.container.tts
    tts.warmup(model_id=model_id)
    return tts.model_catalog()


@router.post("/models/{model_id}/unload", response_model=TtsModelCatalogResponse,
             dependencies=[Depends(require_scope("models:manage"))])
def unload_model(request: Request, model_id: str):
    tts = request.app.state.container.tts
    tts.unload(model_id)
    return tts.model_catalog()


@router.post("/models/{model_id}/enable", response_model=TtsModelCatalogResponse,
             dependencies=[Depends(require_scope("models:manage"))])
def enable_model(request: Request, model_id: str):
    tts = request.app.state.container.tts
    tts.set_enabled(model_id, True)
    return tts.model_catalog()


@router.post("/models/{model_id}/disable", response_model=TtsModelCatalogResponse,
             dependencies=[Depends(require_scope("models:manage"))])
def disable_model(request: Request, model_id: str):
    tts = request.app.state.container.tts
    tts.set_enabled(model_id, False)
    return tts.model_catalog()


@router.post("/models/{model_id}/activate", response_model=TtsModelCatalogResponse,
             dependencies=[Depends(require_scope("models:manage"))])
def activate_model(request: Request, model_id: str):
    tts = request.app.state.container.tts
    tts.activate(model_id)
    return tts.model_catalog()


def _project_id(job: TtsJob) -> str | None:
    provenance = getattr(job, "provenance", {}) or {}
    production = provenance.get("production", {})
    return production.get("project_id") or provenance.get("project_id")


def _assert_job_access(request: Request, job: TtsJob, *, write: bool = False) -> None:
    principal = getattr(request.state, "principal", None)
    if principal is None:
        raise HTTPException(401, "Authentication required")
    if principal.is_admin:
        return
    project_id = _project_id(job)
    if project_id:
        if not principal.has_scope("production:write" if write else "production:read"):
            raise HTTPException(404, "TTS job not found")
        production = getattr(request.app.state.container, "production", None)
        if production is None:
            raise HTTPException(404, "TTS job not found")
        try:
            production.assert_project_access(project_id, principal, action="write" if write else "read")
        except VVoiceError as exc:
            raise HTTPException(404, "TTS job not found") from exc
        return
    if getattr(job, "actor_id", None) != principal.principal_id:
        raise HTTPException(404, "TTS job not found")


def _job_is_visible(request: Request, job: TtsJob, *, write: bool = False) -> bool:
    try:
        _assert_job_access(request, job, write=write)
        return True
    except HTTPException as exc:
        if exc.status_code in {403, 404}:
            return False
        raise


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
        "model_id": job.model_id,
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
        "actor_id": getattr(job, "actor_id", None),
        "request_id": getattr(job, "request_id", None),
        "provenance": getattr(job, "provenance", {}),
        "recovery_count": getattr(job, "recovery_count", 0),
    }
