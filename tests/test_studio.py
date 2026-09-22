from __future__ import annotations

from pathlib import Path
import re
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from vvoice.app.auth.service import LocalAuthService
from vvoice.app.studio.router import STATIC_DIR, _resolve_studio_dir, _safe_static_path, router
from vvoice.core.config import SecuritySettings
from vvoice.main import register_request_middleware


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_studio_route_and_react_assets_are_registered() -> None:
    paths = {route.path for route in router.routes if hasattr(route, "path")}
    assert "/" in paths
    assert "/changelog" in paths
    assert "/support" in paths
    assert "/operations" in paths
    assert "/privacy" in paths
    assert "/license" in paths
    assert "/studio" in paths
    assert "/studio/assets" in paths
    assert "/studio/{path:path}" in paths

    page = STATIC_DIR.joinpath("index.html").read_text(encoding="utf-8")
    assert "VassilStudio" in page
    assert 'href="/studio/brand/vassil-mark.png"' in page
    assert 'src="/studio/assets/' in page
    assert 'href="/studio/assets/' in page
    for screenshot_name in (
        "vassil-studio-generate.png",
        "vassil-studio-transcribe.png",
        "vassil-studio-realtime.png",
        "vassil-studio-voices.png",
    ):
        assert STATIC_DIR.joinpath("brand", screenshot_name).is_file()
    assert not STATIC_DIR.joinpath("brand", "vassil-voice-sculpture.jpg").exists()

    asset_refs = sorted(set(re.findall(r'["\']\/studio\/assets\/([^"\']+)["\']', page)))
    assert asset_refs

    for asset_ref in asset_refs:
        assert STATIC_DIR.joinpath("assets", asset_ref).is_file()

    asset_dir = STATIC_DIR / "assets"
    scripts = [
        path.read_text(encoding="utf-8")
        for path in asset_dir.glob("*.js")
    ]
    styles = [
        path.read_text(encoding="utf-8")
        for path in asset_dir.glob("*.css")
    ]

    script = "\n".join(scripts)
    style = "\n".join(styles)

    assert "/api/v1/tts/jobs/voices/" in script
    assert "/api/v1/asr/jobs" in script
    assert "/api/v1/voices/import" in script
    assert "/api/v1/voices/" in script
    assert "/api/v1/auth/change-password" in script
    assert "PATCH" in script
    assert "DELETE" in script
    assert "/model-status" in script
    assert "/livez" in script
    assert "/readyz" in script
    assert "/warmup" in script
    assert "/warmup/asr" in script
    assert "/warmup/tts" in script
    assert "/studio/brand/vassil-logo.png" in script
    assert "voiceprint-canvas" in script
    assert "/studio/brand/vassil-voice-sculpture.jpg" not in script
    assert "/studio/brand/vassil-studio-generate.png" in script
    assert "/studio/brand/vassil-studio-transcribe.png" in script
    assert "/studio/brand/vassil-studio-realtime.png" in script
    assert "/studio/brand/vassil-studio-voices.png" in script
    assert "vassil.apiKey" in script
    assert "vvoice.apiKey" in script
    assert "vassil.sessionApiKey" in script
    assert "vassil.selectedVoiceId" in script
    assert "vvoice.selectedVoiceId" in script
    assert "vassil.generateDraft" in script
    assert "vvoice.generateDraft" in script
    assert "Script editor" in script
    assert "Voice and render" in script
    assert "Output and queue" in script
    assert "Search voices or files" in script
    assert "Add voice profile" in script
    assert "Upload audio" in script
    assert "Queue transcription" in script
    assert "Preview unavailable in this browser" in script
    assert "No transcript output" in script
    assert "Stop and finalize" in script
    assert "Microphone input" in script
    assert "input-level-meter" in script
    assert "Active for this session" in script
    assert "No realtime transcript" in script
    assert "Queue activity" in script
    assert "Search ID, text, language, or status" in script
    assert "Job details" in script
    assert "Lifecycle" in script
    assert "Failure details" in script
    assert "Output audio" in script
    assert "Run again" in script
    assert "Create voice profile" in script
    assert "reference_audio" in script
    assert "Delete voice profile?" in script
    assert "Voice selected" in script
    assert "Run diagnostics" in script
    assert "Download bundle" in script
    assert "Workspace readiness" in script
    assert "Speech recognition" in script
    assert "Troubleshooting" in script
    assert "Disk free" in script
    assert "Storage needs attention" in script
    assert "Workspace settings" in script
    assert "Owner sign-in is preferred" in script
    assert "Keep through reloads in this tab" in script
    assert "Copy API key" not in script
    assert "VASSIL_API_KEYS" not in script
    assert "Confirm password" in script
    assert "Passwords do not match" in script
    assert "Checking workspace" in script
    assert "Storage and retention" in script
    assert "Version" in script
    assert "Operations guide" in script
    assert "Application code is MIT-licensed." in script
    assert "Models and datasets are installed separately" in script
    assert "External telemetry is disabled by default" in script
    assert "belong here" not in script
    assert "Change password" in script
    assert "Changelog" in script
    assert "Warm all models" in script
    assert "Render mode" in script
    assert "First output checklist" in script
    assert "Production" in script
    assert "01 / Workflow" in script
    assert "Configured workspace paths" in script
    assert "Voice in. Voice out. Nothing leaves your machine." in script
    assert "The actual workspace, not a mockup" in script
    assert "No cloud account required" in script
    assert "2 voice profiles" not in script
    assert "color-scheme:light" in style
    assert "vvoice-soft-grid" not in style


