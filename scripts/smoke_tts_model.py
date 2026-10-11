"""Exercise a configured TTS model through the live API using a real voice reference.

The created voice and job are deliberately retained for inspection in Studio.
API authentication uses VASSIL_API_KEY (or the legacy VVOICE_API_KEY).
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from io import BytesIO
import json
import math
import os
from pathlib import Path
import re
import time
from urllib.parse import quote
import uuid

import numpy as np
import requests
import soundfile as sf


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--language", required=True, choices=("vi", "en"))
    parser.add_argument("--reference-wav", type=Path)
    reference = parser.add_mutually_exclusive_group()
    reference.add_argument("--reference-text")
    reference.add_argument("--reference-text-file", type=Path)
    text = parser.add_mutually_exclusive_group(required=True)
    text.add_argument("--text")
    text.add_argument("--text-file", type=Path)
    parser.add_argument("--voice-id", help="Reuse this saved voice without editing it")
    parser.add_argument("--acknowledge-warnings", action="store_true")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--base-url", default=(
        os.getenv("VASSIL_BASE_URL") or os.getenv("VVOICE_BASE_URL") or "http://127.0.0.1:8000"
    ))
    parser.add_argument("--timeout", type=float, default=900,
                        help="Total wall-clock budget in seconds, including warmup (default: 900)")
    args = parser.parse_args(argv)
    if not args.model_id.strip():
        parser.error("--model-id must not be empty")
    args.model_id = args.model_id.strip()
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--timeout must be a positive finite number")
    if args.voice_id:
        if args.reference_wav or args.reference_text is not None or args.reference_text_file:
            parser.error("Use --voice-id alone to reuse a reference, or supply a new WAV/transcript")
    elif not args.reference_wav or (args.reference_text is None and not args.reference_text_file):
        parser.error("A new voice requires --reference-wav and --reference-text[-file]")
    return args


def _text(value: str | None, filename: Path | None, label: str) -> str:
    value = filename.read_text(encoding="utf-8-sig") if filename else value
    if not value or not value.strip():
        raise ValueError(f"{label} must not be empty")
    return value.strip()


def audio_metrics(wav: bytes, expected_sample_rate: int) -> dict:
    with sf.SoundFile(BytesIO(wav)) as source:
        if source.format not in {"WAV", "WAVEX", "RF64"}:
            raise ValueError("Generated audio is not a WAV container")
        samples = source.read(dtype="float32", always_2d=True)
        rate = source.samplerate
    if samples.shape[1] != 1:
        raise ValueError("Generated audio must be mono")
    if rate != expected_sample_rate:
        raise ValueError(f"Expected {expected_sample_rate} Hz, received {rate} Hz")
    if not samples.size or not np.isfinite(samples).all():
        raise ValueError("Generated audio is empty or contains non-finite samples")
    duration = len(samples) / rate
    if not 0.2 < duration <= 120:
        raise ValueError(f"Generated duration {duration:.3f}s is outside (0.2, 120] seconds")
    samples = samples.astype(np.float64)
    peak = float(np.max(np.abs(samples)))
    rms = float(np.sqrt(np.mean(samples ** 2)))
    variation = float(np.std(samples))
    if peak <= 1e-4 or rms <= 1e-5 or variation <= 1e-5:
        raise ValueError("Generated audio is silent or constant")
    return {
        "sample_rate": rate, "channels": 1, "frames": len(samples),
        "duration_seconds": duration, "peak_amplitude": peak, "rms_amplitude": rms,
        "clipping_ratio": float(np.mean(np.abs(samples) >= 0.999)),
        "non_silent_fraction": float(np.mean(np.abs(samples) > 1e-4)),
        "finite": True, "byte_count": len(wav),
    }


def run_smoke(args, result: dict, session=None) -> dict:
    deadline = time.monotonic() + args.timeout
    session = session or requests.Session()
    api_key = (os.getenv("VASSIL_API_KEY") or os.getenv("VVOICE_API_KEY") or "").strip()
    headers = {"X-Vassil-API-Key": api_key} if api_key else {}
    base_url = args.base_url.rstrip("/")
    text = _text(args.text, args.text_file, "text")
    reference_text = None
    if not args.voice_id:
        reference_text = _text(args.reference_text, args.reference_text_file, "reference_text")
        info = sf.info(args.reference_wav)
        if info.format not in {"WAV", "WAVEX", "RF64"} or not info.frames:
            raise ValueError("--reference-wav must be a nonempty real speech WAV recording")

    def remaining():
        seconds = deadline - time.monotonic()
        if seconds <= 0:
            raise TimeoutError("Smoke test exceeded --timeout; saved server records are retained")
        return seconds

    def request(method, path, *, long=False, **kwargs):
        response = session.request(
            method, base_url + path, headers={**headers, **kwargs.pop("headers", {})},
            timeout=remaining() if long else min(30, remaining()), **kwargs,
        )
        if not response.ok:
            raise RuntimeError(f"{method} {path}: HTTP {response.status_code}: {response.text[:1000]}")
        remaining()
        return response

    def selected_model():
        catalog = request("GET", "/api/v1/tts/models").json()
        selected = next((item for item in catalog["models"]
                         if item["model_id"] == args.model_id), None)
        if selected is None:
            raise ValueError(f"Model {args.model_id!r} is absent from the server catalog")
        if args.language not in selected["languages"]:
            raise ValueError(f"Model {args.model_id!r} does not support {args.language}")
        if not selected["ready"]:
            raise RuntimeError(f"Model is not ready: {selected.get('message') or selected['status']}")
        return selected

    selected = selected_model()
    expected_rate = selected["sample_rate"]
    result["engine"] = selected["engine"]
    result["expected_sample_rate"] = expected_rate
    started = time.monotonic()
    request("POST", "/warmup/tts", long=True,
            params={"model_id": args.model_id, "language": args.language})
    if not selected_model()["loaded"]:
        raise RuntimeError("Selected model was not reported loaded after warmup")
    result["warmup_seconds"] = time.monotonic() - started

    if args.voice_id:
        voice = request("GET", "/api/v1/voices/" + quote(args.voice_id, safe="")).json()
        if voice["language"] != args.language:
            raise ValueError("Saved reference language differs from --language")
        result["voice_created"] = False
    else:
        with args.reference_wav.open("rb") as audio_file:
            voice = request(
                "POST", "/api/v1/voices", long=True,
                data={
                    "name": f"Model smoke {args.model_id[:24]} {result['run_id'][:8]}",
                    "language": args.language, "reference_text": reference_text,
                    "auto_transcribe": "false",
                    "acknowledge_warnings": str(args.acknowledge_warnings).lower(),
                },
                files={"reference_audio": (args.reference_wav.name, audio_file, "audio/wav")},
            ).json()
        result["voice_created"] = True
    result["voice_id"] = voice["voice_id"]
    key = "model-smoke-" + result["run_id"]
    path = "/api/v1/tts/jobs/voices/" + quote(voice["voice_id"], safe="")
    data = {"model_id": args.model_id, "language": args.language, "text": text}

    def check_job(job):
        if job["model_id"] != args.model_id or job["language"] != args.language:
            raise RuntimeError("Job did not preserve the explicitly selected model and language")

    started = time.monotonic()
    job = request("POST", path, data=data, headers={"Idempotency-Key": key}).json()
    result["job_id"] = job["job_id"]
    result["idempotency_key"] = key
    check_job(job)
    replay = request("POST", path, data=data, headers={"Idempotency-Key": key}).json()
    check_job(replay)
    if replay["job_id"] != job["job_id"]:
        raise RuntimeError("Idempotent replay unexpectedly created a different job")
    result["idempotent_replay_verified"] = True
    job_path = "/api/v1/tts/jobs/" + quote(job["job_id"], safe="")
    while True:
        job = request("GET", job_path).json()
        check_job(job)
        result["job_status"] = job["status"]
        if job["status"] in {"succeeded", "failed", "cancelled"}:
            break
        time.sleep(min(0.5, remaining()))
    result["job_seconds"] = time.monotonic() - started
    if job["status"] != "succeeded":
        raise RuntimeError(f"TTS job {job['status']}: {job.get('error')}")
    if job["sample_rate"] != expected_rate:
        raise RuntimeError("Completed job sample rate differs from the model catalog")
    wav = request("GET", job_path + "/audio", long=True).content
    Path(result["wav_path"]).write_bytes(wav)
    result["audio"] = audio_metrics(wav, expected_rate)
    result["status"] = "passed"
    return result


def main(argv=None) -> int:
    args = parse_args(argv)
    args.output_dir = args.output_dir.resolve()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    run_id = uuid.uuid4().hex
    stem = re.sub(r"[^A-Za-z0-9._-]", "_", args.model_id)[:64] + "-" + run_id[:8]
    report_path = args.output_dir / (stem + ".json")
    result = {
        "run_id": run_id, "model_id": args.model_id, "language": args.language,
        "started_at": datetime.now(timezone.utc).isoformat(), "status": "running",
        "report_path": str(report_path), "wav_path": str(args.output_dir / (stem + ".wav")),
    }
    started = time.monotonic()
    try:
        run_smoke(args, result)
    except (OSError, ValueError, RuntimeError, requests.RequestException) as exc:
        result.update(status="failed", error=str(exc))
    result["total_seconds"] = time.monotonic() - started
    encoded = json.dumps(result, ensure_ascii=False, indent=2)
    report_path.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
