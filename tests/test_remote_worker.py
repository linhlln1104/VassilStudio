import json
from types import SimpleNamespace

import numpy as np
import pytest

from vvoice.core.errors import ModelConfigurationError
from vvoice.core.observability import reset_request_id, set_request_id
from vvoice.inference.remote import (
    RemoteAsrService, RemoteTtsService, WorkerControlServer, WorkerControlStore,
)
from vvoice.shared.audio.io import encode_wav, load_audio_bytes
from vvoice.shared.jobs.durable import FileLock
from vvoice.shared.security.principal import Principal, reset_current_principal, set_current_principal


class MetadataTts:
    def __init__(self):
        self.closed = False

    def model_catalog(self):
        return {"default_models": {"vi": "voice-vi", "en": "voice-en"}, "models": [
            {"model_id": name, "languages": [language], "status": "available",
             "ready": True, "loaded": False, "message": "Ready to load"}
            for name, language in (("voice-vi", "vi"), ("voice-en", "en"))
        ]}

    def resolve_parameters(self, language=None, model_id=None, num_steps=None, speed=None):
        return {"model_id": model_id or "voice-vi", "language": language or "vi",
                "num_steps": num_steps or 8, "speed": speed or 1.0,
                "deployment_version": "frozen-v1"}

    def readiness_checks(self):
        return {"model_assets": True}

    def synthesize(self, **_):
        raise AssertionError("API must never run inference")

    def warmup(self, *_args, **_kwargs):
        raise AssertionError("API must never load a model")

    def resolve_model_id(self, *_args, **_kwargs):
        raise AssertionError("Worker must resolve a model-only warmup language")

    def close(self):
        self.closed = True


class WorkerTts(MetadataTts):
    def __init__(self):
        super().__init__()
        self.loaded = set()
        self.calls = []

    def warmup(self, language=None, model_id=None):
        self.calls.append(("warmup", language, model_id))
        self.loaded.add(model_id or "voice-vi")

    def warmup_all(self):
        self.loaded.update(("voice-vi", "voice-en"))

    def unload(self, model_id):
        self.calls.append(("unload", model_id))
        self.loaded.discard(model_id)

    def model_catalog(self):
        catalog = super().model_catalog()
        for model in catalog["models"]:
            if model["model_id"] in self.loaded:
                model.update(loaded=True, status="loaded")
        return catalog


class WorkerAsr:
    def __init__(self):
        self._settings = SimpleNamespace(default_language="vi")
        self.loaded_languages = ()

    def sample_rate_for(self, language=None):
        return 16000

    def warmup(self, language=None):
        self.loaded_languages = (language or "vi",)

    def warmup_all(self):
        self.loaded_languages = ("en", "vi")


class ResultQueue:
    def __init__(self, directory, *, complete=True):
        self.directory = directory
        self.complete = complete
        self.calls = []
        self.cancelled = []

    def create_from_snapshot(self, **kwargs):
        self.calls.append(kwargs)
        output = self.directory / "generated.wav"
        output.write_bytes(encode_wav(np.sin(np.arange(2400) * 0.1).astype(np.float32) * 0.2, 24000))
        self.result = SimpleNamespace(job_id="job", status="succeeded" if self.complete else "queued",
                                      output_path=output, sample_rate=24000, duration_seconds=0.1)
        return self.result

    def create_from_audio(self, **kwargs):
        self.calls.append(kwargs)
        self.result = SimpleNamespace(job_id="asr-job", status="succeeded" if self.complete else "queued",
                                      text="recognized", sample_rate=16000, segments=())
        return self.result

    def get(self, _job_id):
        return self.result

    def cancel(self, job_id):
        self.cancelled.append(job_id)
        self.result.status = "cancelled"


@pytest.fixture
def control(tmp_path):
    store = WorkerControlStore(tmp_path / "control.sqlite3")
    worker_tts, worker_asr = WorkerTts(), WorkerAsr()
    server = WorkerControlServer(store, worker_tts, worker_asr)
    server.start()
    try:
        yield SimpleNamespace(store=store, server=server, tts=worker_tts, asr=worker_asr)
    finally:
        server.shutdown()


def test_warmup_unload_and_status_are_worker_owned_including_english_id(control, tmp_path):
    local = MetadataTts()
    remote = RemoteTtsService(local, ResultQueue(tmp_path), control.store, timeout_seconds=2)
    remote.warmup(model_id="voice-en")
    assert control.tts.calls == [("warmup", None, "voice-en")]
    assert remote.loaded_languages == ("en",)
    assert remote.is_loaded
    remote.unload("voice-en")
    assert not remote.is_loaded
    remote.close()
    assert local.closed
    assert control.store.status()["online"]
    assert not control.tts.closed


