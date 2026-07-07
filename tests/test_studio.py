from __future__ import annotations

import re

from vvoice.app.studio.router import STATIC_DIR, _resolve_studio_dir, router


def test_studio_route_and_react_assets_are_registered() -> None:
    paths = {route.path for route in router.routes if hasattr(route, "path")}
    assert "/studio" in paths
    assert "/studio/assets" in paths
    assert "/studio/{path:path}" in paths

    page = STATIC_DIR.joinpath("index.html").read_text(encoding="utf-8")
    assert "VassilStudio" in page
    assert 'href="/studio/brand/vassil-mark.png"' in page
    assert 'src="/studio/assets/' in page
    assert 'href="/studio/assets/' in page

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
    assert "PATCH" in script
    assert "DELETE" in script
    assert "/model-status" in script
    assert "/warmup" in script
    assert "/studio/brand/vassil-logo.png" in script
    assert "vassil.apiKey" in script
    assert "vvoice.apiKey" in script
    assert "vassil.selectedVoiceId" in script
    assert "vvoice.selectedVoiceId" in script
    assert "Script editor" in script
    assert "Voice and render" in script
    assert "Search voices or files" in script
    assert "Delete voice profile?" in script
    assert "Voice selected" in script
    assert "Run diagnostics" in script
    assert "Warm models" in script
    assert "Render mode" in script
    assert "Production" in script
    assert "color-scheme:light" in style
    assert "vvoice-soft-grid" not in style


def test_studio_dir_prefers_vassil_env(tmp_path, monkeypatch) -> None:
    studio_dir = tmp_path / "studio"
    studio_dir.mkdir()
    studio_dir.joinpath("index.html").write_text("<!doctype html><title>VassilStudio</title>", encoding="utf-8")

    monkeypatch.setenv("VASSIL_STUDIO_DIR", str(studio_dir))

    assert _resolve_studio_dir() == studio_dir
