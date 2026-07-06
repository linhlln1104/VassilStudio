from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from vvoice.core.brand import API_BRAND_NAME
from vvoice.core.config import load_settings
from vvoice.core.container import AppContainer
from vvoice.core.errors import (
    AudioError,
    AsrJobNotFoundError,
    ModelConfigurationError,
    TtsJobNotFoundError,
    VVoiceError,
    VoiceNotFoundError,
)
from vvoice.domains.asr.router import router as asr_router
from vvoice.domains.realtime.router import router as realtime_router
from vvoice.shared.security.auth import require_api_key
from vvoice.app.studio.router import router as studio_router
from vvoice.app.system.router import router as system_router
from vvoice.domains.tts.router import router as tts_router
from vvoice.domains.voices.router import router as voices_router


def create_app() -> FastAPI:
    settings = load_settings()
    container = AppContainer(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        try:
            yield
        finally:
            container.shutdown()

    app = FastAPI(title=API_BRAND_NAME, version="0.1.0", lifespan=lifespan)
    app.state.container = container

    register_exception_handlers(app)

    app.include_router(system_router, tags=["system"])
    protected = [Depends(require_api_key)]

    app.include_router(asr_router, prefix="/api/v1/asr", tags=["asr"], dependencies=protected)
    app.include_router(tts_router, prefix="/api/v1/tts", tags=["tts"], dependencies=protected)
    app.include_router(voices_router, prefix="/api/v1/voices", tags=["voices"], dependencies=protected)
    app.include_router(realtime_router, prefix="/api/v1/realtime", tags=["realtime"])
    app.include_router(studio_router, tags=["studio"])

    return app


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AudioError)
    async def audio_error_handler(_: Request, exc: AudioError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"error": "audio_error", "message": str(exc)})

    @app.exception_handler(VoiceNotFoundError)
    async def voice_not_found_handler(_: Request, exc: VoiceNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"error": "voice_not_found", "message": str(exc)})

    @app.exception_handler(TtsJobNotFoundError)
    async def tts_job_not_found_handler(_: Request, exc: TtsJobNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"error": "tts_job_not_found", "message": str(exc)})

    @app.exception_handler(AsrJobNotFoundError)
    async def asr_job_not_found_handler(_: Request, exc: AsrJobNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"error": "asr_job_not_found", "message": str(exc)})

    @app.exception_handler(ModelConfigurationError)
    async def model_config_error_handler(
        _: Request,
        exc: ModelConfigurationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={"error": "model_configuration_error", "message": str(exc)},
        )

    @app.exception_handler(VVoiceError)
    async def vvoice_error_handler(_: Request, exc: VVoiceError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"error": "vvoice_error", "message": str(exc)})