def test_direct_tts_queues_snapshot_and_preserves_actor_without_local_inference(control, tmp_path):
    queue = ResultQueue(tmp_path)
    remote = RemoteTtsService(MetadataTts(), queue, control.store, timeout_seconds=2)
    token = set_current_principal(Principal("integration", "App", "api_key", "operator", ("tts:write",)))
    try:
        result = remote.synthesize(text="Hello", reference_audio=np.ones(100, dtype=np.float32) * 0.1,
                                   reference_sample_rate=16000, reference_text="Reference", language="en",
                                   model_id="voice-en")
    finally:
        reset_current_principal(token)
    call = queue.calls[0]
    assert call["actor_id"] == "integration"
    assert call["provenance"]["deployment_version"] == "frozen-v1"
    assert call["voice_id"].startswith("direct-")
    reference, rate = load_audio_bytes(call["reference_bytes"])
    assert rate == 16000 and reference.size == 100
    assert result.sample_rate == 24000 and result.samples.size == 2400


def test_remote_asr_uses_durable_audio_job_and_control(control, tmp_path):
    local = WorkerAsr()
    queue = ResultQueue(tmp_path)
    remote = RemoteAsrService(local, queue, control.store, timeout_seconds=2)
    result = remote.transcribe(np.ones(160, dtype=np.float32) * 0.1, 16000, "en")
    assert result.text == "recognized"
    assert queue.calls[0]["language"] == "en"
    remote.warmup("en")
    assert remote.loaded_languages == ("en",)
    assert local.loaded_languages == ()


def test_direct_request_timeout_cancels_job_with_bounded_wait(control, tmp_path):
    queue = ResultQueue(tmp_path, complete=False)
    remote = RemoteTtsService(MetadataTts(), queue, control.store, timeout_seconds=0.02)
    with pytest.raises(ModelConfigurationError, match="cancellation requested"):
        remote.synthesize(text="Hello", reference_audio=np.ones(100, dtype=np.float32),
                          reference_sample_rate=16000, reference_text="Reference")
    assert queue.cancelled == ["job"]


def test_offline_or_stale_heartbeat_never_reports_resident_models(tmp_path):
    store = WorkerControlStore(tmp_path / "control.sqlite3")
    local, queue = MetadataTts(), ResultQueue(tmp_path)
    remote = RemoteTtsService(local, queue, store)
    with pytest.raises(ModelConfigurationError, match="offline"):
        remote.warmup()
    store.publish({"online": True, "tts_catalog": {"models": [
        {"model_id": "voice-vi", "loaded": True, "status": "loaded"},
    ]}})
    assert remote.is_loaded
    with store.connection() as db:
        row = json.loads(db.execute("SELECT payload FROM runtime WHERE id=1").fetchone()[0])
        row["updated_at"] = 0
        db.execute("UPDATE runtime SET payload=? WHERE id=1", (json.dumps(row),))
    assert not remote.is_loaded
    assert not remote.readiness_checks()["tts_worker_online"]
    assert remote.model_catalog()["models"][0]["status"] == "worker_offline"
    assert not queue.calls


def test_expired_controls_are_not_executed_and_crashed_controls_not_replayed(tmp_path):
    store = WorkerControlStore(tmp_path / "control.sqlite3")
    expired = store.submit("tts", "warmup", {"model_id": "voice-vi"}, timeout_seconds=-1)
    assert store.claim() is None
    assert store.get(expired)["status"] == "expired"
    running = store.submit("tts", "unload", {"model_id": "voice-vi"})
    assert store.claim()["command_id"] == running
    reopened = WorkerControlStore(store.path)
    reopened.recover()
    assert reopened.get(running)["status"] == "failed"
    assert reopened.claim() is None
    with pytest.raises(ModelConfigurationError, match="Unsupported"):
        store.submit("tts", "__getattribute__", {"name": "danger"})


def test_only_one_control_worker_can_publish_heartbeat(control):
    other = WorkerControlServer(WorkerControlStore(control.store.path), WorkerTts(), WorkerAsr())
    with pytest.raises(RuntimeError, match="already owns"):
        other.start()
    assert control.store.status()["online"]
    other.shutdown()


def test_cli_takes_host_lock_before_constructing_either_queue(tmp_path, monkeypatch):
    from vvoice import worker
    from vvoice.core import config, container, observability
    settings = SimpleNamespace(storage=SimpleNamespace(data_dir=tmp_path),
                               runtime=SimpleNamespace(debug=False, log_level="INFO"))
    monkeypatch.setenv("VASSIL_WORKER_MODE", "external")
    monkeypatch.setattr(config, "load_settings", lambda _: settings)
    monkeypatch.setattr(observability, "configure_logging", lambda **_: None)
    calls = []
    monkeypatch.setattr(container, "AppContainer", lambda _: calls.append("constructed"))
    lock = FileLock(tmp_path / ".worker-host.lock")
    assert lock.acquire(blocking=False)
    try:
        with pytest.raises(RuntimeError, match="already owns"):
            worker.main([])
        assert not calls
    finally:
        lock.release()


def test_worker_control_records_actor_and_request_metadata(control):
    token = set_current_principal(Principal("operator", "Operator", "user", "operator", ("models:manage",)))
    request_token = set_request_id("model-control-request")
    try:
        command_id = control.store.submit("tts", "warmup", {"model_id": "voice-vi"})
    finally:
        reset_current_principal(token)
        reset_request_id(request_token)
    control.store.wait(command_id, timeout_seconds=2)
    command = control.store.get(command_id)
    assert command["actor_id"] == "operator"
    assert command["request_id"] == "model-control-request"
    assert command["status"] == "succeeded"
