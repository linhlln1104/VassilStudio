from pathlib import Path

from vvoice.domains.voices.router import _import_candidate_response, _voice_response, router
from vvoice.domains.voices.service import VoiceProfile


def test_voice_router_registers_reference_audio_route() -> None:
    paths = {route.path for route in router.routes if hasattr(route, "path")}
    voice_route_methods = {
        method
        for route in router.routes
        if getattr(route, "path", None) == "/{voice_id}"
        for method in getattr(route, "methods", set())
    }

    assert "/{voice_id}/reference-audio" in paths
    assert "/import-candidates" in paths
    assert "/import-candidates/{filename}/audio" in paths
    assert "/import" in paths
    assert "PATCH" in voice_route_methods


def test_voice_response_includes_reference_audio_url() -> None:
    profile = VoiceProfile(
        voice_id="voice-1",
        name="demo",
        language="vi",
        reference_text="xin chao",
        reference_text_source="user",
        audio_path=Path("data/voices/voice-1/reference.wav"),
        audio_size_bytes=1234,
        sample_rate=24000,
        duration_seconds=1.0,
        created_at="2026-06-30T00:00:00+00:00",
    )

    payload = _voice_response(profile)

    assert payload["reference_audio_url"] == "/api/v1/voices/voice-1/reference-audio"
    assert payload["language"] == "vi"
    assert payload["audio_size_bytes"] == 1234
    assert "updated_at" in payload
    assert "audio_path" not in payload


def test_import_candidate_response_includes_audio_url(tmp_path) -> None:
    candidate = tmp_path / "anh Long.weba"
    candidate.write_bytes(b"audio")

    payload = _import_candidate_response(candidate)

    assert payload["filename"] == "anh Long.weba"
    assert payload["audio_url"] == "/api/v1/voices/import-candidates/anh%20Long.weba/audio"
