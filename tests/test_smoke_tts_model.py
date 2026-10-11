from io import BytesIO
import json
from types import SimpleNamespace

import numpy as np
import pytest
import soundfile as sf

from scripts import smoke_tts_model as smoke


def wav_bytes(samples=None, sample_rate=24000):
    # Unit-test audio only: the live smoke CLI always requires a supplied speech recording.
    if samples is None:
        samples = np.random.default_rng(42).normal(0, 0.05, sample_rate // 2)
    buffer = BytesIO()
    sf.write(buffer, samples, sample_rate, format="WAV", subtype="FLOAT")
    return buffer.getvalue()


class FakeSession:
    def __init__(self, *, ready=True, replay_id="job-1"):
        self.ready, self.replay_id = ready, replay_id
        self.loaded = False
        self.requests = []
        self.creates = 0
        self.polls = 0

    def request(self, method, url, **kwargs):
        path = url.removeprefix("http://test")
        self.requests.append((method, path, kwargs))
        payload, content = {}, b""
        if path == "/api/v1/tts/models":
            payload = {"models": [{
                "model_id": "vieneu-v3-turbo", "engine": "vieneu", "languages": ["vi"],
                "sample_rate": 24000, "ready": self.ready, "loaded": self.loaded,
                "status": "available" if self.ready else "missing_assets", "message": None,
            }]}
        elif path == "/warmup/tts":
            assert kwargs["params"] == {"model_id": "vieneu-v3-turbo", "language": "vi"}
            self.loaded = True
        elif path in {"/api/v1/voices", "/api/v1/voices/voice-1"}:
            payload = {"voice_id": "voice-1", "language": "vi"}
        elif path == "/api/v1/tts/jobs/voices/voice-1":
            self.creates += 1
            payload = {
                "job_id": "job-1" if self.creates == 1 else self.replay_id,
                "model_id": kwargs["data"]["model_id"], "language": "vi", "status": "queued",
            }
        elif path == "/api/v1/tts/jobs/job-1":
            self.polls += 1
            payload = {
                "job_id": "job-1", "model_id": "vieneu-v3-turbo", "language": "vi",
                "status": "running" if self.polls == 1 else "succeeded", "sample_rate": 24000,
            }
        elif path == "/api/v1/tts/jobs/job-1/audio":
            content = wav_bytes()
        else:
            raise AssertionError(f"Unexpected request: {method} {path}")
        assert method in {"GET", "POST"}
        return SimpleNamespace(ok=True, json=lambda: payload, content=content)


def arguments(tmp_path, *, reuse=True):
    args = [
        "--model-id", "vieneu-v3-turbo", "--language", "vi", "--text", "Xin chào",
        "--output-dir", str(tmp_path), "--base-url", "http://test", "--timeout", "30",
    ]
    if reuse:
        args += ["--voice-id", "voice-1"]
    else:
        reference = tmp_path / "supplied-reference.wav"
        reference.write_bytes(wav_bytes())
        transcript = tmp_path / "reference.txt"
        transcript.write_text("\ufeffXin chào", encoding="utf-8")
        args += ["--reference-wav", str(reference), "--reference-text-file", str(transcript),
                 "--acknowledge-warnings"]
    return args


@pytest.mark.parametrize("reuse", [True, False])
def test_live_workflow_selects_exact_model_replays_and_retains_records(tmp_path, monkeypatch, reuse):
    args = smoke.parse_args(arguments(tmp_path, reuse=reuse))
    session = FakeSession()
    monkeypatch.setattr(smoke.time, "sleep", lambda _: None)
    result = {"run_id": "abc123", "wav_path": str(tmp_path / "output.wav")}
    smoke.run_smoke(args, result, session)
    assert result["status"] == "passed"
    assert result["voice_created"] is not reuse
    assert result["job_id"] == "job-1"
    assert result["idempotent_replay_verified"]
    assert result["audio"]["duration_seconds"] == 0.5
    assert (tmp_path / "output.wav").exists()
    creates = [request for request in session.requests if "/jobs/voices/" in request[1]]
    assert creates[0][2]["headers"]["Idempotency-Key"] == creates[1][2]["headers"]["Idempotency-Key"]
    assert all(request[2]["timeout"] <= 30 for request in session.requests)
    if not reuse:
        create = next(request for request in session.requests if request[1] == "/api/v1/voices")
        assert create[2]["data"]["name"].startswith("Model smoke vieneu-v3-turbo")
        assert create[2]["data"]["reference_text"] == "Xin chào"
        assert create[2]["data"]["acknowledge_warnings"] == "true"


def test_unready_model_does_not_start_inference_or_create_records(tmp_path):
    session = FakeSession(ready=False)
    with pytest.raises(RuntimeError, match="not ready"):
        smoke.run_smoke(smoke.parse_args(arguments(tmp_path)), {}, session)
    assert [(method, path) for method, path, _ in session.requests] == [
        ("GET", "/api/v1/tts/models"),
    ]


def test_broken_idempotency_is_reported_without_deleting_the_created_job(tmp_path):
    result = {"run_id": "abc123", "wav_path": str(tmp_path / "output.wav")}
    with pytest.raises(RuntimeError, match="different job"):
        smoke.run_smoke(smoke.parse_args(arguments(tmp_path)), result, FakeSession(replay_id="other"))
    assert result["job_id"] == "job-1"
    assert not (tmp_path / "output.wav").exists()


@pytest.mark.parametrize(("samples", "rate", "message"), [
    (np.zeros(12000), 24000, "silent"),
    (np.ones(12000) * 0.1, 24000, "constant"),
    (np.full(12000, np.nan), 24000, "non-finite"),
    (np.zeros((12000, 2)), 24000, "mono"),
    (np.zeros(4800), 24000, "duration"),
    (np.zeros(12000), 16000, "Expected 24000"),
])
def test_audio_verification_rejects_unusable_outputs(samples, rate, message):
    with pytest.raises(ValueError, match=message):
        smoke.audio_metrics(wav_bytes(samples, rate), 24000)


def test_polling_has_a_wall_clock_deadline(tmp_path, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(smoke.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(smoke.time, "sleep", lambda seconds: clock.__setitem__(0, 31.0))
    result = {"run_id": "abc123", "wav_path": str(tmp_path / "output.wav")}
    with pytest.raises(TimeoutError, match="--timeout"):
        smoke.run_smoke(smoke.parse_args(arguments(tmp_path)), result, FakeSession())
    assert result["job_id"] == "job-1"


def test_cli_persists_failure_report_and_identifies_retained_job(tmp_path, monkeypatch, capsys):
    def fail(_args, result):
        result["job_id"] = "retained-job"
        raise RuntimeError("Engine failed")

    monkeypatch.setattr(smoke, "run_smoke", fail)
    assert smoke.main(arguments(tmp_path)) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "failed"
    assert result["job_id"] == "retained-job"
    saved = json.loads(next(tmp_path.glob("*.json")).read_text(encoding="utf-8"))
    assert saved == result


def test_cli_requires_supplied_reference_when_not_reusing_voice(tmp_path):
    args = arguments(tmp_path)
    with pytest.raises(SystemExit):
        smoke.parse_args(args[:-2])
