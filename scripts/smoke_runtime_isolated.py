"""Exercise installed VI/EN engines through the API using disposable synthetic data."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import time

import numpy as np
from fastapi.testclient import TestClient

try:
    from scripts._path import ROOT, bootstrap_backend_path
    from scripts.isolated_workspace import isolated_environment
except ModuleNotFoundError:
    from _path import ROOT, bootstrap_backend_path
    from isolated_workspace import isolated_environment

bootstrap_backend_path()

from vvoice.main import create_app  # noqa: E402
from vvoice.shared.audio.io import encode_wav, load_audio_bytes  # noqa: E402


def completed(client: TestClient, domain: str, job_id: str) -> dict:
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/{domain}/jobs/{job_id}")
        response.raise_for_status()
        payload = response.json()
        if payload["status"] in {"succeeded", "failed", "cancelled"}:
            if payload["status"] != "succeeded":
                raise RuntimeError(f"{domain} smoke job did not succeed: {payload['error']}")
            return payload
        time.sleep(0.1)
    raise TimeoutError(f"{domain} smoke job did not finish")


def main() -> None:
    summary = []
    with tempfile.TemporaryDirectory(prefix="vassil-runtime-smoke-") as temporary:
        workspace = Path(temporary)
        with isolated_environment(workspace, {
            "VASSIL_AUTH_REQUIRED": "true",
            "VASSIL_SESSION_SECRET": "isolated-runtime-smoke-secret-at-least-32-characters",
        }):
            config_path = workspace / "vassil.qa.json"
            config = json.loads(config_path.read_text(encoding="utf-8"))
            config["paths"]["models_root"] = str(ROOT / "models")
            for domain in ("asr", "tts"):
                config[domain]["enabled"] = True
                for model in config[domain]["models"].values():
                    for name in ("encoder", "decoder", "joiner", "tokens", "vocoder", "data_dir", "lexicon"):
                        if name in model:
                            model[name] = str(ROOT / model[name])
            config["realtime"]["enabled"] = True
            config_path.write_text(json.dumps(config), encoding="utf-8")

            app = create_app()
            try:
                with TestClient(app) as client:
                    client.post("/api/v1/auth/setup", json={
                        "username": "smoke-owner", "password": "isolated-smoke-password",
                    }).raise_for_status()
                    client.get("/readyz").raise_for_status()
                    for language, text, steps, frequency in (
                        ("vi", "Xin chào, đây là bài kiểm tra tiếng Việt.", 4, 220),
                        ("en", "Hello, this is an English language test.", 8, 240),
                    ):
                        reference = encode_wav(
                            0.05 * np.sin(2 * np.pi * frequency * np.arange(72000) / 24000), 24000,
                        )
                        fields = {"language": language, "reference_text": text}
                        files = {"reference_audio": ("reference.wav", reference, "audio/wav")}
                        review = client.post("/api/v1/voices/intake/analyze", data=fields, files=files)
                        review.raise_for_status()
                        assert review.json()["status"] != "blocked"
                        created = client.post("/api/v1/voices", files=files, data={
                            **fields, "name": f"Synthetic smoke {language}",
                            "reviewed_source_sha256": review.json()["source_sha256"],
                            "acknowledge_warnings": "true",
                        })
                        created.raise_for_status()
                        voice_id = created.json()["voice_id"]
                        started = time.perf_counter()
                        queued = client.post(f"/api/v1/tts/jobs/voices/{voice_id}", data={
                            "text": text, "language": language, "num_steps": str(steps),
                        }, headers={"Idempotency-Key": f"smoke-{language}"})
                        queued.raise_for_status()
                        tts_job = completed(client, "tts", queued.json()["job_id"])
                        generated = client.get(tts_job["audio_url"])
                        generated.raise_for_status()
                        samples, sample_rate = load_audio_bytes(generated.content)
                        assert sample_rate == 24000 and samples.size > 0
                        assert np.isfinite(samples).all() and np.abs(samples).max() > 0
                        rendered_seconds = round(time.perf_counter() - started, 2)
                        asr = client.post("/api/v1/asr/jobs", data={"language": language}, files={
                            "audio": ("generated.wav", generated.content, "audio/wav"),
                        })
                        asr.raise_for_status()
                        asr_job = completed(client, "asr", asr.json()["job_id"])
                        client.get(f"/api/v1/asr/jobs/{asr_job['job_id']}/exports/json").raise_for_status()
                        pcm, rate = load_audio_bytes(generated.content, 16000)
                        with client.websocket_connect(f"/api/v1/realtime/asr?language={language}") as ws:
                            assert ws.receive_json()["type"] == "ready"
                            ws.send_json({"type": "config", "chunk_seconds": 0.5})
                            assert ws.receive_json()["type"] == "configured"
                            for offset in range(0, len(pcm), rate // 2):
                                frame = pcm[offset:offset + rate // 2]
                                ws.send_bytes(frame.astype("<f4").tobytes())
                                if len(frame) == rate // 2:
                                    assert ws.receive_json()["type"] == "transcript"
                            ws.send_json({"type": "close"})
                            response = ws.receive_json()
                            if response["type"] == "transcript":
                                assert response["final"] is True
                                response = ws.receive_json()
                            assert response["type"] == "closed"
                        client.delete(f"/api/v1/voices/{voice_id}").raise_for_status()
                        replay = client.post(f"/api/v1/tts/jobs/voices/{voice_id}", data={
                            "text": text, "language": language, "num_steps": str(steps),
                        }, headers={"Idempotency-Key": f"smoke-{language}"})
                        replay.raise_for_status()
                        assert replay.json()["job_id"] == tts_job["job_id"]
                        summary.append({
                            "language": language, "steps": steps,
                            "audio_seconds": round(len(samples) / sample_rate, 3),
                            "tts_job_seconds": rendered_seconds,
                            "asr_text_nonempty": bool(asr_job["text"]),
                            "realtime_finalized": True, "idempotent_replay_after_voice_delete": True,
                        })
                        print(f"Runtime smoke {language}: passed", flush=True)
            finally:
                app.state.container.shutdown()
                app.state.container.asr_jobs._executor.shutdown(wait=True)
                app.state.container.tts_jobs._executor.shutdown(wait=True)
    output = ROOT / "artifacts/runtime-smoke/result.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"kind": "synthetic_pipeline_smoke", "runs": summary}, indent=2), encoding="utf-8")
    print(f"Runtime pipeline smoke passed; this is not a perceptual voice-quality evaluation. {output}")


if __name__ == "__main__":
    main()
