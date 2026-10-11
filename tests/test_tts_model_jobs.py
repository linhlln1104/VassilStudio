import json
from datetime import UTC, datetime
import threading
import time
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import numpy as np
import pytest

from vvoice.core.config import RuntimeSettings, TtsProfileSettings, TtsSettings
from vvoice.core.errors import IdempotencyConflictError, VVoiceError
from vvoice.domains.tts.jobs import TtsJobService
from vvoice.domains.tts.parameters import validate_tts_parameters
from vvoice.domains.tts.router import router
from vvoice.domains.tts.service import GeneratedSpeech, TtsService
from vvoice.domains.voices.service import VoiceStore
from vvoice.inference.tts.base import TtsCapabilities
from vvoice.inference.tts.registry import TtsRegistry
from vvoice.main import register_exception_handlers
from vvoice.shared.audio.io import encode_wav
from vvoice.shared.jobs.integrity import idempotency_key_hash, request_fingerprint


class MultiModelTts:
    """An inference-free implementation of the public model-selection contract."""

    def __init__(self):
        self.default_models = {"vi": "zipvoice-vi", "en": "zipvoice-en"}
        self.models = {
            "zipvoice-vi": ("vi", 24000, True),
            "zipvoice-en": ("en", 24000, True),
            "vieneu-v3-turbo": ("vi", 16000, False),
        }
        self.calls = []
        self.on_synthesize = None

    def resolve_model_id(self, language=None, model_id=None):
        selected = self.default_models[language or "vi"] if model_id is None else model_id.strip()
        if selected not in self.models:
            raise VVoiceError("Unknown TTS model_id")
        if language and self.models[selected][0] != language:
            raise VVoiceError("Model does not support language")
        return selected

    def validate_request(self, *, language=None, model_id=None, num_steps=None, speed=None):
        validate_tts_parameters(num_steps, speed)
        selected = self.resolve_model_id(language, model_id)
        if num_steps is not None and not self.models[selected][2]:
            raise VVoiceError("Model does not support num_steps")
        return selected

    def sample_rate_for(self, language=None, model_id=None):
        return self.models[self.resolve_model_id(language, model_id)][1]

    def synthesize(self, **kwargs):
        self.calls.append(kwargs)
        if self.on_synthesize:
            self.on_synthesize(kwargs)
        rate = self.sample_rate_for(kwargs["language"], kwargs["model_id"])
        return GeneratedSpeech(np.zeros(rate // 10, dtype=np.float32), rate, 0.1)

    def model_catalog(self):
        return {
            "default_models": self.default_models,
            "models": [
                {
                    "model_id": model_id,
                    "engine": "zipvoice" if model_id.startswith("zipvoice") else "vieneu",
                    "label": model_id,
                    "languages": [language],
                    "sample_rate": rate,
                    "capabilities": {
                        "reference_audio": True, "num_steps": num_steps, "speed": True,
                    },
                    "ready": True,
                    "loaded": False,
                    "status": "ready",
                    "checks": {"configured": True},
                    "message": None,
                }
                for model_id, (language, rate, num_steps) in self.models.items()
            ],
        }


@pytest.fixture
def model_jobs(tmp_path):
    voices = VoiceStore(tmp_path / "voices")
    audio = encode_wav(np.zeros(2400, dtype=np.float32), 24000)
    profile = voices.create(
        name="Vietnamese reference", language="vi", reference_text="Xin chào",
        reference_text_source="user", audio_bytes=audio,
        sample_rate=24000, duration_seconds=0.1,
    )
    tts = MultiModelTts()
    jobs = TtsJobService(
        tmp_path / "jobs", tts, voices, max_attempts=2, retry_backoff_seconds=0,
    )
    app = FastAPI()
    app.state.container = SimpleNamespace(
        tts=tts, tts_jobs=jobs, voices=voices,
        settings=SimpleNamespace(security=SimpleNamespace(auth_required=False, api_keys=()), limits=SimpleNamespace(
            max_tts_text_chars=5000, max_reference_text_chars=5000, max_upload_bytes=100000,
        )),
    )
    register_exception_handlers(app)
    app.include_router(router, prefix="/api/v1/tts")
    with TestClient(app) as client:
        yield SimpleNamespace(
            tts=tts, jobs=jobs, voices=voices, profile=profile, audio=audio,
            client=client, directory=tmp_path / "jobs",
        )
    jobs.shutdown()
    jobs._executor.shutdown(wait=True)


def wait_for_job(jobs, job_id):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        job = jobs.get(job_id)
        if job.status in {"succeeded", "failed", "cancelled"}:
            return job
        time.sleep(0.01)
    raise AssertionError("TTS job did not finish")


def test_two_models_for_one_language_use_their_own_audio_rate_and_persist_selection(model_jobs):
    env = model_jobs
    for model_id, rate in [("zipvoice-vi", 24000), ("vieneu-v3-turbo", 16000)]:
        response = env.client.post(
            f"/api/v1/tts/jobs/voices/{env.profile.voice_id}",
            data={"text": "Xin chào", "model_id": model_id},
        )
        assert response.status_code == 202
        assert response.json()["model_id"] == model_id
        job = wait_for_job(env.jobs, response.json()["job_id"])
        assert job.status == "succeeded"
        assert job.model_id == model_id
        assert job.sample_rate == rate
        assert env.tts.calls[-1]["model_id"] == model_id
        assert env.tts.calls[-1]["reference_sample_rate"] == rate
        metadata = json.loads((env.directory / job.job_id / "metadata.json").read_text())
        assert metadata["model_id"] == model_id
        detail = env.client.get(f"/api/v1/tts/jobs/{job.job_id}")
        assert detail.json()["model_id"] == model_id


def test_retry_does_not_follow_a_changed_default(model_jobs):
    env = model_jobs

    def change_default_and_fail_once(_):
        if len(env.tts.calls) == 1:
            env.tts.default_models["vi"] = "vieneu-v3-turbo"
            raise RuntimeError("Transient inference failure")

    env.tts.on_synthesize = change_default_and_fail_once
    created = env.jobs.create_from_voice(voice_id=env.profile.voice_id, text="Xin chào")
    job = wait_for_job(env.jobs, created.job_id)
    assert job.status == "succeeded"
    assert job.attempt == 2
    assert [call["model_id"] for call in env.tts.calls] == ["zipvoice-vi", "zipvoice-vi"]
    assert job.sample_rate == 24000


def test_waiting_job_keeps_accepted_model_while_new_jobs_follow_new_default(model_jobs):
    env = model_jobs
    started, release = threading.Event(), threading.Event()

    def hold_first_request(kwargs):
        if kwargs["text"] == "first":
            started.set()
            if not release.wait(10):
                raise RuntimeError("Test inference was not released")

    env.tts.on_synthesize = hold_first_request
    try:
        first = env.jobs.create_from_voice(voice_id=env.profile.voice_id, text="first")
        assert started.wait(5)
        queued = env.jobs.create_from_voice(voice_id=env.profile.voice_id, text="second")
        assert queued.status == "queued"
        env.tts.default_models["vi"] = "vieneu-v3-turbo"
        newest = env.jobs.create_from_voice(voice_id=env.profile.voice_id, text="third")
        release.set()
        for job in [first, queued, newest]:
            assert wait_for_job(env.jobs, job.job_id).status == "succeeded"
        assert [(call["text"], call["model_id"]) for call in env.tts.calls] == [
            ("first", "zipvoice-vi"), ("second", "zipvoice-vi"), ("third", "vieneu-v3-turbo"),
        ]
    finally:
        release.set()


def test_idempotent_replay_keeps_accepted_model_after_default_switch(model_jobs):
    env = model_jobs
    request = {"voice_id": env.profile.voice_id, "text": "Xin chào", "idempotency_key": "model-1"}
    created = env.jobs.create_from_voice(**request)
    assert wait_for_job(env.jobs, created.job_id).status == "succeeded"
    env.tts.default_models["vi"] = "vieneu-v3-turbo"
    env.voices.delete(env.profile.voice_id)
    # Result retrieval must not depend on the reference or model still being configured.
    del env.tts.models["zipvoice-vi"]
    assert env.jobs.create_from_voice(**request).job_id == created.job_id
    assert env.jobs.create_from_voice(**request, model_id=" zipvoice-vi ").job_id == created.job_id
    with pytest.raises(IdempotencyConflictError):
        env.jobs.create_from_voice(**request, model_id="vieneu-v3-turbo")
    assert len(env.tts.calls) == 1


@pytest.mark.parametrize("status", ["succeeded", "running"])
def test_legacy_jobs_and_fingerprints_keep_zipvoice_after_restart(model_jobs, status):
    env = model_jobs
    legacy_dir = env.directory / "legacy"
    legacy_dir.mkdir()
    request = {
        "voice_id": env.profile.voice_id, "language": "vi", "text": "Xin chào",
        "num_steps": None, "speed": None,
    }
    (legacy_dir / "metadata.json").write_text(json.dumps({
        **request, "job_id": "legacy", "status": status,
        "created_at": datetime.now(UTC).isoformat(),
        "idempotency_key_hash": idempotency_key_hash("legacy-key"),
        "request_fingerprint": request_fingerprint(request),
    }), encoding="utf-8")
    env.tts.default_models["vi"] = "vieneu-v3-turbo"
    env.voices.delete(env.profile.voice_id)
    recovered = TtsJobService(env.directory, env.tts, env.voices, worker_enabled=False)
    try:
        job = recovered.get("legacy")
        assert job.model_id == "zipvoice-vi"
        assert job.status == status
        replay = recovered.create_from_voice(
            voice_id=env.profile.voice_id, text="Xin chào", idempotency_key="legacy-key",
        )
        assert replay.job_id == "legacy"
        assert replay.model_id == "zipvoice-vi"
        with pytest.raises(IdempotencyConflictError):
            recovered.create_from_voice(
                **request, model_id="vieneu-v3-turbo", idempotency_key="legacy-key",
            )
        if status == "running":
            saved = json.loads((legacy_dir / "metadata.json").read_text())
            assert saved["model_id"] == "zipvoice-vi"
            assert saved["request_fingerprint"] == request_fingerprint({
                **request, "model_id": "zipvoice-vi",
            })
    finally:
        recovered.shutdown()


@pytest.mark.parametrize("data", [
    {"model_id": "unknown-model"},
    {"model_id": "   "},
    {"model_id": "vieneu-v3-turbo", "language": "en"},
    {"model_id": "vieneu-v3-turbo", "num_steps": "8"},
])
def test_invalid_model_requests_are_rejected_before_queueing(model_jobs, data):
    env = model_jobs
    response = env.client.post(
        f"/api/v1/tts/jobs/voices/{env.profile.voice_id}", data={"text": "Xin chào", **data},
    )
    assert response.status_code == 400
    assert env.jobs.list() == []
    assert env.tts.calls == []


@pytest.mark.parametrize("saved_voice", [False, True])
def test_synchronous_synthesis_forwards_selected_model_and_sample_rate(model_jobs, saved_voice):
    env = model_jobs
    data = {"text": "Xin chào", "model_id": "vieneu-v3-turbo"}
    if saved_voice:
        response = env.client.post(
            f"/api/v1/tts/synthesize/voices/{env.profile.voice_id}", data=data,
        )
    else:
        response = env.client.post(
            "/api/v1/tts/synthesize", data={**data, "reference_text": "Xin chào"},
            files={"reference_audio": ("reference.wav", env.audio, "audio/wav")},
        )
    assert response.status_code == 200
    assert response.headers["x-vassil-sample-rate"] == "16000"
    assert env.tts.calls[-1]["model_id"] == "vieneu-v3-turbo"
    assert env.tts.calls[-1]["reference_sample_rate"] == 16000


def test_model_catalog_and_openapi_expose_selection_without_inference(model_jobs):
    env = model_jobs
    response = env.client.get("/api/v1/tts/models")
    assert response.status_code == 200
    assert response.json() == env.tts.model_catalog()
    assert env.tts.calls == []
    schema = env.client.get("/openapi.json").json()
    assert "model_id" in schema["components"]["schemas"]["TtsJobResponse"]["required"]
    for path in ["/synthesize", "/synthesize/voices/{voice_id}", "/jobs/voices/{voice_id}"]:
        body = schema["paths"][f"/api/v1/tts{path}"]["post"]["requestBody"]
        media = next(iter(body["content"].values()))
        form_name = media["schema"]["$ref"].rsplit("/", 1)[-1]
        form = schema["components"]["schemas"][form_name]
        assert "model_id" in form["properties"]
        assert "model_id" not in form["required"]


def test_real_service_api_validates_catalog_selection_before_loading_and_routes_audio(model_jobs):
    env = model_jobs
    loaded, generated = [], []

    class Adapter:
        def __init__(self, profile, _runtime):
            self.profile = profile
            supports_controls = profile.model_id.startswith("zipvoice")
            self.capabilities = TtsCapabilities(
                reference_audio=True, num_steps=supports_controls, speed=supports_controls,
            )

        def checks(self):
            return {"configured": True}

        def load(self):
            loaded.append(self.profile.model_id)

        def synthesize(self, **kwargs):
            generated.append((self.profile.model_id, kwargs["reference_sample_rate"]))
            rate = self.profile.sample_rate
            return GeneratedSpeech(np.zeros(rate // 10, dtype=np.float32), rate, 0.1)

    profiles = {
        model_id: TtsProfileSettings(
            model_id, "fixture", model_id, (language,), rate, env.directory, {},
        )
        for model_id, (language, rate, _) in env.tts.models.items()
    }
    settings = TtsSettings(True, 24000, "vi", {}, profiles, dict(env.tts.default_models))
    runtime = RuntimeSettings("local", "127.0.0.1", "INFO", "cpu", 1, False, False)
    registry = TtsRegistry()
    registry.register("fixture", Adapter)
    service = TtsService(settings, runtime, registry)
    env.client.app.state.container.tts = service
    env.jobs._tts = service

    catalog = env.client.get("/api/v1/tts/models")
    assert catalog.status_code == 200
    assert {model["model_id"] for model in catalog.json()["models"]} == set(profiles)
    endpoint = f"/api/v1/tts/jobs/voices/{env.profile.voice_id}"
    for invalid in [
        {"model_id": "unknown"}, {"model_id": "   "},
        {"model_id": "vieneu-v3-turbo", "language": "en"},
        {"model_id": "vieneu-v3-turbo", "num_steps": "8"},
        {"model_id": "vieneu-v3-turbo", "speed": "1.25"},
    ]:
        response = env.client.post(endpoint, data={"text": "Xin chào", **invalid})
        assert response.status_code == 400, response.text
    assert env.jobs.list() == []
    assert loaded == []

    for model_id in ["zipvoice-vi", "vieneu-v3-turbo"]:
        response = env.client.post(endpoint, data={"text": "Xin chào", "model_id": model_id})
        assert response.status_code == 202
        assert wait_for_job(env.jobs, response.json()["job_id"]).status == "succeeded"
    assert loaded == ["zipvoice-vi", "vieneu-v3-turbo"]
    assert generated == [("zipvoice-vi", 24000), ("vieneu-v3-turbo", 16000)]
