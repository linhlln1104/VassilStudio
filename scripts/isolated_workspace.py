"""Disposable application configuration shared by non-runtime quality tools."""

from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
from collections.abc import Iterator


ROOT = Path(__file__).resolve().parents[1]
STUDIO = ROOT / "frontend/studio-react"


def prepare_workspace(workspace: Path, inherited: dict[str, str]) -> dict[str, str]:
    config = json.loads((ROOT / "config/vassil.example.json").read_text(encoding="utf-8"))
    config["paths"] = {"models_root": "models", "data_root": "data", "logs_root": "logs"}
    config["storage"] = {
        "data_dir": "data", "voices_dir": "data/voices", "asr_jobs_dir": "data/jobs/asr",
        "tts_jobs_dir": "data/jobs/tts", "uploads_dir": "data/uploads",
        "outputs_dir": "data/outputs", "logs_dir": "logs",
    }
    config["security"].update({
        "api_keys": [], "auth_required": False, "auth_db_path": "data/auth.sqlite3",
        "session_secret": "", "secure_cookies": False,
    })
    for domain in ("asr", "tts", "realtime"):
        config[domain]["enabled"] = False
    config["runtime"]["warmup_on_startup"] = False
    config_path = workspace / "vassil.qa.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    environment = {
        key: value for key, value in inherited.items()
        if not key.startswith(("VASSIL_", "VVOICE_"))
    }
    environment.update({
        "PYTHONPATH": str(ROOT / "backend"),
        "VASSIL_ROOT": str(workspace),
        "VASSIL_CONFIG": str(config_path),
        "VASSIL_STUDIO_DIR": str(STUDIO / "dist"),
        "VASSIL_ENV": "development",
        "VASSIL_BIND_ADDRESS": "127.0.0.1",
        "VASSIL_AUTH_REQUIRED": "false",
        "VASSIL_LOG_LEVEL": "WARNING",
    })
    return environment


def _managed(name: str) -> bool:
    return name == "PYTHONPATH" or name.startswith(("VASSIL_", "VVOICE_"))


@contextmanager
def isolated_environment(
    workspace: Path, overrides: dict[str, str] | None = None,
) -> Iterator[None]:
    previous = {key: value for key, value in os.environ.items() if _managed(key)}
    environment = prepare_workspace(workspace, dict(os.environ))
    environment.update(overrides or {})
    try:
        for key in tuple(os.environ):
            if _managed(key):
                del os.environ[key]
        os.environ.update({key: value for key, value in environment.items() if _managed(key)})
        yield
    finally:
        for key in tuple(os.environ):
            if _managed(key):
                del os.environ[key]
        os.environ.update(previous)
