from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from scripts.export_openapi import export_openapi
from scripts.isolated_workspace import ROOT, STUDIO, isolated_environment
from scripts.smoke_auth import main as run_auth_smoke


def app_environment() -> dict[str, str]:
    return {
        key: value for key, value in os.environ.items()
        if key.startswith(("VASSIL_", "VVOICE_")) or key == "PYTHONPATH"
    }


@pytest.mark.parametrize("tool", ["openapi", "auth"])
def test_quality_tool_never_initializes_user_storage_and_restores_environment(
    monkeypatch, tmp_path: Path, tool: str,
) -> None:
    if tool == "auth" and not (STUDIO / "dist/index.html").is_file():
        pytest.skip("Auth product smoke requires the built Studio, as in scripts/check.ps1")
    import vvoice.main

    user_workspace = tmp_path / "user-workspace"
    active_job = user_workspace / "data/jobs/asr/active/metadata.json"
    active_job.parent.mkdir(parents=True)
    active_job.write_text(json.dumps({
        "job_id": "active", "status": "running", "filename": "input.wav",
        "created_at": "2026-09-22T00:00:00+00:00",
    }), encoding="utf-8")
    original_metadata = active_job.read_bytes()
    monkeypatch.setenv("VASSIL_ROOT", str(user_workspace))
    monkeypatch.setenv("VASSIL_CONFIG", str(ROOT / "config/vassil.example.json"))
    monkeypatch.setenv("VASSIL_AUTH_DB_PATH", str(user_workspace / "owner.sqlite3"))
    monkeypatch.setenv("VVOICE_API_KEYS", "user-secret-for-isolation-test")
    monkeypatch.setenv("VASSIL_WARMUP_ON_STARTUP", "true")
    before_environment = app_environment()
    real_container = vvoice.main.AppContainer
    initialized_roots = []

    def guarded_container(settings):
        # Check before construction so a regression cannot mutate actual repository storage.
        assert settings.root not in (ROOT, user_workspace)
        for field in settings.storage.__dataclass_fields__:
            assert getattr(settings.storage, field).is_relative_to(settings.root)
        assert settings.security.auth_db_path.is_relative_to(settings.root)
        assert not settings.runtime.warmup_on_startup
        assert not settings.asr.enabled and not settings.tts.enabled
        initialized_roots.append(settings.root)
        return real_container(settings)

    monkeypatch.setattr(vvoice.main, "AppContainer", guarded_container)
    if tool == "openapi":
        export_openapi(tmp_path / "openapi.json")
    else:
        run_auth_smoke()

    assert initialized_roots
    assert all(not directory.exists() for directory in initialized_roots)
    assert active_job.read_bytes() == original_metadata
    assert not (user_workspace / "owner.sqlite3").exists()
    assert app_environment() == before_environment


def test_isolated_environment_restores_host_overrides_when_tool_fails(
    monkeypatch, tmp_path: Path,
) -> None:
    monkeypatch.setenv("VASSIL_ROOT", "original-workspace")
    monkeypatch.setenv("VVOICE_CONFIG", "original-config")
    before_environment = app_environment()
    with pytest.raises(RuntimeError, match="simulated"):
        with isolated_environment(tmp_path):
            assert os.environ["VASSIL_ROOT"] == str(tmp_path)
            assert "VVOICE_CONFIG" not in os.environ
            raise RuntimeError("simulated tool failure")
    assert app_environment() == before_environment
