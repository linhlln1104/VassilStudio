from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlsplit, urlunsplit

import numpy as np
import requests
import websockets

from vvoice.shared.audio.io import load_audio_bytes
from vvoice.shared.language import normalize_language


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_URL = "http://127.0.0.1:8000"
OUT_DIR = ROOT / "tmp" / "smoke" / "language-matrix"

LANGUAGE_CASES = {
    "vi": {
        "label": "Vietnamese",
        "text": (
            "Xin ch\u00e0o, \u0111\u00e2y l\u00e0 b\u00e0i ki\u1ec3m tra "
            "ti\u1ebfng Vi\u1ec7t c\u1ee7a Vassil Studio."
        ),
        "keywords": ["XIN", "CHAO", "TIENG", "VIET", "KIEM", "TRA"],
    },
    "en": {
        "label": "English",
        "text": "Hello, this is a clean English language model test for Vassil Studio.",
        "keywords": ["HELLO", "ENGLISH", "LANGUAGE", "MODEL", "TEST"],
    },
}


class SmokeError(RuntimeError):
    pass


def main() -> int:
    configure_stdout()
    args = parse_args()
    base_url = args.base_url.rstrip("/")
    api_key = env_value("VASSIL_API_KEY", "VVOICE_API_KEY").strip()
    headers = {"X-Vassil-API-Key": api_key} if api_key else {}
    languages = [normalize_language(item.strip()) for item in args.languages.split(",") if item.strip()]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"base_url: {base_url}")
    print(f"languages: {', '.join(languages)}")

    check_model_status(base_url, headers, languages)
    voices = list_voices(base_url, headers)

    for language in languages:
        if language not in LANGUAGE_CASES:
            raise SmokeError(f"Unsupported smoke language: {language}")
        run_language_case(base_url, headers, api_key, voices, language, args)

    print("Language matrix smoke passed")
    return 0


def configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def env_value(primary: str, legacy: str, default: str = "") -> str:
    return os.getenv(primary) or os.getenv(legacy) or default


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render and verify VI/EN Vassil Studio paths with matching ASR/TTS runtimes."
    )
    parser.add_argument(
        "--base-url",
        default=env_value("VASSIL_BASE_URL", "VVOICE_BASE_URL", DEFAULT_BASE_URL),
        help=f"Vassil Studio API base URL. Defaults to {DEFAULT_BASE_URL}.",
    )
    parser.add_argument(
        "--languages",
        default=env_value("VASSIL_LANGUAGE_MATRIX", "VVOICE_LANGUAGE_MATRIX", "vi,en"),
        help="Comma-separated languages to test. Defaults to vi,en.",
    )
    parser.add_argument(
        "--num-steps",
        type=int,
        default=int(env_value("VASSIL_LANGUAGE_MATRIX_NUM_STEPS", "VVOICE_LANGUAGE_MATRIX_NUM_STEPS", "16")),
        help="ZipVoice generation steps.",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=float(env_value("VASSIL_LANGUAGE_MATRIX_SPEED", "VVOICE_LANGUAGE_MATRIX_SPEED", "1.0")),
        help="ZipVoice speech speed.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=float(
            env_value("VASSIL_LANGUAGE_MATRIX_TIMEOUT_SECONDS", "VVOICE_LANGUAGE_MATRIX_TIMEOUT_SECONDS", "240")
        ),
        help="Maximum wait time per async TTS job.",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=float(
            env_value("VASSIL_LANGUAGE_MATRIX_POLL_INTERVAL", "VVOICE_LANGUAGE_MATRIX_POLL_INTERVAL", "2")
        ),
        help="Polling interval for async TTS jobs.",
    )
    parser.add_argument(
        "--skip-realtime",
        action="store_true",
        default=env_value("VASSIL_LANGUAGE_MATRIX_SKIP_REALTIME", "VVOICE_LANGUAGE_MATRIX_SKIP_REALTIME").lower()
        in {"1", "true", "yes"},
        help="Skip realtime websocket verification.",
    )
    parser.add_argument(
        "--keep-jobs",
        action="store_true",
        default=env_value("VASSIL_LANGUAGE_MATRIX_KEEP_JOBS", "VVOICE_LANGUAGE_MATRIX_KEEP_JOBS").lower()
        in {"1", "true", "yes"},
        help="Keep completed TTS jobs after downloading output audio.",
    )
    return parser.parse_args()


