from __future__ import annotations

from datetime import UTC, datetime
import io
import json
from pathlib import Path
import platform
import sys
import zipfile

from fastapi import APIRouter, Depends, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse

from vvoice import __version__
from vvoice.app.system.schemas import (
    DiagnosticsResponse,
    HealthResponse,
    ModelStatusResponse,
    ProbeResponse,
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
        "version": __version__,
        "asr_enabled": settings.asr.enabled,
        "tts_enabled": settings.tts.enabled,
        "provider": settings.runtime.provider,
        "asr_loaded": container.asr.is_loaded,
        "tts_loaded": container.tts.is_loaded,
    }


@router.get("/livez", response_model=ProbeResponse)
async def liveness():
    return {"status": "ok", "checks": {}}


@router.get("/readyz", response_model=ProbeResponse)
async def readiness(request: Request, response: Response):
    settings = request.app.state.container.settings
    checks = {
        **_model_file_checks(settings),
        **_storage_checks(settings),
    }
    ready = all(checks.values())
    if not ready:
        response.status_code = 503

    return {
        "status": "ready" if ready else "not_ready",
        "checks": checks,
    }


@router.get(
    "/model-status",
    response_model=ModelStatusResponse,
    dependencies=[Depends(require_api_key)],
)
async def model_status(request: Request):
    container = request.app.state.container
    settings = request.app.state.container.settings
    checks = _model_file_checks(settings)
    return {
        "ready": all(checks.values()),
        "checks": checks,
        "runtime": _runtime_status(container, settings),
    }


@router.get(
    "/diagnostics",
    response_model=DiagnosticsResponse,
    dependencies=[Depends(require_api_key)],
)
async def diagnostics(request: Request):
    container = request.app.state.container
    settings = request.app.state.container.settings
    return _diagnostics_payload(container, settings)


@router.get(
    "/diagnostics/bundle",
    dependencies=[Depends(require_api_key)],
)
async def diagnostics_bundle(request: Request):
    container = request.app.state.container
    settings = request.app.state.container.settings
    payload = _diagnostics_payload(container, settings)
    readiness_checks = {
        **_model_file_checks(settings),
        **_storage_checks(settings),
    }
    generated_at = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

    archive = io.BytesIO()
    with zipfile.ZipFile(archive, mode="w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("diagnostics.json", _json_bytes(payload))
        bundle.writestr(
            "readiness.json",
            _json_bytes(
                {
                    "status": "ready" if all(readiness_checks.values()) else "not_ready",
                    "checks": readiness_checks,
                }
            ),
        )
        bundle.writestr(
            "environment.json",
            _json_bytes(
                {
                    "python": sys.version.split()[0],
                    "platform": platform.platform(),
                }
            ),
        )
        bundle.writestr(
            "README.txt",
            (
                "VassilStudio diagnostics bundle\n"
                "This bundle contains redacted runtime, readiness, storage, and environment metadata.\n"
                "It does not include API keys, session secrets, cookies, transcripts, or audio files.\n"
            ),
        )

    archive.seek(0)
    return StreamingResponse(
        archive,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="vassilstudio-diagnostics-{generated_at}.zip"',
        },
    )


def _diagnostics_payload(container, settings) -> dict:
    return {
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "version": __version__,
        "runtime": _runtime_status(container, settings),
        "security": {
            "auth_required": getattr(settings.security, "auth_required", False),
            "api_key_auth_enabled": bool(settings.security.api_keys),
            "session_cookie_name": getattr(settings.security, "session_cookie_name", "vassil_session"),
            "session_ttl_seconds": getattr(settings.security, "session_ttl_seconds", 0),
            "secure_cookies": getattr(settings.security, "secure_cookies", False),
        },
        "storage": _diagnostic_storage_items(settings),
        "license": {
            "status": "local",
            "plan": "Local workspace",
            "billing_enabled": False,
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


def _runtime_status(container, settings) -> dict:
    return {
        "environment": settings.runtime.environment,
        "log_level": settings.runtime.log_level,
        "provider": settings.runtime.provider,
        "num_threads": settings.runtime.num_threads,
        "debug": settings.runtime.debug,
        "warmup_on_startup": settings.runtime.warmup_on_startup,
        "asr_job_workers": settings.jobs.asr_max_workers,
        "tts_job_workers": settings.jobs.tts_max_workers,
        "asr_job_max_attempts": settings.jobs.asr_max_attempts,
        "tts_job_max_attempts": settings.jobs.tts_max_attempts,
        "job_retry_backoff_seconds": settings.jobs.retry_backoff_seconds,
        "asr_loaded": container.asr.is_loaded,
        "tts_loaded": container.tts.is_loaded,
        "asr_configured_languages": list(container.asr.configured_languages),
        "asr_loaded_languages": list(container.asr.loaded_languages),
        "tts_configured_languages": list(container.tts.configured_languages),
        "tts_loaded_languages": list(container.tts.loaded_languages),
    }


def _diagnostic_storage_items(settings) -> list[dict[str, object]]:
    storage = getattr(settings, "storage", None)
    if storage is None:
        return []

    paths: dict[str, Path] = {
        "data": storage.data_dir,
        "voices": storage.voices_dir,
        "asr_jobs": storage.asr_jobs_dir,
        "tts_jobs": storage.tts_jobs_dir,
        "uploads": storage.uploads_dir,
        "outputs": storage.outputs_dir,
        "logs": storage.logs_dir,
        "auth_db": getattr(settings.security, "auth_db_path", storage.data_dir / "auth.sqlite3"),
    }
    return [
        {
            "name": name,
            "path": str(path),
            "exists": path.exists(),
            "is_dir": path.is_dir(),
            **_path_usage(path),
        }
        for name, path in paths.items()
    ]


def _path_usage(path: Path) -> dict[str, int]:
    if path.is_file():
        return {"size_bytes": path.stat().st_size, "file_count": 1}
    if not path.is_dir():
        return {"size_bytes": 0, "file_count": 0}

    size_bytes = 0
    file_count = 0
    for item in path.rglob("*"):
        if not item.is_file():
            continue
        try:
            size_bytes += item.stat().st_size
            file_count += 1
        except OSError:
            continue
    return {"size_bytes": size_bytes, "file_count": file_count}


def _json_bytes(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")


def _model_file_checks(settings) -> dict[str, bool]:
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
    return checks


def _storage_checks(settings) -> dict[str, bool]:
    storage = getattr(settings, "storage", None)
    if storage is None:
        return {}

    paths: dict[str, Path] = {
        "storage_data_dir": storage.data_dir,
        "storage_voices_dir": storage.voices_dir,
        "storage_asr_jobs_dir": storage.asr_jobs_dir,
        "storage_tts_jobs_dir": storage.tts_jobs_dir,
        "storage_uploads_dir": storage.uploads_dir,
        "storage_outputs_dir": storage.outputs_dir,
        "storage_logs_dir": storage.logs_dir,
    }
    return {name: path.exists() and path.is_dir() for name, path in paths.items()}
