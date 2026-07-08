from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from vvoice.app.system.router import router


class FakeRuntimeService:
    def __init__(self, languages: tuple[str, ...]) -> None:
        self.configured_languages = languages
        self.loaded_languages: tuple[str, ...] = ()
        self.is_loaded = False
        self.warmup_all_called = False

    def warmup(self) -> None:
        self.loaded_languages = self.configured_languages[:1]
        self.is_loaded = True

    def warmup_all(self) -> None:
        self.loaded_languages = self.configured_languages
        self.is_loaded = True
        self.warmup_all_called = True


def test_model_status_reports_job_workers(tmp_path) -> None:
    app, _, _ = make_app(tmp_path)
    client = TestClient(app)

    response = client.get("/model-status")

    assert response.status_code == 200
    runtime = response.json()["runtime"]
    assert runtime["asr_job_workers"] == 2
    assert runtime["tts_job_workers"] == 3
    assert runtime["asr_job_max_attempts"] == 2
    assert runtime["tts_job_max_attempts"] == 2
    assert runtime["job_retry_backoff_seconds"] == 0.01
    assert runtime["warmup_on_startup"] is True


def test_diagnostics_reports_redacted_operations_metadata(tmp_path) -> None:
    app, _, _ = make_app(tmp_path)
    client = TestClient(app)

    response = client.get("/diagnostics")

    assert response.status_code == 200
    payload = response.json()
    assert payload["license"] == {
        "status": "local",
        "plan": "Local workspace",
        "billing_enabled": False,
    }
    assert payload["security"]["auth_required"] is False
    assert payload["security"]["api_key_auth_enabled"] is False
    assert "api_keys" not in payload["security"]
    assert "session_secret" not in payload["security"]
    assert any(item["name"] == "auth_db" for item in payload["storage"])


def test_liveness_probe_is_process_only(tmp_path) -> None:
    app, _, _ = make_app(tmp_path)
    client = TestClient(app)

    response = client.get("/livez")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {}}


def test_readiness_probe_reports_model_and_storage_checks(tmp_path) -> None:
    app, _, _ = make_app(tmp_path)
    client = TestClient(app)

    response = client.get("/readyz")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["checks"]["asr_vi_encoder"] is True
    assert payload["checks"]["tts_en_data_dir"] is True
    assert payload["checks"]["storage_data_dir"] is True


def test_readiness_probe_returns_503_when_not_ready(tmp_path) -> None:
    app, _, _ = make_app(tmp_path)
    app.state.container.settings.asr.models["vi"].encoder = tmp_path / "missing.onnx"
    client = TestClient(app)

    response = client.get("/readyz")

    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == "not_ready"
    assert payload["checks"]["asr_vi_encoder"] is False


def test_warmup_loads_all_languages(tmp_path) -> None:
    app, asr, tts = make_app(tmp_path)
    client = TestClient(app)

    response = client.post("/warmup")

    assert response.status_code == 200
    assert response.json() == {
        "asr_loaded": True,
        "tts_loaded": True,
        "asr_loaded_languages": ["en", "vi"],
        "tts_loaded_languages": ["en", "vi"],
    }
    assert asr.warmup_all_called
    assert tts.warmup_all_called


def make_app(tmp_path):
    asr = FakeRuntimeService(("en", "vi"))
    tts = FakeRuntimeService(("en", "vi"))
    settings = SimpleNamespace(
        runtime=SimpleNamespace(provider="cpu", num_threads=2, debug=False, warmup_on_startup=True),
        jobs=SimpleNamespace(
            asr_max_workers=2,
            tts_max_workers=3,
            asr_max_attempts=2,
            tts_max_attempts=2,
            retry_backoff_seconds=0.01,
        ),
        security=SimpleNamespace(
            api_keys=(),
            auth_required=False,
            auth_db_path=tmp_path / "auth.sqlite3",
            session_cookie_name="vassil_session",
            session_ttl_seconds=3600,
            secure_cookies=False,
        ),
        asr=SimpleNamespace(enabled=True, models={"vi": make_asr_model(tmp_path), "en": make_asr_model(tmp_path)}),
        tts=SimpleNamespace(enabled=True, models={"vi": make_tts_model(tmp_path), "en": make_tts_model(tmp_path)}),
        storage=SimpleNamespace(
            data_dir=mkdir(tmp_path / "data"),
            voices_dir=mkdir(tmp_path / "voices"),
            asr_jobs_dir=mkdir(tmp_path / "asr-jobs"),
            tts_jobs_dir=mkdir(tmp_path / "tts-jobs"),
            uploads_dir=mkdir(tmp_path / "uploads"),
            outputs_dir=mkdir(tmp_path / "outputs"),
            logs_dir=mkdir(tmp_path / "logs"),
        ),
    )
    app = FastAPI()
    app.state.container = SimpleNamespace(settings=settings, asr=asr, tts=tts)
    app.include_router(router)
    return app, asr, tts


def make_asr_model(tmp_path):
    return SimpleNamespace(
        encoder=touch(tmp_path / "encoder.onnx"),
        decoder=touch(tmp_path / "decoder.onnx"),
        joiner=touch(tmp_path / "joiner.onnx"),
        tokens=touch(tmp_path / "tokens.txt"),
    )


def make_tts_model(tmp_path):
    return SimpleNamespace(
        encoder=touch(tmp_path / "text_model.onnx"),
        decoder=touch(tmp_path / "flow_matching_model.onnx"),
        vocoder=touch(tmp_path / "vocos_24khz.onnx"),
        tokens=touch(tmp_path / "tts_tokens.txt"),
        lexicon=touch(tmp_path / "lexicon.txt"),
        data_dir=mkdir(tmp_path / "espeak-ng-data"),
    )


def touch(path):
    path.write_text("", encoding="utf-8")
    return path


def mkdir(path):
    path.mkdir(exist_ok=True)
    return path
