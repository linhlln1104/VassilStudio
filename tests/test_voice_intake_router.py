from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import numpy as np

from vvoice.domains.voices.router import router
from vvoice.domains.voices.service import VoiceStore
from vvoice.main import register_exception_handlers
from vvoice.shared.audio.io import encode_wav


SAMPLE_RATE = 16000


def test_reviewed_upload_creates_once_and_reports_duplicate(tmp_path) -> None:
    client = _client(tmp_path)
    audio = _wave_bytes(3.0)
    form = {"language": "vi", "reference_text": "Giọng nói rõ ràng"}

    reviewed = client.post(
        "/api/v1/voices/intake/analyze",
        data=form,
        files={"reference_audio": ("voice.wav", audio, "audio/wav")},
    )

    assert reviewed.status_code == 200
    report = reviewed.json()
    assert report["status"] == "ready"
    assert report["can_create"] is True
    assert report["channels"] == 1
    assert report["source_sample_rate"] == SAMPLE_RATE
    assert len(report["source_sha256"]) == 64
    assert "audio_path" not in report

    created = client.post(
        "/api/v1/voices",
        data={
            **form,
            "name": "Reviewed voice",
            "reviewed_source_sha256": report["source_sha256"],
            "trim_start_seconds": report["trim_start_seconds"],
            "trim_end_seconds": report["trim_end_seconds"],
        },
        files={"reference_audio": ("voice.wav", audio, "audio/wav")},
    )
    assert created.status_code == 200
    assert created.json()["name"] == "Reviewed voice"

    duplicate_report = client.post(
        "/api/v1/voices/intake/analyze",
        data=form,
        files={"reference_audio": ("renamed.wav", audio, "audio/wav")},
    )
    assert duplicate_report.status_code == 200
    assert duplicate_report.json()["status"] == "blocked"
    assert duplicate_report.json()["duplicate"]["voice_id"] == created.json()["voice_id"]

    duplicate_create = client.post(
        "/api/v1/voices",
        data={**form, "name": "Unexpected duplicate"},
        files={"reference_audio": ("renamed.wav", audio, "audio/wav")},
    )
    assert duplicate_create.status_code == 409
    assert duplicate_create.json()["error"] == "voice_duplicate"


def test_quality_report_blocks_silence_before_profile_creation(tmp_path) -> None:
    client = _client(tmp_path)
    audio = encode_wav(np.zeros(SAMPLE_RATE * 3, dtype=np.float32), SAMPLE_RATE)
    data = {"name": "Silent", "language": "vi", "reference_text": "Giọng nói rõ ràng"}

    reviewed = client.post(
        "/api/v1/voices/intake/analyze",
        data=data,
        files={"reference_audio": ("silent.wav", audio, "audio/wav")},
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["status"] == "blocked"
    assert "speech_not_detected" in {issue["code"] for issue in reviewed.json()["issues"]}

    rejected = client.post(
        "/api/v1/voices",
        data=data,
        files={"reference_audio": ("silent.wav", audio, "audio/wav")},
    )
    assert rejected.status_code == 422
    assert rejected.json()["error"] == "voice_intake_rejected"
    assert client.get("/api/v1/voices").json() == []


def test_local_candidate_uses_the_same_quality_contract(tmp_path) -> None:
    audio = _wave_bytes(3.0)
    (tmp_path / "local voice.wav").write_bytes(audio)
    client = _client(tmp_path)

    response = client.post(
        "/api/v1/voices/import-candidates/local%20voice.wav/analyze",
        data={"language": "vi", "reference_text": "Giọng nói rõ ràng"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["source_duration_seconds"] == 3.0


def _client(voices_dir) -> TestClient:
    class TtsRuntime:
        @staticmethod
        def sample_rate_for(language: str) -> int:
            assert language in {"vi", "en"}
            return 24000

    container = SimpleNamespace(
        settings=SimpleNamespace(
            limits=SimpleNamespace(
                max_upload_bytes=10 * 1024 * 1024,
                max_voice_name_chars=120,
                max_reference_text_chars=2000,
            )
        ),
        tts=TtsRuntime(),
        voices=VoiceStore(voices_dir),
    )
    app = FastAPI()
    app.state.container = container
    register_exception_handlers(app)
    app.include_router(router, prefix="/api/v1/voices")
    return TestClient(app)


def _wave_bytes(seconds: float) -> bytes:
    sample_count = round(seconds * SAMPLE_RATE)
    time = np.arange(sample_count, dtype=np.float32) / SAMPLE_RATE
    samples = (0.25 * np.sin(2 * np.pi * 220 * time)).astype(np.float32)
    return encode_wav(samples, SAMPLE_RATE)
