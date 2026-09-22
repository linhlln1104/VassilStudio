from __future__ import annotations

from datetime import UTC, datetime
import io
import json
import os
from pathlib import Path
import platform
import shutil
import sys
import zipfile

from fastapi import APIRouter, Depends, Query, Request, Response
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

_MEBIBYTE = 1024**2
_GIBIBYTE = 1024**3
_TEBIBYTE = 1024**4
_STORAGE_PATH_ALIASES = {
    "data": "DATA_ROOT",
    "voices": "DATA_ROOT/voices",
    "asr_jobs": "DATA_ROOT/jobs/asr",
    "tts_jobs": "DATA_ROOT/jobs/tts",
    "uploads": "DATA_ROOT/uploads",
    "outputs": "DATA_ROOT/outputs",
    "logs": "LOGS_ROOT",
    "auth_db": "DATA_ROOT/auth.sqlite3",
}


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
async def diagnostics(request: Request, response: Response):
    container = request.app.state.container
    settings = request.app.state.container.settings
    response.headers["Cache-Control"] = "no-store"
    return await run_in_threadpool(_diagnostics_payload, container, settings)


@router.get(
    "/diagnostics/bundle",
    dependencies=[Depends(require_api_key)],
)
async def diagnostics_bundle(
    request: Request,
    include_host_metadata: bool = Query(
        default=False,
        description="Include coarse Python, operating-system, and architecture metadata.",
    ),
):
    container = request.app.state.container
    settings = request.app.state.container.settings
    payload = await run_in_threadpool(
        _diagnostics_payload,
        container,
        settings,
        host_metadata_included=include_host_metadata,
    )
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
            _json_bytes(_environment_payload(include_host_metadata)),
        )
        bundle.writestr(
            "README.txt",
            _bundle_readme(include_host_metadata),
        )

    archive.seek(0)
    return StreamingResponse(
        archive,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="vassilstudio-diagnostics-{generated_at}.zip"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


def _diagnostics_payload(
    container,
    settings,
    *,
    host_metadata_included: bool = False,
) -> dict:
    return {
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "version": __version__,
        "privacy": {
            "storage_paths": "logical_aliases",
            "storage_metrics": "bucketed",
            "host_metadata_included": host_metadata_included,
        },
        "runtime": _runtime_status(container, settings),
        "security": {
            "auth_required": getattr(settings.security, "auth_required", False),
            "api_key_auth_enabled": bool(settings.security.api_keys),
            "session_cookie_name": getattr(settings.security, "session_cookie_name", "vassil_session"),
            "session_ttl_seconds": getattr(settings.security, "session_ttl_seconds", 0),
            "secure_cookies": getattr(settings.security, "secure_cookies", False),
        },
        "storage": _diagnostic_storage_items(settings),
        "recovery_warnings": _recovery_warnings(container),
        "license": {
            "status": "open-source",
            "plan": "GPL-3.0-or-later",
            "billing_enabled": False,
        },
    }


def _recovery_warnings(container) -> list[str]:
    warnings = []
    for name in ("voices", "asr_jobs", "tts_jobs"):
        count = getattr(getattr(container, name, None), "quarantined_count", 0)
        if count:
            warnings.append(
                f"{name}: {count} damaged metadata record(s) were isolated. "
                "Original records are retained for recovery; restore them from a verified backup."
            )
    return warnings


@router.post(
    "/warmup/asr",
    response_model=WarmupResponse,
    dependencies=[Depends(require_api_key)],
)
async def warmup_asr(request: Request, language: str | None = None):
    container = request.app.state.container
    await run_in_threadpool(container.asr.warmup, language)
    return {
        "loaded": container.asr.is_loaded,
        "loaded_languages": list(container.asr.loaded_languages),
    }


@router.post(
    "/warmup/tts",
    response_model=WarmupResponse,
    dependencies=[Depends(require_api_key)],
)
async def warmup_tts(request: Request, language: str | None = None):
    container = request.app.state.container
    await run_in_threadpool(container.tts.warmup, language)
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
        "asr_num_threads": settings.runtime.effective_asr_num_threads,
        "tts_num_threads": settings.runtime.effective_tts_num_threads,
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
    items: list[dict[str, object]] = []
    for name, path in paths.items():
        capacity_bytes, free_bytes = _volume_usage(path)
        size_bytes, file_count = _path_usage(path)
        items.append(
            {
                "name": name,
                "path_alias": _STORAGE_PATH_ALIASES[name],
                "exists": path.exists(),
                "is_dir": path.is_dir(),
                "writable": _path_writable(path),
                "usage_bucket": _usage_bucket(size_bytes),
                "file_count_bucket": _file_count_bucket(file_count),
                "capacity_bucket": _capacity_bucket(capacity_bytes),
                "free_space_bucket": _capacity_bucket(free_bytes),
                "storage_pressure": _storage_pressure(capacity_bytes, free_bytes),
            }
        )
    return items


def _path_usage(path: Path) -> tuple[int, int]:
    if path.is_file():
        return path.stat().st_size, 1
    if not path.is_dir():
        return 0, 0

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
    return size_bytes, file_count


def _usage_bucket(size_bytes: int) -> str:
    if size_bytes <= 0:
        return "empty"
    if size_bytes < _MEBIBYTE:
        return "under_1_mb"
    if size_bytes < 100 * _MEBIBYTE:
        return "1_to_99_mb"
    if size_bytes < _GIBIBYTE:
        return "100_to_999_mb"
    if size_bytes < 10 * _GIBIBYTE:
        return "1_to_9_gb"
    if size_bytes < 100 * _GIBIBYTE:
        return "10_to_99_gb"
    return "100_gb_or_more"


def _file_count_bucket(file_count: int) -> str:
    if file_count <= 0:
        return "none"
    if file_count < 10:
        return "1_to_9"
    if file_count < 100:
        return "10_to_99"
    if file_count < 1000:
        return "100_to_999"
    return "1000_or_more"


def _capacity_bucket(size_bytes: int | None) -> str | None:
    if size_bytes is None:
        return None
    if size_bytes < 10 * _GIBIBYTE:
        return "under_10_gb"
    if size_bytes < 50 * _GIBIBYTE:
        return "10_to_49_gb"
    if size_bytes < 100 * _GIBIBYTE:
        return "50_to_99_gb"
    if size_bytes < 500 * _GIBIBYTE:
        return "100_to_499_gb"
    if size_bytes < _TEBIBYTE:
        return "500_to_999_gb"
    return "1_tb_or_more"


def _storage_pressure(capacity_bytes: int | None, free_bytes: int | None) -> str:
    if capacity_bytes is None or free_bytes is None or capacity_bytes <= 0:
        return "unknown"
    free_ratio = free_bytes / capacity_bytes
    if free_bytes < _GIBIBYTE or free_ratio < 0.05:
        return "critical"
    if free_bytes < 5 * _GIBIBYTE or free_ratio < 0.15:
        return "low"
    return "normal"


def _path_writable(path: Path) -> bool:
    if path.exists():
        return os.access(path, os.W_OK)
    anchor = _existing_path(path.parent)
    return bool(anchor and os.access(anchor, os.W_OK))


def _volume_usage(path: Path) -> tuple[int | None, int | None]:
    anchor = _existing_path(path if path.is_dir() else path.parent)
    if anchor is None:
        return None, None
    try:
        usage = shutil.disk_usage(anchor)
    except OSError:
        return None, None
    return usage.total, usage.free


def _existing_path(path: Path) -> Path | None:
    candidate = path
    while not candidate.exists():
        parent = candidate.parent
        if parent == candidate:
            return None
        candidate = parent
    return candidate


def _json_bytes(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")


def _environment_payload(include_host_metadata: bool) -> dict[str, object]:
    if not include_host_metadata:
        return {"included": False}
    return {
        "included": True,
        "python_version": sys.version.split()[0],
        "operating_system": platform.system(),
        "operating_system_release": platform.release(),
        "architecture": platform.machine(),
    }


def _bundle_readme(include_host_metadata: bool) -> str:
    host_status = "included by explicit request" if include_host_metadata else "excluded"
    return (
        "VassilStudio diagnostics bundle\n"
        "Storage locations use logical aliases; usage, file counts, and disk values are bucketed.\n"
        f"Host metadata: {host_status}.\n"
        "API keys, session secrets, cookies, transcripts, and audio files are not included.\n"
        "Review every file before sharing this archive.\n"
    )


def _model_file_checks(settings) -> dict[str, bool]:
    checks = {}
    for language, model in settings.asr.models.items():
        if not getattr(settings.asr, "enabled", True):
            continue
        prefix = f"asr_{language}"
        checks.update(
            {
                f"{prefix}_encoder": _usable_file(model.encoder),
                f"{prefix}_decoder": _usable_file(model.decoder),
                f"{prefix}_joiner": _usable_file(model.joiner),
                f"{prefix}_tokens": _usable_file(model.tokens),
            }
        )
    for language, model in settings.tts.models.items():
        if not getattr(settings.tts, "enabled", True):
            continue
        prefix = f"tts_{language}"
        checks.update(
            {
                f"{prefix}_encoder": _usable_file(model.encoder),
                f"{prefix}_decoder": _usable_file(model.decoder),
                f"{prefix}_vocoder": _usable_file(model.vocoder),
                f"{prefix}_tokens": _usable_file(model.tokens),
                f"{prefix}_lexicon": _usable_file(model.lexicon),
                f"{prefix}_data_dir": model.data_dir.is_dir(),
            }
        )
    return checks


def _usable_file(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


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
    return {
        name: path.exists() and path.is_dir() and os.access(path, os.W_OK)
        for name, path in paths.items()
    }
