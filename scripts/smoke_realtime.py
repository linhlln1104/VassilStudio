from __future__ import annotations

import argparse
import asyncio
import json
import os
from urllib.parse import urlencode, urlsplit, urlunsplit

import numpy as np
import websockets

DEFAULT_BASE_URL = "http://127.0.0.1:8000"


async def smoke(url: str) -> None:
    async with websockets.connect(url, max_size=8 * 1024 * 1024) as websocket:
        ready = json.loads(await websocket.recv())
        sample_rate = int(ready["sample_rate"])

        await websocket.send(
            json.dumps(
                {
                    "type": "config",
                    "sample_rate": sample_rate,
                    "encoding": "pcm_f32le",
                    "chunk_seconds": 0.5,
                    "silence_rms": 0.003,
                }
            )
        )
        configured = json.loads(await websocket.recv())

        samples = np.zeros(int(sample_rate * 0.6), dtype=np.float32)
        await websocket.send(samples.tobytes())
        segment = json.loads(await websocket.recv())

        await websocket.send(json.dumps({"type": "close"}))
        while True:
            message = json.loads(await websocket.recv())
            if message["type"] == "closed":
                break

        if ready["type"] != "ready":
            raise RuntimeError(f"Expected ready message, got {ready}")
        if configured["type"] != "configured":
            raise RuntimeError(f"Expected configured message, got {configured}")
        if segment["type"] != "transcript" or not segment.get("skipped"):
            raise RuntimeError(f"Expected skipped silence transcript, got {segment}")

        print(
            "Realtime smoke passed: "
            f"sample_rate={sample_rate}, "
            f"duration={segment['duration_seconds']:.2f}s, "
            f"rms={segment['rms']:.6f}"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--url",
        default=default_realtime_url(),
        help="Realtime ASR websocket URL",
    )
    args = parser.parse_args()
    asyncio.run(smoke(with_api_key(args.url)))


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
    query = parts.query
    separator = "&" if query else ""
    query = f"{query}{separator}{urlencode({'api_key': api_key})}"
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


if __name__ == "__main__":
    main()
