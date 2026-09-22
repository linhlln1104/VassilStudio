from concurrent.futures import ThreadPoolExecutor
from importlib import import_module
import threading
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import numpy as np
import pytest

from vvoice.shared.audio.io import encode_wav


@pytest.mark.parametrize("domain", ["asr", "tts"])
def test_job_preparation_does_not_block_other_requests(domain, monkeypatch) -> None:
    router_module = import_module(f"vvoice.domains.{domain}.router")
    started = threading.Event()
    release = threading.Event()

    def prepare(**_):
        started.set()
        if not release.wait(5):
            raise RuntimeError("preparation blocked the event loop")
        return {"status": "queued"}

    container = SimpleNamespace(
        settings=SimpleNamespace(limits=SimpleNamespace(max_upload_bytes=100000)),
        asr_jobs=SimpleNamespace(create_from_audio=prepare),
        tts_jobs=SimpleNamespace(create_from_voice=prepare),
    )
    app = FastAPI()
    app.state.container = container
    if domain == "asr":
        app.add_api_route("/asr/jobs", router_module.create_asr_job, methods=["POST"])
    else:
        app.add_api_route(
            "/tts/jobs/voices/{voice_id}", router_module.create_tts_job_with_voice,
            methods=["POST"],
        )
    monkeypatch.setattr(router_module, "_job_response", lambda job: job)

    @app.get("/ping")
    async def ping():
        return {"alive": True}

    with TestClient(app) as client, ThreadPoolExecutor(max_workers=2) as pool:
        if domain == "asr":
            pending = pool.submit(
                client.post, "/asr/jobs", data={"language": "vi"},
                files={"audio": ("input.wav", encode_wav(np.zeros(1600), 16000), "audio/wav")},
            )
        else:
            pending = pool.submit(
                client.post, "/tts/jobs/voices/fixture", data={"text": "hello"},
            )
        try:
            assert started.wait(2), "preparation did not start"
            alive = pool.submit(client.get, "/ping")
            assert alive.result(timeout=2).json() == {"alive": True}
        finally:
            release.set()
        assert pending.result(timeout=2).json() == {"status": "queued"}
