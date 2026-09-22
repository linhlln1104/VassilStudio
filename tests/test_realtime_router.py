from types import SimpleNamespace

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from vvoice.core.errors import ModelConfigurationError, PUBLIC_MODEL_ERROR_MESSAGE
from vvoice.domains.realtime.router import router


class FakeAsr:
    def __init__(self) -> None:
        self.calls: list[tuple[int, int, str | None]] = []

    def sample_rate_for(self, language: str | None = None) -> int:
        return 16000

    def transcribe(self, samples: np.ndarray, sample_rate: int, language: str | None = None):
        self.calls.append((len(samples), sample_rate, language))
        return SimpleNamespace(text=f"{language}:{len(samples)}")


class FailingAsr(FakeAsr):
    def transcribe(self, samples: np.ndarray, sample_rate: int, language: str | None = None):
        raise ModelConfigurationError(r"Missing C:\Users\private\models\encoder.onnx")


def protocol_client() -> TestClient:
    app = FastAPI()
    app.state.container = SimpleNamespace(
        asr=FakeAsr(),
        settings=SimpleNamespace(
            realtime=SimpleNamespace(
                encoding="pcm_f32le", chunk_seconds=0.5, min_chunk_seconds=0.1,
                max_buffer_seconds=2.0, silence_rms=0.0,
            ),
            limits=SimpleNamespace(max_realtime_frame_bytes=2 * 1024 * 1024),
            security=SimpleNamespace(api_keys=()),
        ),
    )
    app.include_router(router, prefix="/api/v1/realtime")
    return TestClient(app)


@pytest.mark.parametrize("text", [
    "[]", "null", '"close"', "", '{"type": 1}',
    '{"type":"config","chunk_seconds":"abc"}',
    '{"type":"config","chunk_seconds":NaN}',
    '{"type":"config","max_buffer_seconds":1000000000}',
    '{"type":"ping","extra":true}', " " * 4097,
])
def test_invalid_control_has_error_envelope_and_protocol_close(text) -> None:
    with protocol_client().websocket_connect("/api/v1/realtime/asr") as websocket:
        assert websocket.receive_json()["type"] == "ready"
        websocket.send_text(text)
        assert websocket.receive_json()["type"] == "error"
        with pytest.raises(WebSocketDisconnect) as closed:
            websocket.receive_json()
        assert closed.value.code == 1003


def test_close_ack_follows_final_transcript() -> None:
    with protocol_client().websocket_connect("/api/v1/realtime/asr") as websocket:
        websocket.receive_json()
        websocket.send_bytes(np.full(800, 0.1, dtype=np.float32).tobytes())
        websocket.send_json({"type": "close"})
        final = websocket.receive_json()
        assert final["type"] == "transcript"
        assert final["final"] is True
        assert final["text"] == "vi:800"
        assert websocket.receive_json() == {"type": "closed"}


def test_invalid_language_returns_safe_error_after_accept() -> None:
    with protocol_client().websocket_connect("/api/v1/realtime/asr?language=invalid") as websocket:
        assert websocket.receive_json()["type"] == "error"


def test_realtime_websocket_uses_requested_language() -> None:
    fake_asr = FakeAsr()
    app = FastAPI()
    app.state.container = SimpleNamespace(
        asr=fake_asr,
        settings=SimpleNamespace(
            realtime=SimpleNamespace(
                encoding="pcm_f32le",
                chunk_seconds=0.1,
                min_chunk_seconds=0.1,
                max_buffer_seconds=1.0,
                silence_rms=0.0,
            ),
            limits=SimpleNamespace(max_realtime_frame_bytes=2 * 1024 * 1024),
            security=SimpleNamespace(api_keys=()),
        ),
    )
    app.include_router(router, prefix="/api/v1/realtime")

    client = TestClient(app)
    samples = np.full(1600, 0.1, dtype=np.float32)

    with client.websocket_connect("/api/v1/realtime/asr?language=en") as websocket:
        ready = websocket.receive_json()
        websocket.send_bytes(samples.tobytes())
        transcript = websocket.receive_json()

    assert ready["type"] == "ready"
    assert ready["language"] == "en"
    assert ready["sample_rate"] == 16000
    assert transcript["type"] == "transcript"
    assert transcript["language"] == "en"
    assert transcript["text"] == "en:1600"
    assert fake_asr.calls == [(1600, 16000, "en")]


def test_realtime_websocket_redacts_model_failure_details() -> None:
    app = FastAPI()
    app.state.container = SimpleNamespace(
        asr=FailingAsr(),
        settings=SimpleNamespace(
            realtime=SimpleNamespace(
                encoding="pcm_f32le",
                chunk_seconds=0.1,
                min_chunk_seconds=0.1,
                max_buffer_seconds=1.0,
                silence_rms=0.0,
            ),
            limits=SimpleNamespace(max_realtime_frame_bytes=2 * 1024 * 1024),
            security=SimpleNamespace(api_keys=()),
        ),
    )
    app.include_router(router, prefix="/api/v1/realtime")

    samples = np.full(1600, 0.1, dtype=np.float32)
    with TestClient(app).websocket_connect("/api/v1/realtime/asr?language=en") as websocket:
        websocket.receive_json()
        websocket.send_bytes(samples.tobytes())
        error = websocket.receive_json()

    assert error == {"type": "error", "message": PUBLIC_MODEL_ERROR_MESSAGE}
    assert "C:\\Users" not in error["message"]
