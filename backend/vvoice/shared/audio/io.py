from __future__ import annotations

from io import BytesIO
import shutil
import subprocess

import librosa
import numpy as np
import soundfile as sf

from vvoice.core.errors import AudioError


def load_audio_bytes(data: bytes, target_sample_rate: int | None = None) -> tuple[np.ndarray, int]:
    try:
        samples, sample_rate = sf.read(BytesIO(data), dtype="float32", always_2d=False)
    except Exception as soundfile_exc:  # pragma: no cover - depends on libsndfile codecs
        samples, sample_rate = _load_audio_bytes_with_ffmpeg(data, target_sample_rate, soundfile_exc)

    if samples.ndim == 2:
        samples = samples.mean(axis=1)

    samples = np.asarray(samples, dtype=np.float32)
    if samples.size == 0:
        raise AudioError("Audio file has no samples")

    if not np.isfinite(samples).all():
        raise AudioError("Audio file contains non-finite samples")

    if target_sample_rate and sample_rate != target_sample_rate:
        samples = librosa.resample(samples, orig_sr=sample_rate, target_sr=target_sample_rate)
        sample_rate = target_sample_rate

    return samples, int(sample_rate)


def encode_wav(samples: np.ndarray, sample_rate: int) -> bytes:
    buffer = BytesIO()
    sf.write(buffer, samples, samplerate=sample_rate, format="WAV", subtype="PCM_16")
    return buffer.getvalue()


def duration_seconds(samples: np.ndarray, sample_rate: int) -> float:
    if sample_rate <= 0:
        return 0.0
    return float(len(samples) / sample_rate)


def _load_audio_bytes_with_ffmpeg(
    data: bytes,
    target_sample_rate: int | None,
    soundfile_exc: Exception,
) -> tuple[np.ndarray, int]:
    ffmpeg = _find_ffmpeg()
    if not ffmpeg:
        raise AudioError(
            "Cannot decode audio with libsndfile and ffmpeg is unavailable. "
            "Install imageio-ffmpeg or convert the file to WAV/FLAC."
        ) from soundfile_exc

    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        "pipe:0",
        "-ac",
        "1",
    ]
    if target_sample_rate:
        command.extend(["-ar", str(target_sample_rate)])
    command.extend(["-f", "wav", "pipe:1"])

    try:
        completed = subprocess.run(
            command,
            input=data,
            capture_output=True,
            check=True,
            timeout=90,
        )
        samples, sample_rate = sf.read(
            BytesIO(completed.stdout),
            dtype="float32",
            always_2d=False,
        )
    except Exception as exc:  # pragma: no cover - depends on ffmpeg codecs
        raise AudioError(f"Cannot decode audio with ffmpeg: {exc}") from exc

    return np.asarray(samples, dtype=np.float32), int(sample_rate)


def _find_ffmpeg() -> str | None:
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg

    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None
