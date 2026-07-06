from __future__ import annotations

import os

import requests


BASE_URL = (os.getenv("VASSIL_BASE_URL") or os.getenv("VVOICE_BASE_URL") or "http://127.0.0.1:8000").rstrip("/")
API_KEY = (os.getenv("VASSIL_API_KEY") or os.getenv("VVOICE_API_KEY") or "").strip()
HEADERS = {"X-Vassil-API-Key": API_KEY} if API_KEY else {}
MAX_AGE_SECONDS = 315360000


def main() -> None:
    asr = cleanup_jobs("asr")
    tts = cleanup_jobs("tts")

    print(
        "Cleanup job smoke passed: "
        f"asr_deleted={asr['deleted']}, "
        f"tts_deleted={tts['deleted']}, "
        f"age_filter_seconds={MAX_AGE_SECONDS}"
    )


def cleanup_jobs(module: str) -> dict:
    response = requests.delete(
        f"{BASE_URL}/api/v1/{module}/jobs",
        headers=HEADERS,
        params={"max_age_seconds": str(MAX_AGE_SECONDS)},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if "deleted" not in payload or "job_ids" not in payload:
        raise RuntimeError(f"Unexpected cleanup payload for {module}: {payload}")
    return payload


if __name__ == "__main__":
    main()
