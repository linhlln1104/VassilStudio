from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import requests
import soundfile as sf


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = (os.getenv("VASSIL_BASE_URL") or os.getenv("VVOICE_BASE_URL") or "http://127.0.0.1:8000").rstrip("/")
API_KEY = (os.getenv("VASSIL_API_KEY") or os.getenv("VVOICE_API_KEY") or "").strip()
HEADERS = {"X-Vassil-API-Key": API_KEY} if API_KEY else {}
OUT_DIR = ROOT / "tmp" / "smoke"
REFERENCE_WAV = OUT_DIR / "voice-reference.wav"
DOWNLOADED_WAV = OUT_DIR / "voice-reference-downloaded.wav"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    write_reference_wav(REFERENCE_WAV)

    voice_id = create_voice()
    try:
        update_voice(voice_id)
        profile = get_voice(voice_id)
        download_reference_audio(profile)
    finally:
        delete_voice(voice_id)

    print(f"Voice smoke passed: voice_id={voice_id}, downloaded={DOWNLOADED_WAV}")


def write_reference_wav(path: Path) -> None:
    sample_rate = 24000
    t = np.arange(sample_rate, dtype=np.float32) / sample_rate
    samples = (0.03 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    sf.write(path, samples, sample_rate, subtype="PCM_16")


def create_voice() -> str:
    with REFERENCE_WAV.open("rb") as audio_file:
        response = requests.post(
            f"{BASE_URL}/api/v1/voices",
            headers=HEADERS,
            data={"name": "voice-smoke-test", "reference_text": "xin chao"},
            files={"reference_audio": ("reference.wav", audio_file, "audio/wav")},
            timeout=60,
        )

    response.raise_for_status()
    payload = response.json()
    voice_id = payload["voice_id"]
    if "reference_audio_url" not in payload:
        raise RuntimeError(f"Voice response missing reference_audio_url: {payload}")
    return voice_id


def get_voice(voice_id: str) -> dict:
    response = requests.get(
        f"{BASE_URL}/api/v1/voices/{voice_id}",
        headers=HEADERS,
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if payload["voice_id"] != voice_id:
        raise RuntimeError(f"Unexpected voice payload: {payload}")
    return payload


def update_voice(voice_id: str) -> None:
    response = requests.patch(
        f"{BASE_URL}/api/v1/voices/{voice_id}",
        headers=HEADERS,
        data={"name": "voice-smoke-updated", "reference_text": "xin chao da sua"},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if payload["name"] != "voice-smoke-updated":
        raise RuntimeError(f"Voice update failed: {payload}")
    if payload["reference_text"] != "xin chao da sua":
        raise RuntimeError(f"Voice reference text update failed: {payload}")


def download_reference_audio(profile: dict) -> None:
    response = requests.get(
        f"{BASE_URL}{profile['reference_audio_url']}",
        headers=HEADERS,
        timeout=30,
    )
    response.raise_for_status()
    content_type = response.headers.get("content-type", "")
    if "audio" not in content_type:
        raise RuntimeError(f"Expected audio response, got content-type={content_type}")

    DOWNLOADED_WAV.write_bytes(response.content)
    if DOWNLOADED_WAV.stat().st_size == 0:
        raise RuntimeError("Downloaded reference audio is empty")


def delete_voice(voice_id: str) -> None:
    response = requests.delete(
        f"{BASE_URL}/api/v1/voices/{voice_id}",
        headers=HEADERS,
        timeout=30,
    )
    response.raise_for_status()


if __name__ == "__main__":
    main()
