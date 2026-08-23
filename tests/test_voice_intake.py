import asyncio
from types import SimpleNamespace

import numpy as np
import pytest

from vvoice.core.errors import (
    VoiceDuplicateError,
    VoiceIntakeConflictError,
    VoiceIntakeRejectedError,
)
from vvoice.domains.voices.intake import (
    intake_status,
    prepare_voice_audio,
    reference_text_issues,
)
from vvoice.domains.voices.router import _analyze_voice_intake, _create_voice_from_audio
from vvoice.domains.voices.service import VoiceStore
from vvoice.shared.audio.io import encode_wav


SAMPLE_RATE = 16000


def test_voice_intake_reports_source_metrics_and_suggested_trim() -> None:
    silence = np.zeros(SAMPLE_RATE, dtype=np.float32)
    speech = _tone(3.0)
    stereo = np.column_stack([np.concatenate([silence, speech, silence])] * 2)

    prepared = prepare_voice_audio(
        encode_wav(stereo, SAMPLE_RATE),
        target_sample_rate=24000,
    )

    assert prepared.channels == 2
    assert prepared.source_sample_rate == SAMPLE_RATE
    assert prepared.target_sample_rate == 24000
    assert prepared.source_duration_seconds == pytest.approx(5.0, abs=0.01)
    assert prepared.metrics.leading_silence_seconds == pytest.approx(1.0, abs=0.03)
    assert prepared.metrics.trailing_silence_seconds == pytest.approx(1.0, abs=0.03)
    assert prepared.suggested_trim_start_seconds == pytest.approx(0.9, abs=0.03)
    assert prepared.suggested_trim_end_seconds == pytest.approx(4.1, abs=0.03)
    assert intake_status(prepared.issues) == "review"


def test_voice_intake_rechecks_metrics_after_trim() -> None:
    audio = np.concatenate(
        [np.zeros(SAMPLE_RATE, dtype=np.float32), _tone(3.0), np.zeros(SAMPLE_RATE, dtype=np.float32)]
    )

    prepared = prepare_voice_audio(
        encode_wav(audio, SAMPLE_RATE),
        target_sample_rate=24000,
        trim_start_seconds=1.0,
        trim_end_seconds=4.0,
    )

    assert prepared.duration_seconds == pytest.approx(3.0, abs=0.01)
    assert prepared.metrics.leading_silence_seconds < 0.03
    assert prepared.metrics.trailing_silence_seconds < 0.03
    assert prepared.metrics.speech_coverage_ratio > 0.95
    assert prepared.issues == ()


def test_voice_intake_blocks_silent_and_severely_clipped_audio() -> None:
    silent = prepare_voice_audio(
        encode_wav(np.zeros(SAMPLE_RATE * 3, dtype=np.float32), SAMPLE_RATE),
        target_sample_rate=24000,
    )
    clipped = prepare_voice_audio(
        encode_wav(np.ones(SAMPLE_RATE * 3, dtype=np.float32), SAMPLE_RATE),
        target_sample_rate=24000,
    )

    assert intake_status(silent.issues) == "blocked"
    assert {issue.code for issue in silent.issues} >= {"speech_not_detected"}
    assert intake_status(clipped.issues) == "blocked"
    assert {issue.code for issue in clipped.issues} >= {"severe_clipping"}


def test_reference_text_language_checks_are_conservative() -> None:
    assert reference_text_issues("Hello from the studio", "en") == ()
    assert {issue.code for issue in reference_text_issues("Giọng nói rõ ràng", "en")} == {
        "reference_text_language_mismatch"
    }
    assert {issue.code for issue in reference_text_issues("Xin chao tu studio", "vi")} == {
        "reference_text_diacritics_review"
    }
    assert intake_status(reference_text_issues("123...", "vi")) == "blocked"


