import json

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
