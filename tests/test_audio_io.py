import subprocess

import pytest

from vvoice.core.errors import AudioError, PUBLIC_AUDIO_ERROR_MESSAGE
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
