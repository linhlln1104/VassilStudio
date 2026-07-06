from __future__ import annotations

import os
import json
from pathlib import Path

import numpy as np
import requests
import soundfile as sf


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = (os.getenv("VASSIL_BASE_URL") or os.getenv("VVOICE_BASE_URL") or "http://127.0.0.1:8000").rstrip("/")
API_KEY = (os.getenv("VASSIL_API_KEY") or os.getenv("VVOICE_API_KEY") or "").strip()
HEADERS = {"X-Vassil-API-Key": API_KEY} if API_KEY else {}
OUT_DIR = ROOT / "tmp" / "smoke"
ASR_WAV = OUT_DIR / "asr_input.wav"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    write_probe_wav(ASR_WAV)

    with ASR_WAV.open("rb") as audio_file:
        response = requests.post(
            f"{BASE_URL}/api/v1/asr/transcribe",
            headers=HEADERS,
            files={"audio": ("asr_input.wav", audio_file, "audio/wav")},
            timeout=120,
        )
    response.raise_for_status()
    print("asr response:", json.dumps(response.json(), ensure_ascii=True))


def write_probe_wav(path: Path) -> None:
    sample_rate = 16000
    t = np.arange(sample_rate, dtype=np.float32) / sample_rate
    samples = (0.02 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    sf.write(path, samples, sample_rate, subtype="PCM_16")


if __name__ == "__main__":
    main()
