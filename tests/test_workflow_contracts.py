import time
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import numpy as np
import pytest

from vvoice.domains.asr.jobs import AsrJobService
from vvoice.domains.asr.router import router
from vvoice.domains.asr.service import Transcription
from vvoice.main import register_exception_handlers
from vvoice.shared.audio.io import encode_wav


class ContractAsr:
    def sample_rate_for(self, language):
        return 16000

    def transcribe(self, samples, sample_rate, language=None):
        return Transcription("Synthetic contract transcript", sample_rate)


@pytest.mark.parametrize("original_extension", ["wav", "mp3", "webm", "m4a"])
def test_retained_asr_audio_can_be_requeued_using_its_wav_download_name(tmp_path, original_extension):
    jobs = AsrJobService(tmp_path / "jobs", ContractAsr(), target_sample_rate=16000)
    app = FastAPI()
    app.state.container = SimpleNamespace(
        asr_jobs=jobs,
        settings=SimpleNamespace(limits=SimpleNamespace(max_upload_bytes=100000)),
    )
    register_exception_handlers(app)
    app.include_router(router, prefix="/asr")
    try:
        job = jobs.create_from_audio(
            audio_bytes=encode_wav(np.zeros(1600), 16000),
            filename=f"original.{original_extension}", language="vi",
        )
        deadline = time.monotonic() + 5
        while jobs.get(job.job_id).status == "queued" and time.monotonic() < deadline:
            time.sleep(0.01)
        with TestClient(app) as client:
            audio = client.get(f"/asr/jobs/{job.job_id}/audio")
            assert audio.status_code == 200
            assert audio.headers["content-type"] == "audio/wav"
            filename = f"{job.job_id}-input.wav"
            assert filename in audio.headers["content-disposition"]
            retry = client.post(
                "/asr/jobs", data={"language": "vi"},
                files={"audio": (filename, audio.content, "audio/wav")},
            )
            assert retry.status_code == 202
            assert retry.json()["filename"] == filename
            if original_extension != "wav":
                bad = client.post(
                    "/asr/jobs", data={"language": "vi"},
                    files={"audio": (job.filename, audio.content, "audio/wav")},
                )
                assert bad.status_code == 415
    finally:
        jobs.shutdown()
        jobs._executor.shutdown(wait=True)
