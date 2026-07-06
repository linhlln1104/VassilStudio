from __future__ import annotations

import os
import time
from pathlib import Path

import numpy as np
import requests
import soundfile as sf


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = (os.getenv("VASSIL_BASE_URL") or os.getenv("VVOICE_BASE_URL") or "http://127.0.0.1:8000").rstrip("/")
API_KEY = (os.getenv("VASSIL_API_KEY") or os.getenv("VVOICE_API_KEY") or "").strip()
HEADERS = {"X-Vassil-API-Key": API_KEY} if API_KEY else {}
OUT_DIR = ROOT / "tmp" / "smoke"
REFERENCE_WAV = OUT_DIR / "tts-job-reference.wav"
GENERATED_WAV = OUT_DIR / "tts-job-generated.wav"
SMOKE_TEXT = "xin ch\u00e0o, \u0111\u00e2y l\u00e0 b\u1ea3n ki\u1ec3m tra ti\u1ebfng vi\u1ec7t"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    write_reference_wav(REFERENCE_WAV)

    voice_id = create_voice()
    job_id = None
    try:
        job_id = create_job(voice_id)
        job = wait_for_job(job_id)
        download_audio(job)
    finally:
        if job_id:
            delete_job(job_id)
        delete_voice(voice_id)

    print(f"TTS job smoke passed: job_id={job_id}, generated={GENERATED_WAV}")


def write_reference_wav(path: Path) -> None:
    sample_rate = 24000
    t = np.arange(sample_rate * 2, dtype=np.float32) / sample_rate
    samples = (0.03 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    sf.write(path, samples, sample_rate, subtype="PCM_16")


def create_voice() -> str:
    with REFERENCE_WAV.open("rb") as audio_file:
        response = requests.post(
            f"{BASE_URL}/api/v1/voices",
            headers=HEADERS,
            data={"name": "tts-job-smoke-test", "reference_text": "xin chao"},
            files={"reference_audio": ("reference.wav", audio_file, "audio/wav")},
            timeout=60,
        )
    response.raise_for_status()
    return response.json()["voice_id"]


def create_job(voice_id: str) -> str:
    response = requests.post(
        f"{BASE_URL}/api/v1/tts/jobs/voices/{voice_id}",
        headers=HEADERS,
        data={"text": SMOKE_TEXT, "language": "vi", "num_steps": "16"},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if payload["status"] != "queued":
        raise RuntimeError(f"Expected queued TTS job, got {payload}")
    return payload["job_id"]


def wait_for_job(job_id: str) -> dict:
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        response = requests.get(
            f"{BASE_URL}/api/v1/tts/jobs/{job_id}",
            headers=HEADERS,
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        if payload["status"] == "succeeded":
            return payload
        if payload["status"] == "failed":
            raise RuntimeError(f"TTS job failed: {payload.get('error')}")
        time.sleep(1)
    raise TimeoutError(f"TTS job did not finish: {job_id}")


def download_audio(job: dict) -> None:
    response = requests.get(f"{BASE_URL}{job['audio_url']}", headers=HEADERS, timeout=60)
    response.raise_for_status()
    GENERATED_WAV.write_bytes(response.content)
    if GENERATED_WAV.stat().st_size == 0:
        raise RuntimeError("Generated TTS job audio is empty")


def delete_job(job_id: str) -> None:
    response = requests.delete(
        f"{BASE_URL}/api/v1/tts/jobs/{job_id}",
        headers=HEADERS,
        timeout=30,
    )
    response.raise_for_status()


def delete_voice(voice_id: str) -> None:
    response = requests.delete(
        f"{BASE_URL}/api/v1/voices/{voice_id}",
        headers=HEADERS,
        timeout=30,
    )
    response.raise_for_status()


if __name__ == "__main__":
    main()