def check_model_status(base_url: str, headers: dict[str, str], languages: list[str]) -> None:
    response = requests.get(f"{base_url}/model-status", headers=headers, timeout=30)
    response.raise_for_status()
    payload = response.json()
    runtime = payload.get("runtime", {})
    asr_languages = {normalize_language(item) for item in runtime.get("asr_configured_languages", [])}
    tts_languages = {normalize_language(item) for item in runtime.get("tts_configured_languages", [])}

    print("model-status ready:", payload.get("ready"))
    print("asr languages:", sorted(asr_languages))
    print("tts languages:", sorted(tts_languages))

    if not payload.get("ready"):
        raise SmokeError(f"Model status is not ready: {payload}")
    for language in languages:
        if language not in asr_languages:
            raise SmokeError(f"ASR language is not configured: {language}")
        if language not in tts_languages:
            raise SmokeError(f"TTS language is not configured: {language}")


def list_voices(base_url: str, headers: dict[str, str]) -> list[dict[str, Any]]:
    response = requests.get(f"{base_url}/api/v1/voices", headers=headers, timeout=30)
    response.raise_for_status()
    voices = response.json()
    print("voices:", [f"{voice.get('name')}:{voice.get('language')}" for voice in voices])
    return voices


def run_language_case(
    base_url: str,
    headers: dict[str, str],
    api_key: str,
    voices: list[dict[str, Any]],
    language: str,
    args: argparse.Namespace,
) -> None:
    case = LANGUAGE_CASES[language]
    label = str(case["label"])
    text = str(case["text"])
    keywords = list(case["keywords"])
    voice = find_voice(voices, language)
    job_id: str | None = None

    print("")
    print(f"==> {label} ({language})")
    print(f"voice: {voice['name']} ({voice['voice_id']})")

    try:
        job = create_tts_job(base_url, headers, voice["voice_id"], language, text, args)
        job_id = str(job["job_id"])
        completed = wait_for_tts_job(base_url, headers, job_id, args)
        output = download_audio(base_url, headers, completed, language)
        transcript = transcribe_audio(base_url, headers, output, language)
        assert_keywords(f"{label} direct ASR", transcript, keywords)
        print(f"direct_asr: {transcript}")

        if not args.skip_realtime:
            realtime_text = asyncio.run(
                transcribe_realtime(base_url, api_key, output, language)
            )
            assert_keywords(f"{label} realtime ASR", realtime_text, keywords)
            print(f"realtime_asr: {realtime_text}")
    finally:
        if job_id and not args.keep_jobs:
            delete_tts_job(base_url, headers, job_id)
            print(f"deleted_tts_job: {job_id}")


def find_voice(voices: list[dict[str, Any]], language: str) -> dict[str, Any]:
    matching = [
        voice
        for voice in voices
        if normalize_language(str(voice.get("language", ""))) == language
    ]
    if matching:
        return sorted(matching, key=lambda voice: str(voice.get("created_at", "")))[-1]

    available = ", ".join(
        f"{voice.get('name')}:{voice.get('language')}" for voice in voices
    ) or "none"
    raise SmokeError(
        f"No saved voice profile found for language '{language}'. Available voices: {available}"
    )