def test_browser_api_key_source_avoids_persistent_storage() -> None:
    react_api = REPOSITORY_ROOT.joinpath(
        "frontend", "studio-react", "src", "lib", "api.ts"
    ).read_text(encoding="utf-8")
    settings_view = REPOSITORY_ROOT.joinpath(
        "frontend", "studio-react", "src", "features", "settings", "SettingsView.tsx"
    ).read_text(encoding="utf-8")
    legacy_app = REPOSITORY_ROOT.joinpath("frontend", "studio", "app.js").read_text(
        encoding="utf-8"
    )
    legacy_page = REPOSITORY_ROOT.joinpath("frontend", "studio", "index.html").read_text(
        encoding="utf-8"
    )

    assert "localStorage.setItem" not in react_api
    assert "localStorage.setItem" not in legacy_app
    assert "sessionStorage.setItem" in react_api
    assert "sessionStorage.setItem" in legacy_app
    assert "localStorage.removeItem" in react_api
    assert "localStorage.removeItem" in legacy_app
    assert "Copy API key" not in settings_view
    assert "VASSIL_API_KEYS" not in settings_view
    assert "unpkg.com" not in legacy_page
    assert 'src="/studio/assets/lucide.min.js"' in legacy_page
    legacy_icons = REPOSITORY_ROOT.joinpath("frontend", "studio", "lucide.min.js")
    assert legacy_icons.is_file()
    assert "@license lucide v1.23.0 - ISC" in legacy_icons.read_text(encoding="utf-8")[:200]


def test_jobs_use_authenticated_audio_playback() -> None:
    audio_player = REPOSITORY_ROOT.joinpath(
        "frontend", "studio-react", "src", "components", "ui", "audio-player.tsx"
    ).read_text(encoding="utf-8")
    jobs_view = REPOSITORY_ROOT.joinpath(
        "frontend", "studio-react", "src", "features", "jobs", "JobsView.tsx"
    ).read_text(encoding="utf-8")
    job_inspector = REPOSITORY_ROOT.joinpath(
        "frontend", "studio-react", "src", "features", "jobs", "JobInspector.tsx"
    ).read_text(encoding="utf-8")

    assert "fetchBlob(src" in audio_player
    assert "URL.createObjectURL" in audio_player
    assert "URL.revokeObjectURL" in audio_player
    assert "Download WAV" in audio_player
    assert "Listen" in jobs_view
    assert "audioExpanded" in jobs_view
    assert "<AudioPlayer" in job_inspector
    assert "<audio" not in job_inspector


def test_studio_dir_prefers_vassil_env(tmp_path, monkeypatch) -> None:
    studio_dir = tmp_path / "studio"
    studio_dir.mkdir()
    studio_dir.joinpath("index.html").write_text("<!doctype html><title>VassilStudio</title>", encoding="utf-8")

    monkeypatch.setenv("VASSIL_STUDIO_DIR", str(studio_dir))

    assert _resolve_studio_dir() == studio_dir


def test_studio_static_path_rejects_traversal() -> None:
    assert _safe_static_path("../../pyproject.toml") is None


def test_studio_redirects_to_setup_until_local_session_exists(tmp_path) -> None:
    settings = SecuritySettings(
        api_keys=(),
        auth_required=True,
        auth_db_path=tmp_path / "auth.sqlite3",
        session_cookie_name="vassil_session",
        session_ttl_seconds=3600,
        session_secret="test-session-secret",
        secure_cookies=False,
    )
    auth = LocalAuthService(settings)
    app = FastAPI()
    app.state.container = SimpleNamespace(settings=SimpleNamespace(security=settings), auth=auth)
    register_request_middleware(app)
    app.include_router(router)
    client = TestClient(app)

    response = client.get("/studio", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/setup"

    account = auth.create_owner("owner", "correct horse battery")
    session = auth.create_session(account)
    client.cookies.set(settings.session_cookie_name, session.token)

    authorized_response = client.get("/studio")
    assert authorized_response.status_code == 200
    assert "VassilStudio" in authorized_response.text
    nonce_match = re.search(
        r'<meta name="csp-style-nonce" content="([^"]+)"', authorized_response.text
    )
    assert nonce_match is not None
    nonce = nonce_match.group(1)
    content_security_policy = authorized_response.headers["content-security-policy"]
    assert f"style-src-elem 'self' 'nonce-{nonce}'" in content_security_policy
    assert "style-src-elem 'self' 'unsafe-inline'" not in content_security_policy
    assert authorized_response.headers["cache-control"] == "no-store"

    refreshed_response = client.get("/studio")
    assert f'content="{nonce}"' not in refreshed_response.text


def test_auth_redirect_keeps_studio_path_and_query(tmp_path) -> None:
    app = FastAPI()
    app.state.container = SimpleNamespace(
        settings=SimpleNamespace(security=SimpleNamespace(auth_required=True)),
        auth=SimpleNamespace(setup_required=True, account_from_session_token=lambda _: None),
    )
    app.include_router(router)
    response = TestClient(app).get("/studio/review?job=test-job", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/setup?return_to=%2Fstudio%2Freview%3Fjob%3Dtest-job"


def test_missing_react_build_has_actionable_unavailable_page(tmp_path, monkeypatch) -> None:
    tmp_path.joinpath("index.html").write_text("<html>legacy</html>", encoding="utf-8")
    monkeypatch.setattr("vvoice.app.studio.router.STATIC_DIR", tmp_path)
    app = FastAPI()
    app.include_router(router)
    response = TestClient(app).get("/setup")
    assert response.status_code == 503
    assert "npm run build" in response.text
    assert "Studio needs its frontend build" in response.text
