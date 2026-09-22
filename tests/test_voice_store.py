import json
from pathlib import Path

import pytest

from vvoice.core.errors import VoiceNotFoundError, VVoiceError
from vvoice.domains.voices.service import VoiceStore


def test_voice_store_create_get_list_delete(tmp_path) -> None:
    store = VoiceStore(tmp_path)

    profile = store.create(
        name="demo",
        language="en",
        reference_text="xin chao",
        reference_text_source="user",
        audio_bytes=b"RIFF....WAVE",
        sample_rate=24000,
        duration_seconds=1.25,
    )

    assert profile.voice_id
    assert profile.language == "en"
    assert profile.audio_path.exists()
    assert profile.audio_size_bytes == len(b"RIFF....WAVE")
    assert store.get(profile.voice_id).name == "demo"
    assert store.get(profile.voice_id).reference_text_source == "user"
    assert len(store.list()) == 1

    metadata = json.loads((tmp_path / profile.voice_id / "metadata.json").read_text())
    assert metadata["audio_path"] == "reference.wav"
    assert metadata["language"] == "en"
    assert metadata["audio_size_bytes"] == len(b"RIFF....WAVE")
    assert metadata["metadata_version"] == 4
    assert metadata["audio_sha256"] == profile.audio_sha256

    updated = store.update(
        profile.voice_id,
        name="demo-updated",
        language="vi",
        reference_text="xin chao moi",
    )

    assert updated.name == "demo-updated"
    assert updated.language == "vi"
    assert updated.reference_text == "xin chao moi"
    assert updated.reference_text_source == "user"
    assert updated.updated_at

    store.delete(profile.voice_id)

    assert store.list() == []


def test_voice_store_lists_loose_import_candidates(tmp_path) -> None:
    store = VoiceStore(tmp_path)
    (tmp_path / "sample voice.weba").write_bytes(b"audio")
    (tmp_path / "notes.txt").write_text("ignore", encoding="utf-8")

    candidates = store.list_import_candidates()

    assert [path.name for path in candidates] == ["sample voice.weba"]
    assert store.import_candidate_path("sample voice.weba") == tmp_path / "sample voice.weba"


