from fastapi import FastAPI
from fastapi.testclient import TestClient

from vvoice.core.errors import (
    AudioError,
    IdempotencyConflictError,
    ModelConfigurationError,
    PUBLIC_AUDIO_ERROR_MESSAGE,
    PUBLIC_MODEL_ERROR_MESSAGE,
    PUBLIC_UNSUPPORTED_AUDIO_FORMAT_MESSAGE,
    UnsupportedAudioFormatError,
)
from vvoice.main import register_exception_handlers


def test_audio_error_response_does_not_expose_decoder_details() -> None:
    response = _response_for(
        AudioError(
            r"Command '['C:\Users\private\.venv\ffmpeg.exe', '-i', 'pipe:0'] failed"
        )
    )

    assert response.status_code == 400
    assert response.json() == {"error": "audio_error", "message": PUBLIC_AUDIO_ERROR_MESSAGE}
    assert "C:\\Users" not in response.text
    assert "ffmpeg.exe" not in response.text


def test_model_error_response_does_not_expose_model_paths() -> None:
    response = _response_for(
        ModelConfigurationError(r"Missing model C:\Users\private\models\encoder.onnx")
    )

    assert response.status_code == 503
    assert response.json() == {
        "error": "model_configuration_error",
        "message": PUBLIC_MODEL_ERROR_MESSAGE,
    }
    assert "C:\\Users" not in response.text


def test_unsupported_audio_uses_stable_415_response() -> None:
    response = _response_for(UnsupportedAudioFormatError(r"C:\Users\private\payload.txt"))

    assert response.status_code == 415
    assert response.json() == {
        "error": "unsupported_audio_format",
        "message": PUBLIC_UNSUPPORTED_AUDIO_FORMAT_MESSAGE,
    }
    assert "C:\\Users" not in response.text


def test_idempotency_conflict_uses_stable_409_response() -> None:
    response = _response_for(
        IdempotencyConflictError("Idempotency-Key was already used for a different request")
    )

    assert response.status_code == 409
    assert response.json() == {
        "error": "idempotency_conflict",
        "message": "Idempotency-Key was already used for a different request",
    }


def _response_for(exc: Exception):
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/fail")
    async def fail():
        raise exc

    return TestClient(app).get("/fail")