def test_voice_store_rejects_duplicate_canonical_audio(tmp_path) -> None:
    store = VoiceStore(tmp_path)
    audio_bytes = encode_wav(_tone(3.0), SAMPLE_RATE)
    first = store.create(
        name="first",
        language="vi",
        reference_text="Xin chào",
        reference_text_source="user",
        audio_bytes=audio_bytes,
        sample_rate=SAMPLE_RATE,
        duration_seconds=3.0,
    )

    assert store.find_by_audio_sha256(first.audio_sha256) == first
    with pytest.raises(VoiceDuplicateError, match="first"):
        store.create(
            name="duplicate",
            language="vi",
            reference_text="Xin chào",
            reference_text_source="user",
            audio_bytes=audio_bytes,
            sample_rate=SAMPLE_RATE,
            duration_seconds=3.0,
        )


def test_reviewed_create_requires_same_source_and_warning_acknowledgement(tmp_path) -> None:
    container = _container(tmp_path)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(container=container)))
    raw_audio = encode_wav(_tone(1.5), SAMPLE_RATE)
    report = asyncio.run(
        _analyze_voice_intake(
            request,
            raw_audio=raw_audio,
            language="vi",
            reference_text="Giọng nói thử nghiệm",
            auto_transcribe=False,
            trim_start_seconds=0.0,
            trim_end_seconds=None,
        )
    )

    assert report["status"] == "review"
    with pytest.raises(VoiceIntakeConflictError, match="changed after review"):
        asyncio.run(
            _create_voice_from_audio(
                request,
                raw_audio=raw_audio,
                name="reviewed",
                language="vi",
                reference_text="Giọng nói thử nghiệm",
                auto_transcribe=False,
                reviewed_source_sha256="0" * 64,
                acknowledge_warnings=True,
            )
        )

    with pytest.raises(VoiceIntakeConflictError, match="warnings"):
        asyncio.run(
            _create_voice_from_audio(
                request,
                raw_audio=raw_audio,
                name="reviewed",
                language="vi",
                reference_text="Giọng nói thử nghiệm",
                auto_transcribe=False,
                reviewed_source_sha256=report["source_sha256"],
            )
        )

    profile = asyncio.run(
        _create_voice_from_audio(
            request,
            raw_audio=raw_audio,
            name="reviewed",
            language="vi",
            reference_text="Giọng nói thử nghiệm",
            auto_transcribe=False,
            reviewed_source_sha256=report["source_sha256"],
            acknowledge_warnings=True,
        )
    )
    assert profile.name == "reviewed"


def test_unreviewed_create_still_blocks_invalid_audio(tmp_path) -> None:
    container = _container(tmp_path)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(container=container)))
    silent_audio = encode_wav(np.zeros(SAMPLE_RATE * 3, dtype=np.float32), SAMPLE_RATE)

    report = asyncio.run(
        _analyze_voice_intake(
            request,
            raw_audio=silent_audio,
            language="vi",
            reference_text=None,
            auto_transcribe=True,
            trim_start_seconds=0.0,
            trim_end_seconds=None,
        )
    )
    assert report["status"] == "blocked"

    with pytest.raises(VoiceIntakeRejectedError, match="No usable speech"):
        asyncio.run(
            _create_voice_from_audio(
                request,
                raw_audio=silent_audio,
                name="silent",
                language="vi",
                reference_text="Giọng nói thử nghiệm",
                auto_transcribe=False,
            )
        )


def _tone(seconds: float) -> np.ndarray:
    sample_count = round(seconds * SAMPLE_RATE)
    time = np.arange(sample_count, dtype=np.float32) / SAMPLE_RATE
    return (0.25 * np.sin(2 * np.pi * 220 * time)).astype(np.float32)


def _container(tmp_path):
    class TtsRuntime:
        @staticmethod
        def sample_rate_for(language: str) -> int:
            assert language in {"vi", "en"}
            return 24000

    return SimpleNamespace(
        settings=SimpleNamespace(
            limits=SimpleNamespace(max_voice_name_chars=120, max_reference_text_chars=2000)
        ),
        tts=TtsRuntime(),
        voices=VoiceStore(tmp_path),
    )