def create_tts_job(
    base_url: str,
    headers: dict[str, str],
    voice_id: str,
    language: str,
    text: str,
    args: argparse.Namespace,
) -> dict[str, Any]:
    response = requests.post(
        f"{base_url}/api/v1/tts/jobs/voices/{voice_id}",
        headers=headers,
        data={
            "text": text,
            "language": language,
            "num_steps": str(args.num_steps),
            "speed": str(args.speed),
        },
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") != "queued":
        raise SmokeError(f"Expected queued TTS job, got {payload}")
    if normalize_language(payload.get("language")) != language:
        raise SmokeError(f"TTS job language mismatch: {payload}")
    print(f"tts_job: {payload['job_id']} status={payload['status']}")
    return payload


def wait_for_tts_job(
    base_url: str,
    headers: dict[str, str],
    job_id: str,
    args: argparse.Namespace,
) -> dict[str, Any]:
    deadline = time.monotonic() + args.timeout_seconds
    last_payload: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        response = requests.get(
            f"{base_url}/api/v1/tts/jobs/{job_id}",
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        last_payload = payload
        status = payload.get("status")
        print(f"tts_job_status: {status}")
        if status == "succeeded":
            return payload
        if status == "failed":
            raise SmokeError(f"TTS job failed: {payload.get('error')}")
        time.sleep(args.poll_interval)

    raise SmokeError(f"TTS job timed out after {args.timeout_seconds}s: {last_payload}")


def download_audio(
    base_url: str,
    headers: dict[str, str],
    job: dict[str, Any],
    language: str,
) -> Path:
    audio_url = job.get("audio_url")
    if not audio_url:
        raise SmokeError(f"Completed job has no audio_url: {job}")

    response = requests.get(f"{base_url}{audio_url}", headers=headers, timeout=60)
    response.raise_for_status()

    output = OUT_DIR / f"{language}-tts-output.wav"
    output.write_bytes(response.content)
    if output.stat().st_size == 0:
        raise SmokeError(f"Downloaded output is empty: {output}")
    print(f"generated: {output}")
    return output


def transcribe_audio(
    base_url: str,
    headers: dict[str, str],
    audio_path: Path,
    language: str,
) -> str:
    with audio_path.open("rb") as audio_file:
        response = requests.post(
            f"{base_url}/api/v1/asr/transcribe",
            headers=headers,
            data={"language": language},
            files={"audio": (audio_path.name, audio_file, "audio/wav")},
            timeout=180,
        )
    response.raise_for_status()
    payload = response.json()
    return str(payload.get("text", ""))


async def transcribe_realtime(
    base_url: str,
    api_key: str,
    audio_path: Path,
    language: str,
) -> str:
    url = realtime_url(base_url, language, api_key)
    transcripts: list[str] = []
    async with websockets.connect(url, max_size=8 * 1024 * 1024) as websocket:
        ready = json.loads(await asyncio.wait_for(websocket.recv(), timeout=30))
        if ready.get("type") != "ready":
            raise SmokeError(f"Expected ready realtime message, got {ready}")
        if normalize_language(ready.get("language")) != language:
            raise SmokeError(f"Realtime ready language mismatch: {ready}")

        sample_rate = int(ready["sample_rate"])
        samples, _ = load_audio_bytes(audio_path.read_bytes(), target_sample_rate=sample_rate)
        await websocket.send(np.asarray(samples, dtype="<f4").tobytes())
        await websocket.send(json.dumps({"type": "flush"}))

        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            message = json.loads(await asyncio.wait_for(websocket.recv(), timeout=30))
            if message.get("type") == "transcript" and message.get("text"):
                if normalize_language(message.get("language")) != language:
                    raise SmokeError(f"Realtime transcript language mismatch: {message}")
                transcripts.append(str(message["text"]))
            if message.get("type") == "flushed":
                break
        else:
            raise SmokeError("Realtime ASR did not flush")

    joined = " ".join(transcripts).strip()
    if not joined:
        raise SmokeError(f"Realtime ASR returned empty transcript for {language}")
    return joined


def realtime_url(base_url: str, language: str, api_key: str) -> str:
    parts = urlsplit(base_url)
    scheme = "wss" if parts.scheme == "https" else "ws"
    query = {"language": language}
    if api_key:
        query["api_key"] = api_key
    return urlunsplit((scheme, parts.netloc, "/api/v1/realtime/asr", urlencode(query), ""))


def assert_keywords(name: str, transcript: str, keywords: list[str]) -> None:
    normalized = normalize_for_match(transcript)
    hits = [keyword for keyword in keywords if keyword in normalized]
    if len(hits) < 2:
        raise SmokeError(
            f"{name} transcript did not contain enough expected words. "
            f"hits={hits}, transcript={transcript!r}"
        )


def normalize_for_match(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value)
    asciiish = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    return asciiish.upper()


def delete_tts_job(base_url: str, headers: dict[str, str], job_id: str) -> None:
    response = requests.delete(
        f"{base_url}/api/v1/tts/jobs/{job_id}",
        headers=headers,
        timeout=30,
    )
    response.raise_for_status()


if __name__ == "__main__":
    raise SystemExit(main())