def test_voice_store_reads_legacy_absolute_audio_paths(tmp_path) -> None:
    voice_dir = tmp_path / "voice-legacy"
    voice_dir.mkdir()
    audio_path = voice_dir / "reference.wav"
    audio_path.write_bytes(b"RIFF....WAVE")
    (voice_dir / "metadata.json").write_text(
        json.dumps(
            {
                "voice_id": "voice-legacy",
                "name": "legacy",
                "reference_text": "xin chao",
                "reference_text_source": "user",
                "audio_path": str(audio_path),
                "sample_rate": 24000,
                "duration_seconds": 1.25,
                "created_at": "2026-07-01T00:00:00+00:00",
                "updated_at": "2026-07-01T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )

    profile = VoiceStore(tmp_path).get("voice-legacy")

    assert profile.audio_path == audio_path
    assert profile.language == "vi"
    assert profile.audio_size_bytes == len(b"RIFF....WAVE")


def _create_profile(store: VoiceStore):
    return store.create(
        name="demo", reference_text="hello", reference_text_source="user",
        audio_bytes=b"reference", sample_rate=24000, duration_seconds=1.0,
    )


@pytest.mark.parametrize("voice_id", ["..", "../outside", r"..\outside", "C:outside", "voice."])
def test_voice_store_rejects_untrusted_ids_before_read_write_or_delete(tmp_path, voice_id) -> None:
    root = tmp_path / "voices"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "keep.txt"
    sentinel.write_text("untouched", encoding="utf-8")
    store = VoiceStore(root)

    for operation in (store.get, store.delete, lambda value: store.update(value, name="changed")):
        with pytest.raises(VoiceNotFoundError):
            operation(voice_id)
    assert sentinel.read_text(encoding="utf-8") == "untouched"


def test_voice_delete_route_rejects_encoded_windows_traversal(tmp_path) -> None:
    from types import SimpleNamespace
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from fastapi.responses import JSONResponse
    from vvoice.domains.voices.router import router

    root = tmp_path / "voices"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "keep.txt"
    sentinel.write_text("untouched", encoding="utf-8")
    app = FastAPI()
    app.state.container = SimpleNamespace(voices=VoiceStore(root))
    app.add_exception_handler(
        VoiceNotFoundError, lambda request, exc: JSONResponse({"detail": str(exc)}, status_code=404),
    )
    app.include_router(router, prefix="/voices")
    response = TestClient(app).delete("/voices/..%5Coutside")
    assert response.status_code == 404
    assert sentinel.read_text(encoding="utf-8") == "untouched"


def test_voice_store_rejects_linked_record_directory(tmp_path) -> None:
    outside_store = VoiceStore(tmp_path / "outside")
    profile = _create_profile(outside_store)
    root = tmp_path / "voices"
    root.mkdir()
    linked = root / profile.voice_id
    try:
        linked.symlink_to(profile.audio_path.parent, target_is_directory=True)
    except OSError:
        try:
            import _winapi
            _winapi.CreateJunction(str(profile.audio_path.parent), str(linked))
        except (ImportError, OSError):
            pytest.skip("Creating symbolic links or junctions is unavailable")
    store = VoiceStore(root)
    for operation in (store.get, store.delete, lambda value: store.update(value, name="changed")):
        with pytest.raises(VoiceNotFoundError):
            operation(profile.voice_id)
    assert store.list() == []
    assert outside_store.get(profile.voice_id).name == "demo"


def test_voice_store_rejects_audio_link_and_preserves_target(tmp_path) -> None:
    store = VoiceStore(tmp_path / "voices")
    profile = _create_profile(store)
    outside = tmp_path / "outside.wav"
    outside.write_bytes(b"external data")
    profile.audio_path.unlink()
    try:
        profile.audio_path.symlink_to(outside)
    except OSError:
        pytest.skip("Creating symbolic links is unavailable")
    with pytest.raises(VoiceNotFoundError):
        store.get(profile.voice_id)
    assert outside.read_bytes() == b"external data"
    assert store.quarantined_count == 1


def test_voice_store_rejects_audio_path_through_linked_directory(tmp_path) -> None:
    store = VoiceStore(tmp_path / "voices")
    profile = _create_profile(store)
    outside = tmp_path / "outside"
    outside.mkdir()
    target = outside / "audio.wav"
    target.write_bytes(b"keep external audio")
    link = profile.audio_path.parent / "linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        try:
            import _winapi
            _winapi.CreateJunction(str(outside), str(link))
        except (ImportError, OSError):
            pytest.skip("Creating symbolic links or junctions is unavailable")
    metadata_path = profile.audio_path.parent / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["audio_path"] = "linked/audio.wav"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(VoiceNotFoundError):
        store.snapshot(profile.voice_id)
    assert target.read_bytes() == b"keep external audio"
    assert store.quarantined_count == 1


def test_voice_delete_validates_all_entries_before_removing_files(tmp_path) -> None:
    store = VoiceStore(tmp_path)
    profile = _create_profile(store)
    (profile.audio_path.parent / "unexpected-directory").mkdir()
    with pytest.raises(VVoiceError, match="unexpected"):
        store.delete(profile.voice_id)
    assert profile.audio_path.read_bytes() == b"reference"
    assert (profile.audio_path.parent / "metadata.json").is_file()


@pytest.mark.parametrize("content", ["{", "[]", '{"voice_id":"broken","name":42}'])
def test_voice_store_quarantines_bad_records_without_losing_good_profiles(tmp_path, content) -> None:
    store = VoiceStore(tmp_path)
    profile = _create_profile(store)
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "metadata.json").write_text(content, encoding="utf-8")
    assert [item.voice_id for item in store.list()] == [profile.voice_id]
    assert store.quarantined_count == 1
    assert next(broken.glob("metadata.corrupt-*.json")).read_text(encoding="utf-8") == content
    assert VoiceStore(tmp_path).quarantined_count == 1
    with pytest.raises(VoiceNotFoundError):
        store.get("broken")


def test_voice_update_preserves_previous_metadata_when_atomic_replace_fails(tmp_path, monkeypatch):
    store = VoiceStore(tmp_path)
    profile = _create_profile(store)
    metadata = profile.audio_path.parent / "metadata.json"
    original = metadata.read_bytes()
    original_replace = Path.replace

    def fail_metadata_replace(path, target):
        if Path(target) == metadata:
            raise OSError("simulated interrupted write")
        return original_replace(path, target)

    monkeypatch.setattr(Path, "replace", fail_metadata_replace)
    with pytest.raises(OSError, match="interrupted"):
        store.update(profile.voice_id, name="changed")
    assert metadata.read_bytes() == original
    assert store.get(profile.voice_id).name == "demo"
    assert list(metadata.parent.glob("*.tmp")) == []


def test_voice_store_quarantines_nonfinite_metrics_and_keeps_audio(tmp_path):
    store = VoiceStore(tmp_path)
    profile = _create_profile(store)
    metadata_path = profile.audio_path.parent / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["duration_seconds"] = float("nan")
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    assert store.list() == []
    assert store.quarantined_count == 1
    assert profile.audio_path.read_bytes() == b"reference"
