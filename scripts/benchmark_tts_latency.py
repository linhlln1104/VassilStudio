from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import statistics
import time

import numpy as np
import requests
import soundfile as sf


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = (os.getenv("VASSIL_BASE_URL") or os.getenv("VVOICE_BASE_URL") or "http://127.0.0.1:8000").rstrip("/")
API_KEY = (os.getenv("VASSIL_API_KEY") or os.getenv("VVOICE_API_KEY") or "").strip()
HEADERS = {"X-Vassil-API-Key": API_KEY} if API_KEY else {}
OUT_DIR = ROOT / "tmp" / "benchmarks"
REFERENCE_WAV = OUT_DIR / "tts_latency_reference.wav"


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark direct TTS latency against a running API.")
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument("--language", default="vi")
    parser.add_argument("--num-steps", type=int, default=8)
    parser.add_argument("--text", default="xin chao, day la benchmark ngan cua VassilStudio")
    parser.add_argument("--output", type=Path, default=OUT_DIR / "tts_latency.json")
    args = parser.parse_args()

    if args.iterations <= 0:
        raise ValueError("--iterations must be greater than zero")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    write_reference_wav(REFERENCE_WAV)
    assert_ready_for_tts(args.language)

    voice_id = create_voice(args.language)
    try:
        runs = []
        for index in range(args.iterations):
            elapsed_ms, headers, audio_size = synthesize(voice_id, args.text, args.language, args.num_steps)
            runs.append(
                {
                    "iteration": index + 1,
                    "latency_ms": round(elapsed_ms, 2),
                    "audio_bytes": audio_size,
                    "sample_rate": header_number(headers, "X-Vassil-Sample-Rate"),
                    "duration_seconds": header_number(headers, "X-Vassil-Duration-Seconds"),
                }
            )
            print(f"TTS iteration {index + 1}: {elapsed_ms:.2f} ms")
    finally:
        delete_voice(voice_id)

    result = {
        "kind": "tts_latency",
        "base_url": BASE_URL,
        "language": args.language,
        "num_steps": args.num_steps,
        "text_chars": len(args.text),
        "iterations": args.iterations,
        "summary": summarize([run["latency_ms"] for run in runs]),
        "runs": runs,
    }
    write_json(args.output, result)
    print(f"TTS benchmark written: {args.output}")


def write_reference_wav(path: Path) -> None:
    sample_rate = 24000
    t = np.arange(sample_rate * 2, dtype=np.float32) / sample_rate
    samples = (0.03 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    sf.write(path, samples, sample_rate, subtype="PCM_16")


def assert_ready_for_tts(language: str) -> None:
    response = requests.get(f"{BASE_URL}/model-status", headers=HEADERS, timeout=30)
    response.raise_for_status()
    payload = response.json()
    configured = payload["runtime"]["tts_configured_languages"]
    if language not in configured:
        raise RuntimeError(f"TTS language {language!r} is not configured. Available: {configured}")


def create_voice(language: str) -> str:
    with REFERENCE_WAV.open("rb") as audio_file:
        response = requests.post(
            f"{BASE_URL}/api/v1/voices",
            headers=HEADERS,
            data={
                "name": "tts-latency-benchmark",
                "language": language,
                "reference_text": "xin chao" if language == "vi" else "hello",
            },
            files={"reference_audio": ("reference.wav", audio_file, "audio/wav")},
            timeout=180,
        )
    response.raise_for_status()
    return response.json()["voice_id"]


def synthesize(voice_id: str, text: str, language: str, num_steps: int) -> tuple[float, dict, int]:
    started = time.perf_counter()
    response = requests.post(
        f"{BASE_URL}/api/v1/tts/synthesize/voices/{voice_id}",
        headers=HEADERS,
        data={
            "text": text,
            "language": language,
            "num_steps": str(num_steps),
        },
        timeout=300,
    )
    elapsed_ms = (time.perf_counter() - started) * 1000
    response.raise_for_status()
    return elapsed_ms, dict(response.headers), len(response.content)


def delete_voice(voice_id: str) -> None:
    response = requests.delete(
        f"{BASE_URL}/api/v1/voices/{voice_id}",
        headers=HEADERS,
        timeout=30,
    )
    response.raise_for_status()


def header_number(headers: dict, name: str) -> float | int | None:
    value = headers.get(name) or headers.get(name.lower())
    if not value:
        return None
    parsed = float(value)
    return int(parsed) if parsed.is_integer() else round(parsed, 3)


def summarize(values: list[float]) -> dict[str, float]:
    sorted_values = sorted(values)
    p95_index = max(0, min(len(sorted_values) - 1, round((len(sorted_values) - 1) * 0.95)))
    return {
        "min_ms": round(min(values), 2),
        "mean_ms": round(statistics.fmean(values), 2),
        "p95_ms": round(sorted_values[p95_index], 2),
        "max_ms": round(max(values), 2),
    }


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    main()
