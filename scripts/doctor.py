from __future__ import annotations

import argparse
import importlib
import json
import platform
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

try:
    from scripts._path import bootstrap_backend_path
except ModuleNotFoundError:
    from _path import bootstrap_backend_path

bootstrap_backend_path()

from vvoice.core.config import load_settings  # noqa: E402
from vvoice.domains.tts.text_frontend import ZipVoiceTextFrontend  # noqa: E402


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


def dependency_checks() -> list[Check]:
    modules = [
        "fastapi",
        "librosa",
        "numpy",
        "sherpa_onnx",
        "soundfile",
        "uvicorn",
        "websockets",
        "onnxruntime",
        "torch",
        "torchaudio",
        "piper_phonemize",
        "phonemizer",
        "espeakng_loader",
    ]
    checks: list[Check] = []
    for module_name in modules:
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:
            checks.append(Check(f"dependency:{module_name}", False, str(exc)))
            continue

        version = getattr(module, "__version__", "installed")
        checks.append(Check(f"dependency:{module_name}", True, str(version)))
    return checks


def model_checks(config_path: str | None) -> list[Check]:
    settings = load_settings(config_path)
    paths = {
        "paths.models_root": settings.paths.models_root,
        "paths.data_root": settings.paths.data_root,
        "paths.logs_root": settings.paths.logs_root,
        "storage.data_dir": settings.storage.data_dir,
        "storage.voices_dir": settings.storage.voices_dir,
        "storage.asr_jobs_dir": settings.storage.asr_jobs_dir,
        "storage.tts_jobs_dir": settings.storage.tts_jobs_dir,
        "storage.uploads_dir": settings.storage.uploads_dir,
        "storage.outputs_dir": settings.storage.outputs_dir,
        "storage.logs_dir": settings.storage.logs_dir,
    }
    for language, model in settings.asr.models.items():
        prefix = f"asr.models.{language}"
        paths.update(
            {
                f"{prefix}.encoder": model.encoder,
                f"{prefix}.decoder": model.decoder,
                f"{prefix}.joiner": model.joiner,
                f"{prefix}.tokens": model.tokens,
            }
        )
    for language, model in settings.tts.models.items():
        prefix = f"tts.models.{language}"
        paths.update(
            {
                f"{prefix}.encoder": model.encoder,
                f"{prefix}.decoder": model.decoder,
                f"{prefix}.vocoder": model.vocoder,
                f"{prefix}.tokens": model.tokens,
                f"{prefix}.lexicon": model.lexicon,
                f"{prefix}.data_dir": model.data_dir,
            }
        )

    checks = [
        Check("runtime.provider", True, settings.runtime.provider),
        Check("runtime.num_threads", settings.runtime.num_threads > 0, str(settings.runtime.num_threads)),
        Check("jobs.asr_max_workers", settings.jobs.asr_max_workers > 0, str(settings.jobs.asr_max_workers)),
        Check("jobs.tts_max_workers", settings.jobs.tts_max_workers > 0, str(settings.jobs.tts_max_workers)),
        Check("realtime.encoding", settings.realtime.encoding in {"pcm_f32le", "pcm_s16le"}, settings.realtime.encoding),
        Check(
            "security.api_key_auth",
            True,
            "enabled" if settings.security.api_keys else "disabled",
        ),
    ]

    for name, path in paths.items():
        checks.append(path_check(name, path))

    for language, model in settings.tts.models.items():
        if language == "vi":
            tokens_ok, tokens_detail = zipvoice_token_check(model.tokens)
            checks.append(Check(f"tts.models.{language}.tokens.compatibility", tokens_ok, tokens_detail))

        if language in {"vi", "en"}:
            frontend_ok, frontend_detail = zipvoice_frontend_check(language, model)
            checks.append(Check(f"tts.models.{language}.text_frontend", frontend_ok, frontend_detail))

        if model.vocoder.name == "vocos_24khz.onnx":
            checks.append(Check(f"tts.models.{language}.vocoder.compatibility", True, model.vocoder.name))
        else:
            checks.append(
                Check(
                    f"tts.models.{language}.vocoder.compatibility",
                    False,
                    "Use vocos_24khz.onnx; this ZipVoice decoder emits 100-bin mel features",
                )
            )

    legacy_zipmodel = settings.root / "Zipmodel"
    checks.append(
        Check(
            "models.legacy_zipmodel",
            True,
            "present but not used by default config" if legacy_zipmodel.exists() else "not present",
        )
    )

    return checks


def zipvoice_frontend_check(language: str, model) -> tuple[bool, str]:
    try:
        text = "xin ch\u00e0o" if language == "vi" else "hello"
        phonemes = ZipVoiceTextFrontend().prepare(text, language=language, model_settings=model)
    except Exception as exc:
        return False, str(exc)

    if language == "vi" and text in phonemes:
        return False, f"text was not phonemized: {phonemes}"
    if language == "en" and "hello" in phonemes.lower():
        return False, f"text was not phonemized: {phonemes}"

    if "(en)" in phonemes or "(vi)" in phonemes:
        return False, f"language switch tags were not removed: {phonemes}"

    return True, phonemes.encode("unicode_escape").decode("ascii")


def path_check(name: str, path: Path) -> Check:
    if not path.exists():
        return Check(name, False, f"missing: {path}")
    if path.is_dir():
        return Check(name, True, f"dir: {path}")
    return Check(name, True, f"{path} ({path.stat().st_size / (1024 * 1024):.1f} MB)")


def zipvoice_token_check(path: Path) -> tuple[bool, str]:
    if not path.exists():
        return False, f"missing: {path}"

    tokens: list[str] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            if "\t" in line:
                token, _raw_id = line.rstrip("\n").split("\t", 1)
            else:
                parts = line.rsplit(" ", 1)
                if len(parts) != 2:
                    return False, f"malformed token line: {line!r}"
                token = parts[0]
            if not token:
                return False, f"malformed token line: {line!r}"
            tokens.append(token)
    except UnicodeDecodeError as exc:
        return False, f"tokens must be UTF-8: {exc}"

    if len(tokens) < 300:
        return (
            False,
            f"{len(tokens)} tokens; expected the 360-entry ZipVoice direct ONNX vocabulary",
        )

    required = {"_", " ", "\u02c8", "\u0283", "6"}
    missing = sorted(required - set(tokens))
    if missing:
        rendered = ", ".join(repr(token) for token in missing)
        return False, f"{len(tokens)} tokens but missing required symbols: {rendered}"

    pinyin_like = [token for token in tokens if re.search(r"[A-Za-z0-9]+[0-5]$", token)]
    return True, f"{len(tokens)} ZipVoice direct ONNX tokens; {len(pinyin_like)} pinyin-style entries"


def build_report(config_path: str | None) -> dict[str, Any]:
    checks = [
        Check("python", True, platform.python_version()),
        Check("platform", True, platform.platform()),
        *dependency_checks(),
        *model_checks(config_path),
    ]
    return {
        "ok": all(check.ok for check in checks),
        "checks": [asdict(check) for check in checks],
    }


def print_text_report(report: dict[str, Any]) -> None:
    for check in report["checks"]:
        marker = "OK" if check["ok"] else "FAIL"
        print(f"[{marker}] {check['name']}: {check['detail']}")

    if report["ok"]:
        print("VassilStudio doctor passed")
    else:
        print("VassilStudio doctor found issues")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", help="Path to a VassilStudio config JSON file")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    args = parser.parse_args()

    report = build_report(args.config)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_text_report(report)

    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
