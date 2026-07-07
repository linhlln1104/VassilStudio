from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool

from vvoice.app.system.schemas import (
    HealthResponse,
    ModelStatusResponse,
    WarmupAllResponse,
    WarmupResponse,
)
from vvoice.shared.security.auth import require_api_key


router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health(request: Request):
    settings = request.app.state.container.settings
    container = request.app.state.container
    return {
        "status": "ok",
        "asr_enabled": settings.asr.enabled,
        "tts_enabled": settings.tts.enabled,
        "provider": settings.runtime.provider,
        "asr_loaded": container.asr.is_loaded,
        "tts_loaded": container.tts.is_loaded,
    }


@router.get(
    "/model-status",
    response_model=ModelStatusResponse,
    dependencies=[Depends(require_api_key)],
)
async def model_status(request: Request):
    container = request.app.state.container
    settings = request.app.state.container.settings
    checks = {}
    for language, model in settings.asr.models.items():
        prefix = f"asr_{language}"
        checks.update(
            {
                f"{prefix}_encoder": model.encoder.exists(),
                f"{prefix}_decoder": model.decoder.exists(),
                f"{prefix}_joiner": model.joiner.exists(),
                f"{prefix}_tokens": model.tokens.exists(),
            }
        )
    for language, model in settings.tts.models.items():
        prefix = f"tts_{language}"
        checks.update(
            {
                f"{prefix}_encoder": model.encoder.exists(),
                f"{prefix}_decoder": model.decoder.exists(),
                f"{prefix}_vocoder": model.vocoder.exists(),
                f"{prefix}_tokens": model.tokens.exists(),
                f"{prefix}_lexicon": model.lexicon.exists(),
                f"{prefix}_data_dir": model.data_dir.exists(),
            }
        )
    return {
        "ready": all(checks.values()),
        "checks": checks,
        "runtime": {
            "provider": settings.runtime.provider,
            "num_threads": settings.runtime.num_threads,
            "debug": settings.runtime.debug,
            "warmup_on_startup": settings.runtime.warmup_on_startup,
            "asr_job_workers": settings.jobs.asr_max_workers,
            "tts_job_workers": settings.jobs.tts_max_workers,
            "asr_loaded": container.asr.is_loaded,
            "tts_loaded": container.tts.is_loaded,
            "asr_configured_languages": list(container.asr.configured_languages),
            "asr_loaded_languages": list(container.asr.loaded_languages),
            "tts_configured_languages": list(container.tts.configured_languages),
            "tts_loaded_languages": list(container.tts.loaded_languages),
        },
    }


@router.post(
    "/warmup/asr",
    response_model=WarmupResponse,
    dependencies=[Depends(require_api_key)],
)
async def warmup_asr(request: Request):
    container = request.app.state.container
    await run_in_threadpool(container.asr.warmup)
    return {
        "loaded": container.asr.is_loaded,
        "loaded_languages": list(container.asr.loaded_languages),
    }


@router.post(
    "/warmup/tts",
    response_model=WarmupResponse,
    dependencies=[Depends(require_api_key)],
)
async def warmup_tts(request: Request):
    container = request.app.state.container
    await run_in_threadpool(container.tts.warmup)
    return {
        "loaded": container.tts.is_loaded,
        "loaded_languages": list(container.tts.loaded_languages),
    }


@router.post(
    "/warmup",
    response_model=WarmupAllResponse,
    dependencies=[Depends(require_api_key)],
)
async def warmup_all(request: Request):
    container = request.app.state.container
    await run_in_threadpool(container.asr.warmup_all)
    await run_in_threadpool(container.tts.warmup_all)
    return {
        "asr_loaded": container.asr.is_loaded,
        "tts_loaded": container.tts.is_loaded,
        "asr_loaded_languages": list(container.asr.loaded_languages),
        "tts_loaded_languages": list(container.tts.loaded_languages),
    }
