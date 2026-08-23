from contextlib import asynccontextmanager
import logging
import time
import uuid

from fastapi import Depends, FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from vvoice import __version__
from vvoice.core.brand import API_BRAND_NAME
from vvoice.core.config import load_settings
from vvoice.core.container import AppContainer
from vvoice.core.errors import (
    AudioError,
    AsrJobNotFoundError,
    IdempotencyConflictError,
    ModelConfigurationError,
    TranscriptNotReadyError,
    TranscriptRevisionConflictError,
    TtsJobNotFoundError,
    UnsupportedAudioFormatError,
    VVoiceError,
    VoiceNotFoundError,
    public_error_message,
)
from vvoice.core.observability import (
    REQUEST_ID_HEADER,
    configure_logging,
    get_request_id,
    reset_request_id,
    set_request_id,
)
from vvoice.app.auth.router import router as auth_router
from vvoice.domains.asr.router import router as asr_router
from vvoice.domains.realtime.router import router as realtime_router
from vvoice.shared.security.auth import require_api_key
from vvoice.shared.security.headers import apply_browser_security_headers
from vvoice.app.studio.router import router as studio_router
from vvoice.app.system.router import router as system_router
from vvoice.domains.tts.router import router as tts_router
from vvoice.domains.voices.router import router as voices_router


def create_app() -> FastAPI:
    settings = load_settings()
    configure_logging(
        debug=settings.runtime.debug,
        log_level=settings.runtime.log_level,
    )
    container = AppContainer(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        try:
            if settings.runtime.warmup_on_startup:
                await run_in_threadpool(container.asr.warmup_all)
                await run_in_threadpool(container.tts.warmup_all)
            yield
        finally:
            container.shutdown()

    app = FastAPI(title=API_BRAND_NAME, version=__version__, lifespan=lifespan)
    app.state.container = container

    register_request_middleware(app)
    register_exception_handlers(app)

    app.include_router(system_router, tags=["system"])
    app.include_router(auth_router, prefix="/api/v1/auth", tags=["auth"])
    protected = [Depends(require_api_key)]

    app.include_router(asr_router, prefix="/api/v1/asr", tags=["asr"], dependencies=protected)
    app.include_router(tts_router, prefix="/api/v1/tts", tags=["tts"], dependencies=protected)
    app.include_router(voices_router, prefix="/api/v1/voices", tags=["voices"], dependencies=protected)
    app.include_router(realtime_router, prefix="/api/v1/realtime", tags=["realtime"])
    app.include_router(studio_router, tags=["studio"])

    return app


def register_request_middleware(app: FastAPI) -> None:
    logger = logging.getLogger("vvoice.http")

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = _request_id_from_header(request.headers.get(REQUEST_ID_HEADER))
        request.state.request_id = request_id
        token = set_request_id(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
            logger.exception(
                "http_request_failed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": elapsed_ms,
                },
            )
            raise
        else:
            elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
            apply_browser_security_headers(request, response)
            response.headers[REQUEST_ID_HEADER] = request_id
            logger.info(
                "http_request_completed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": elapsed_ms,
                },
            )
            return response
        finally:
            reset_request_id(token)


def register_exception_handlers(app: FastAPI) -> None:
    logger = logging.getLogger("vvoice.errors")

    @app.exception_handler(UnsupportedAudioFormatError)
    async def unsupported_audio_handler(
        _: Request,
        exc: UnsupportedAudioFormatError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=415,
            content=_error_content("unsupported_audio_format", public_error_message(exc)),
        )

    @app.exception_handler(AudioError)
    async def audio_error_handler(_: Request, exc: AudioError) -> JSONResponse:
        _log_private_exception(logger, "audio_request_failed", exc)
        return JSONResponse(
            status_code=400,
            content=_error_content("audio_error", public_error_message(exc)),
        )

    @app.exception_handler(VoiceNotFoundError)
    async def voice_not_found_handler(_: Request, exc: VoiceNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content=_error_content("voice_not_found", str(exc)))

    @app.exception_handler(TtsJobNotFoundError)
    async def tts_job_not_found_handler(_: Request, exc: TtsJobNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content=_error_content("tts_job_not_found", str(exc)))

    @app.exception_handler(AsrJobNotFoundError)
    async def asr_job_not_found_handler(_: Request, exc: AsrJobNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content=_error_content("asr_job_not_found", str(exc)))

    @app.exception_handler(ModelConfigurationError)
    async def model_config_error_handler(
        _: Request,
        exc: ModelConfigurationError,
    ) -> JSONResponse:
        _log_private_exception(logger, "model_request_failed", exc)
        return JSONResponse(
            status_code=503,
            content=_error_content("model_configuration_error", public_error_message(exc)),
        )

    @app.exception_handler(IdempotencyConflictError)
    async def idempotency_conflict_handler(
        _: Request,
        exc: IdempotencyConflictError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content=_error_content("idempotency_conflict", str(exc)),
        )

    @app.exception_handler(TranscriptRevisionConflictError)
    async def transcript_revision_conflict_handler(
        _: Request,
        exc: TranscriptRevisionConflictError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content=_error_content("transcript_revision_conflict", str(exc)),
        )

    @app.exception_handler(TranscriptNotReadyError)
    async def transcript_not_ready_handler(
        _: Request,
        exc: TranscriptNotReadyError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content=_error_content("transcript_not_ready", str(exc)),
        )

    @app.exception_handler(VVoiceError)
    async def vvoice_error_handler(_: Request, exc: VVoiceError) -> JSONResponse:
        return JSONResponse(status_code=400, content=_error_content("vvoice_error", str(exc)))


def _request_id_from_header(value: str | None) -> str:
    candidate = (value or "").strip()
    if candidate and len(candidate) <= 128 and "\r" not in candidate and "\n" not in candidate:
        return candidate
    return uuid.uuid4().hex


def _error_content(error: str, message: str) -> dict[str, str]:
    content = {"error": error, "message": message}
    request_id = get_request_id()
    if request_id:
        content["request_id"] = request_id
    return content


def _log_private_exception(logger: logging.Logger, event: str, exc: Exception) -> None:
    logger.warning(
        event,
        extra={"exception_type": type(exc).__name__},
        exc_info=(type(exc), exc, exc.__traceback__),
    )
