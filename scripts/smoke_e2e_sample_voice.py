from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_CANDIDATE = "sample voice.weba"
DEFAULT_OUTPUT = ROOT / "data" / "outputs" / "sample-voice-e2e.wav"
DEFAULT_TEXT = "Xin ch\u00e0o, \u0111\u00e2y l\u00e0 b\u1ea3n ki\u1ec3m tra gi\u1ecdng n\u00f3i ti\u1ebfng Vi\u1ec7t."


class SmokeError(RuntimeError):
    pass


def main() -> int:
    configure_stdout()
    args = parse_args()
    base_url = args.base_url.rstrip("/")
    headers = auth_headers()

    print(f"base_url: {base_url}")
    check_health(base_url)
    check_model_status(base_url, headers)

    candidate = find_import_candidate(base_url, headers, args.candidate)
    print(f"candidate: {candidate['filename']} ({candidate['size_bytes']} bytes)")

    voice_id = import_voice(
        base_url,
        headers,
        filename=candidate["filename"],
        name=args.voice_name,
        reference_text=args.reference_text,
        auto_transcribe=not args.skip_auto_transcribe,
    )
    print(f"voice_id: {voice_id}")

    job_id: str | None = None
    try:
        job = create_tts_job(base_url, headers, voice_id, args.text, args.num_steps, args.speed)
        job_id = str(job["job_id"])
        completed = wait_for_tts_job(
            base_url,
            headers,
            job_id,
            timeout_seconds=args.timeout_seconds,
            interval_seconds=args.poll_interval,
        )
        output = download_tts_job_audio(base_url, headers, completed, args.output)
        print(f"generated: {output}")
        if not args.keep_job:
            delete_tts_job(base_url, headers, job_id)
            print(f"deleted_tts_job: {job_id}")
    finally:
        if not args.keep_voice:
            delete_voice(base_url, headers, voice_id)
            print(f"deleted_voice: {voice_id}")

    return 0


def configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def env_value(primary: str, legacy: str, default: str = "") -> str:
    return os.getenv(primary) or os.getenv(legacy) or default


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a real VassilStudio E2E smoke test with data/voices/sample voice.weba."
    )
    parser.add_argument(
        "--base-url",
        default=env_value("VASSIL_BASE_URL", "VVOICE_BASE_URL", DEFAULT_BASE_URL),
        help=f"VassilStudio API base URL. Defaults to {DEFAULT_BASE_URL}.",
    )
    parser.add_argument(
        "--candidate",
        default=env_value("VASSIL_E2E_CANDIDATE", "VVOICE_E2E_CANDIDATE", DEFAULT_CANDIDATE),
        help=f"Loose voice import candidate filename. Defaults to {DEFAULT_CANDIDATE}.",
    )
    parser.add_argument(
        "--voice-name",
        default=env_value("VASSIL_E2E_VOICE_NAME", "VVOICE_E2E_VOICE_NAME", "sample-voice-e2e"),
        help="Temporary imported voice name.",
    )
    parser.add_argument(
        "--text",
        default=env_value("VASSIL_E2E_TEXT", "VVOICE_E2E_TEXT", DEFAULT_TEXT),
        help="Vietnamese text to synthesize.",
    )
    parser.add_argument(
        "--reference-text",
        default=env_value("VASSIL_E2E_REFERENCE_TEXT", "VVOICE_E2E_REFERENCE_TEXT"),
        help="Optional manual reference text. Empty value uses ASR auto-transcription.",
    )
    parser.add_argument(
        "--skip-auto-transcribe",
        action="store_true",
        default=env_value("VASSIL_E2E_SKIP_AUTO_TRANSCRIBE", "VVOICE_E2E_SKIP_AUTO_TRANSCRIBE").lower()
        in {"1", "true", "yes"},
        help="Skip ASR auto-transcription and require --reference-text.",
    )
    parser.add_argument(
        "--num-steps",
        type=int,
        default=int(env_value("VASSIL_E2E_NUM_STEPS", "VVOICE_E2E_NUM_STEPS", "8")),
        help="ZipVoice generation steps. Defaults to the 8-step quality profile.",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=float(env_value("VASSIL_E2E_SPEED", "VVOICE_E2E_SPEED", "1.0")),
        help="ZipVoice speech speed.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=float(env_value("VASSIL_E2E_TIMEOUT_SECONDS", "VVOICE_E2E_TIMEOUT_SECONDS", "240")),
        help="Maximum wait time for the async TTS job.",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=float(env_value("VASSIL_E2E_POLL_INTERVAL", "VVOICE_E2E_POLL_INTERVAL", "2")),
        help="Polling interval for the async TTS job.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(env_value("VASSIL_E2E_OUTPUT", "VVOICE_E2E_OUTPUT", str(DEFAULT_OUTPUT))),
        help=f"Output WAV path. Defaults to {DEFAULT_OUTPUT}.",
    )
    parser.add_argument(
        "--keep-voice",
        action="store_true",
        default=env_value("VASSIL_E2E_KEEP_VOICE", "VVOICE_E2E_KEEP_VOICE").lower()
        in {"1", "true", "yes"},
        help="Keep the imported temporary voice profile after the smoke test.",
    )
    parser.add_argument(
        "--keep-job",
        action="store_true",
        default=env_value("VASSIL_E2E_KEEP_JOB", "VVOICE_E2E_KEEP_JOB").lower() in {"1", "true", "yes"},
        help="Keep the completed TTS job after the smoke test.",
    )
    return parser.parse_args()


