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
REFERENCE_WAV = OUT_DIR / "reference.wav"
GENERATED_WAV = OUT_DIR / "generated.wav"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    write_reference_wav(REFERENCE_WAV)

    health = requests.get(f"{BASE_URL}/health", headers=HEADERS, timeout=10)
    health.raise_for_status()
    print("health:", health.json())

    status = requests.get(f"{BASE_URL}/model-status", headers=HEADERS, timeout=10)
    status.raise_for_status()
    model_status = status.json()
    print("model-status ready:", model_status["ready"])
    if not model_status["ready"]:
        raise RuntimeError(model_status)

    voice_id = create_voice()
    try:
        synthesize_with_voice(voice_id)
    finally:
        if not (os.getenv("VASSIL_KEEP_SMOKE_VOICE") or os.getenv("VVOICE_KEEP_SMOKE_VOICE")):
            delete_voice(voice_id)

    print(f"generated: {GENERATED_WAV}")


def write_reference_wav(path: Path) -> None:
    sample_rate = 24000
    t = np.arange(sample_rate * 2, dtype=np.float32) / sample_rate
    samples = (0.03 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    sf.write(path, samples, sample_rate, subtype="PCM_16")


def create_voice() -> str:
    data = {"name": "smoke-test"}
    if os.getenv("VASSIL_SMOKE_AUTO_TRANSCRIBE") or os.getenv("VVOICE_SMOKE_AUTO_TRANSCRIBE"):
        data["auto_transcribe"] = "true"
    else:
        data["reference_text"] = "xin chao"

    with REFERENCE_WAV.open("rb") as audio_file:
        response = requests.post(
            f"{BASE_URL}/api/v1/voices",
            headers=HEADERS,
            data=data,
            files={
                "reference_audio": ("reference.wav", audio_file, "audio/wav"),
            },
            timeout=180,
        )
    response.raise_for_status()
    payload = response.json()
    voice_id = payload["voice_id"]
    print("voice_id:", voice_id)
    print("reference_text_source:", payload.get("reference_text_source"))
    return voice_id


def synthesize_with_voice(voice_id: str) -> None:
    response = requests.post(
        f"{BASE_URL}/api/v1/tts/synthesize/voices/{voice_id}",
        headers=HEADERS,
        data={
            "text": "xin chào, đây là bản kiểm tra tiếng việt",
            "num_steps": "16",
        },
        timeout=180,
    )
    response.raise_for_status()
    GENERATED_WAV.write_bytes(response.content)
    print(
        "tts sample-rate:",
        response.headers.get("X-Vassil-Sample-Rate") or response.headers.get("X-VVoice-Sample-Rate"),
    )
    print(
        "tts duration:",
        response.headers.get("X-Vassil-Duration-Seconds")
        or response.headers.get("X-VVoice-Duration-Seconds"),
    )


def delete_voice(voice_id: str) -> None:
    response = requests.delete(
        f"{BASE_URL}/api/v1/voices/{voice_id}",
        headers=HEADERS,
        timeout=10,
    )
    response.raise_for_status()


if __name__ == "__main__":
    main()
