import subprocess
from io import BytesIO

import numpy as np
import pytest
import soundfile as sf

from vvoice.core.errors import AudioError, AudioLimitError, PUBLIC_AUDIO_ERROR_MESSAGE
from vvoice.shared.audio import io as audio_io


def test_ffmpeg_decode_failure_does_not_enter_public_error_message(monkeypatch) -> None:
    private_executable = r"C:\Users\private\.venv\ffmpeg.exe"
    monkeypatch.setattr(audio_io, "_find_ffmpeg", lambda: private_executable)

    def fail(command, **_):
        raise subprocess.CalledProcessError(returncode=1, cmd=command)

    monkeypatch.setattr(audio_io.subprocess, "run", fail)

    with pytest.raises(AudioError) as error:
        audio_io._load_audio_bytes_with_ffmpeg(
            b"invalid audio",
            target_sample_rate=16000,
            soundfile_exc=RuntimeError("libsndfile rejected input"),
        )

    assert str(error.value) == PUBLIC_AUDIO_ERROR_MESSAGE
    assert private_executable not in str(error.value)


def test_compressed_audio_is_rejected_before_decoding_past_budget(monkeypatch) -> None:
    audio = BytesIO()
    sf.write(audio, np.zeros(16000, dtype=np.float32), 16000, format="FLAC")
    monkeypatch.setattr(audio_io, "MAX_DECODED_SAMPLES", 100)
    monkeypatch.setattr(audio_io, "_find_ffmpeg", lambda: pytest.fail("must not retry limit failure"))
    with pytest.raises(AudioLimitError):
        audio_io.load_audio_bytes(audio.getvalue())


def test_audio_duration_limit_and_resampled_sample_limit(monkeypatch) -> None:
    audio = audio_io.encode_wav(np.ones(16000, dtype=np.float32) * 0.1, 16000)
    monkeypatch.setattr(audio_io, "MAX_AUDIO_SECONDS", 0.5)
    with pytest.raises(AudioLimitError):
        audio_io.load_audio_bytes(audio)
    monkeypatch.setattr(audio_io, "MAX_AUDIO_SECONDS", 2)
    monkeypatch.setattr(audio_io, "MAX_DECODED_SAMPLES", 20000)
    with pytest.raises(AudioLimitError):
        audio_io.load_audio_bytes(audio, target_sample_rate=48000)


def test_bounded_decode_retains_channels_and_normalizes_mono() -> None:
    audio = BytesIO()
    stereo = np.column_stack([np.ones(1000) * 0.2, np.ones(1000) * 0.4])
    sf.write(audio, stereo, 16000, format="WAV", subtype="FLOAT")
    samples, rate, channels = audio_io.load_audio_bytes_with_metadata(audio.getvalue())
    assert rate == 16000
    assert channels == 2
    assert np.allclose(samples, 0.3)


def test_ffmpeg_fallback_preserves_source_rate_and_sample_budget(monkeypatch) -> None:
    source_rate = 16000
    source_samples = np.full((source_rate, 2), 0.25, dtype=np.float32)
    monkeypatch.setattr(audio_io, "_find_ffmpeg", lambda: "fixture-ffmpeg")
    monkeypatch.setattr(audio_io, "MAX_DECODED_SAMPLES", source_samples.size)

    def decode_fixture(command, **kwargs):
        assert "-ar" not in command, "Intake must not silently resample source metadata"
        assert kwargs["input"] == b"compressed-fixture"
        sf.write(command[-1], source_samples, source_rate, format="WAV", subtype="PCM_16")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(audio_io.subprocess, "run", decode_fixture)
    samples, rate, channels = audio_io.load_audio_bytes_with_metadata(b"compressed-fixture")

    assert rate == source_rate
    assert channels == 2
    assert samples.shape == (source_rate,)
    assert np.allclose(samples, 0.25)