def auth_headers() -> dict[str, str]:
    api_key = env_value("VASSIL_API_KEY", "VVOICE_API_KEY").strip()
    return {"X-Vassil-API-Key": api_key} if api_key else {}


def check_health(base_url: str) -> None:
    response = requests.get(f"{base_url}/health", timeout=10)
    response.raise_for_status()
    print("health:", response.json())


def check_model_status(base_url: str, headers: dict[str, str]) -> None:
    response = requests.get(f"{base_url}/model-status", headers=headers, timeout=10)
    response.raise_for_status()
    payload = response.json()
    print("model-status ready:", payload.get("ready"))
    if not payload.get("ready"):
        raise SmokeError(f"Model status is not ready: {payload}")


def find_import_candidate(
    base_url: str,
    headers: dict[str, str],
    filename: str,
) -> dict[str, Any]:
    response = requests.get(
        f"{base_url}/api/v1/voices/import-candidates",
        headers=headers,
        timeout=30,
    )
    response.raise_for_status()
    candidates = response.json()
    for candidate in candidates:
        if candidate.get("filename") == filename:
            return candidate

    available = ", ".join(candidate.get("filename", "") for candidate in candidates) or "none"
    raise SmokeError(f"Voice import candidate not found: {filename}. Available: {available}")


def import_voice(
    base_url: str,
    headers: dict[str, str],
    *,
    filename: str,
    name: str,
    reference_text: str,
    auto_transcribe: bool,
) -> str:
    if not auto_transcribe and not reference_text.strip():
        raise SmokeError("--reference-text is required when --skip-auto-transcribe is used")

    data = {
        "filename": filename,
        "name": name,
        "auto_transcribe": "true" if auto_transcribe else "false",
    }
    if reference_text.strip():
        data["reference_text"] = reference_text.strip()

    response = requests.post(
        f"{base_url}/api/v1/voices/import",
        headers=headers,
        data=data,
        timeout=240,
    )
    response.raise_for_status()
    payload = response.json()
    print("reference_text_source:", payload.get("reference_text_source"))
    print("reference_text:", payload.get("reference_text"))
    return str(payload["voice_id"])


def create_tts_job(
    base_url: str,
    headers: dict[str, str],
    voice_id: str,
    text: str,
    num_steps: int,
    speed: float,
) -> dict[str, Any]:
    response = requests.post(
        f"{base_url}/api/v1/tts/jobs/voices/{voice_id}",
        headers=headers,
        data={
            "text": text,
            "num_steps": str(num_steps),
            "speed": str(speed),
        },
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    print(f"tts_job: {payload['job_id']} status={payload['status']}")
    return payload


def wait_for_tts_job(
    base_url: str,
    headers: dict[str, str],
    job_id: str,
    *,
    timeout_seconds: float,
    interval_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
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
        time.sleep(interval_seconds)

    raise SmokeError(f"TTS job timed out after {timeout_seconds}s: {last_payload}")


def download_tts_job_audio(
    base_url: str,
    headers: dict[str, str],
    job: dict[str, Any],
    output: Path,
) -> Path:
    audio_url = job.get("audio_url")
    if not audio_url:
        raise SmokeError(f"Completed job has no audio_url: {job}")

    response = requests.get(f"{base_url}{audio_url}", headers=headers, timeout=60)
    response.raise_for_status()

    output = output if output.is_absolute() else ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(response.content)

    if output.stat().st_size == 0:
        raise SmokeError(f"Downloaded output is empty: {output}")
    return output


def delete_voice(base_url: str, headers: dict[str, str], voice_id: str) -> None:
    response = requests.delete(
        f"{base_url}/api/v1/voices/{voice_id}",
        headers=headers,
        timeout=30,
    )
    response.raise_for_status()


def delete_tts_job(base_url: str, headers: dict[str, str], job_id: str) -> None:
    response = requests.delete(
        f"{base_url}/api/v1/tts/jobs/{job_id}",
        headers=headers,
        timeout=30,
    )
    response.raise_for_status()


if __name__ == "__main__":
    raise SystemExit(main())
