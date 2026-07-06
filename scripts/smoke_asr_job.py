from __future__ import annotations

import os
import json
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
ASR_WAV = OUT_DIR / "asr-job-input.wav"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    write_probe_wav(ASR_WAV)

    job_id = create_job()
    try:
        job = wait_for_job(job_id)
    finally:
        delete_job(job_id)

    print(
        "ASR job smoke passed: "
        f"job_id={job_id}, "
        f"status={job['status']}, "
        f"text={json.dumps(job.get('text', ''), ensure_ascii=True)}"
    )


def write_probe_wav(path: Path) -> None:
    sample_rate = 16000
    t = np.arange(sample_rate, dtype=np.float32) / sample_rate
    samples = (0.02 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    sf.write(path, samples, sample_rate, subtype="PCM_16")


def create_job() -> str:
    with ASR_WAV.open("rb") as audio_file:
        response = requests.post(
            f"{BASE_URL}/api/v1/asr/jobs",
            headers=HEADERS,
            files={"audio": ("asr-job-input.wav", audio_file, "audio/wav")},
            timeout=60,
        )
    response.raise_for_status()
    payload = response.json()
    if payload["status"] != "queued":
        raise RuntimeError(f"Expected queued ASR job, got {payload}")
    return payload["job_id"]


def wait_for_job(job_id: str) -> dict:
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        response = requests.get(
            f"{BASE_URL}/api/v1/asr/jobs/{job_id}",
            headers=HEADERS,
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        if payload["status"] == "succeeded":
            return payload
        if payload["status"] == "failed":
            raise RuntimeError(f"ASR job failed: {payload.get('error')}")
        time.sleep(1)
    raise TimeoutError(f"ASR job did not finish: {job_id}")


def delete_job(job_id: str) -> None:
    response = requests.delete(
        f"{BASE_URL}/api/v1/asr/jobs/{job_id}",
        headers=HEADERS,
        timeout=30,
    )
    response.raise_for_status()


if __name__ == "__main__":
    main()
