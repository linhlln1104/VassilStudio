from types import SimpleNamespace

import numpy as np
from fastapi import FastAPI
from fastapi.testclient import TestClient

from vvoice.domains.realtime.router import router


class FakeAsr:
    def __init__(self) -> None:
        self.calls: list[tuple[int, int, str | None]] = []

    def sample_rate_for(self, language: str | None = None) -> int:
        return 16000

    def transcribe(self, samples: np.ndarray, sample_rate: int, language: str | None = None):
        self.calls.append((len(samples), sample_rate, language))
        return SimpleNamespace(text=f"{language}:{len(samples)}")


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
