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
ASR_WAV = OUT_DIR / "asr_latency_input.wav"


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark direct ASR latency against a running API.")
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--language", default="vi")
    parser.add_argument("--duration-seconds", type=float, default=1.0)
    parser.add_argument("--output", type=Path, default=OUT_DIR / "asr_latency.json")
    args = parser.parse_args()

    if args.iterations <= 0:
        raise ValueError("--iterations must be greater than zero")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    write_probe_wav(ASR_WAV, duration_seconds=args.duration_seconds)
    assert_ready_for_asr(args.language)

    runs = []
    for index in range(args.iterations):
        elapsed_ms, payload = transcribe(args.language)
        runs.append(
            {
                "iteration": index + 1,
                "latency_ms": round(elapsed_ms, 2),
                "duration_seconds": payload.get("duration_seconds"),
                "sample_rate": payload.get("sample_rate"),
                "text_length": len(payload.get("text") or ""),
            }
        )
        print(f"ASR iteration {index + 1}: {elapsed_ms:.2f} ms")

    result = {
        "kind": "asr_latency",
        "base_url": BASE_URL,
        "language": args.language,
        "input_duration_seconds": args.duration_seconds,
        "iterations": args.iterations,
        "summary": summarize([run["latency_ms"] for run in runs]),
        "runs": runs,
    }
    write_json(args.output, result)
    print(f"ASR benchmark written: {args.output}")


def write_probe_wav(path: Path, *, duration_seconds: float) -> None:
    sample_rate = 16000
    frames = max(1, int(sample_rate * duration_seconds))
    t = np.arange(frames, dtype=np.float32) / sample_rate
    samples = (0.02 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    sf.write(path, samples, sample_rate, subtype="PCM_16")


def assert_ready_for_asr(language: str) -> None:
    response = requests.get(f"{BASE_URL}/model-status", headers=HEADERS, timeout=30)
    response.raise_for_status()
    payload = response.json()
    configured = payload["runtime"]["asr_configured_languages"]
    if language not in configured:
        raise RuntimeError(f"ASR language {language!r} is not configured. Available: {configured}")


def transcribe(language: str) -> tuple[float, dict]:
    with ASR_WAV.open("rb") as audio_file:
        started = time.perf_counter()
        response = requests.post(
            f"{BASE_URL}/api/v1/asr/transcribe",
            headers=HEADERS,
            data={"language": language},
            files={"audio": ("asr_latency_input.wav", audio_file, "audio/wav")},
            timeout=180,
        )
    elapsed_ms = (time.perf_counter() - started) * 1000
    response.raise_for_status()
    return elapsed_ms, response.json()


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
