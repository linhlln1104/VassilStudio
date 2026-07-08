from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import statistics
import time
from urllib.parse import urlencode, urlsplit, urlunsplit

import numpy as np
import websockets


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_URL = "http://127.0.0.1:8000"
OUT_DIR = ROOT / "tmp" / "benchmarks"


async def benchmark(url: str, *, chunks: int, chunk_seconds: float, output: Path) -> None:
    async with websockets.connect(with_api_key(url), max_size=8 * 1024 * 1024) as websocket:
        ready = json.loads(await websocket.recv())
        sample_rate = int(ready["sample_rate"])

        await websocket.send(
            json.dumps(
                {
                    "type": "config",
                    "sample_rate": sample_rate,
                    "encoding": "pcm_f32le",
                    "chunk_seconds": chunk_seconds,
                    "silence_rms": 0.003,
                }
            )
        )
        configured = json.loads(await websocket.recv())
        if ready["type"] != "ready" or configured["type"] != "configured":
            raise RuntimeError(f"Unexpected websocket setup: ready={ready}, configured={configured}")

        runs = []
        samples = np.zeros(int(sample_rate * chunk_seconds), dtype=np.float32)
        for index in range(chunks):
            started = time.perf_counter()
            await websocket.send(samples.tobytes())
            segment = json.loads(await websocket.recv())
            elapsed_ms = (time.perf_counter() - started) * 1000
            if segment["type"] != "transcript":
                raise RuntimeError(f"Expected transcript message, got {segment}")
            runs.append(
                {
                    "iteration": index + 1,
                    "roundtrip_ms": round(elapsed_ms, 2),
                    "duration_seconds": segment.get("duration_seconds"),
                    "skipped": bool(segment.get("skipped")),
                    "rms": segment.get("rms"),
                }
            )
            print(f"Realtime chunk {index + 1}: {elapsed_ms:.2f} ms")

        await websocket.send(json.dumps({"type": "close"}))
        while True:
            message = json.loads(await websocket.recv())
            if message["type"] == "closed":
                break

    result = {
        "kind": "realtime_chunking",
        "url": url_without_query(url),
        "chunks": chunks,
        "chunk_seconds": chunk_seconds,
        "sample_rate": sample_rate,
        "summary": summarize([run["roundtrip_ms"] for run in runs]),
        "runs": runs,
    }
    write_json(output, result)
    print(f"Realtime benchmark written: {output}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark realtime ASR websocket chunk roundtrips.")
    parser.add_argument("--url", default=default_realtime_url())
    parser.add_argument("--chunks", type=int, default=5)
    parser.add_argument("--chunk-seconds", type=float, default=0.5)
    parser.add_argument("--output", type=Path, default=OUT_DIR / "realtime_chunking.json")
    args = parser.parse_args()

    if args.chunks <= 0:
        raise ValueError("--chunks must be greater than zero")
    if args.chunk_seconds <= 0:
        raise ValueError("--chunk-seconds must be greater than zero")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    asyncio.run(benchmark(args.url, chunks=args.chunks, chunk_seconds=args.chunk_seconds, output=args.output))


def default_realtime_url() -> str:
    explicit = (os.getenv("VASSIL_REALTIME_URL") or os.getenv("VVOICE_REALTIME_URL") or "").strip()
    if explicit:
        return explicit

    base_url = (os.getenv("VASSIL_BASE_URL") or os.getenv("VVOICE_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
    parts = urlsplit(base_url)
    scheme = "wss" if parts.scheme == "https" else "ws"
    return urlunsplit((scheme, parts.netloc, "/api/v1/realtime/asr", "", ""))


def with_api_key(url: str) -> str:
    api_key = (os.getenv("VASSIL_API_KEY") or os.getenv("VVOICE_API_KEY") or "").strip()
    if not api_key:
        return url

    parts = urlsplit(url)
    separator = "&" if parts.query else ""
    query = f"{parts.query}{separator}{urlencode({'api_key': api_key})}"
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


def url_without_query(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", parts.fragment))


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
