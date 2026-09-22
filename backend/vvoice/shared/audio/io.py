from __future__ import annotations

from io import BytesIO
from pathlib import Path
import shutil
import subprocess
import tempfile

import librosa
import numpy as np
import soundfile as sf

from vvoice.core.errors import AudioError, AudioLimitError, PUBLIC_AUDIO_ERROR_MESSAGE


MAX_AUDIO_SECONDS = 1800
MAX_DECODED_SAMPLES = 32_000_000
MAX_AUDIO_CHANNELS = 8
MAX_AUDIO_SAMPLE_RATE = 192000


def _read_bounded_audio(source) -> tuple[np.ndarray, int]:
    with sf.SoundFile(source) as audio:
        if (
            not 1 <= audio.channels <= MAX_AUDIO_CHANNELS
            or not 1 <= audio.samplerate <= MAX_AUDIO_SAMPLE_RATE
        ):
            raise AudioLimitError("Audio exceeds the supported channel count or sample rate")
        max_frames = min(
            MAX_AUDIO_SECONDS * audio.samplerate,
            MAX_DECODED_SAMPLES // audio.channels,
        )
        if audio.frames > max_frames:
            raise AudioLimitError("Audio exceeds the decoded duration or sample limit; split the file")
        samples = audio.read(frames=max_frames + 1, dtype="float32", always_2d=True)
        if len(samples) > max_frames:
            raise AudioLimitError("Audio exceeds the decoded duration or sample limit; split the file")
        return samples, audio.samplerate


def load_audio_bytes(data: bytes, target_sample_rate: int | None = None) -> tuple[np.ndarray, int]:
    samples, sample_rate, _ = load_audio_bytes_with_metadata(data, target_sample_rate)
    return samples, sample_rate


def load_audio_bytes_with_metadata(
    data: bytes,
    target_sample_rate: int | None = None,
) -> tuple[np.ndarray, int, int]:
    try:
        samples, sample_rate = _read_bounded_audio(BytesIO(data))
    except AudioLimitError:
        raise
    except Exception as soundfile_exc:  # pragma: no cover - depends on libsndfile codecs
        samples, sample_rate = _load_audio_bytes_with_ffmpeg(data, target_sample_rate, soundfile_exc)

    if samples.ndim != 2:
        samples = np.atleast_2d(samples).T
    channels = int(samples.shape[1])
    samples = samples.mean(axis=1)

    samples = np.asarray(samples, dtype=np.float32)
    if samples.size == 0:
        raise AudioError("Audio file has no samples")

    if not np.isfinite(samples).all():
        raise AudioError("Audio file contains non-finite samples")

    if target_sample_rate and sample_rate != target_sample_rate:
        if not 1 <= target_sample_rate <= MAX_AUDIO_SAMPLE_RATE:
            raise AudioLimitError("Unsupported target audio sample rate")
        if len(samples) * target_sample_rate / sample_rate > MAX_DECODED_SAMPLES:
            raise AudioLimitError("Resampled audio exceeds the sample limit; split the file")
        samples = librosa.resample(samples, orig_sr=sample_rate, target_sr=target_sample_rate)
        sample_rate = target_sample_rate

    return samples, int(sample_rate), channels


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
        raise AudioError(PUBLIC_AUDIO_ERROR_MESSAGE) from soundfile_exc

    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        "pipe:0",
    ]
    output_limit = MAX_DECODED_SAMPLES * 2 + 4096
    if target_sample_rate:
        command.extend(["-ar", str(target_sample_rate)])
    command.extend([
        "-vn",
        "-t", str(MAX_AUDIO_SECONDS + 1), "-fs", str(output_limit),
        "-c:a", "pcm_s16le", "-f", "wav",
    ])

    try:
        with tempfile.TemporaryDirectory(prefix="vassil-decode-") as folder:
            output = Path(folder) / "decoded.wav"
            subprocess.run(
                [*command, str(output)],
                input=data,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                check=True,
                timeout=90,
            )
            if output.stat().st_size >= output_limit:
                raise AudioLimitError("Audio exceeds the decoded sample limit; split the file")
            samples, sample_rate = _read_bounded_audio(output)
    except AudioLimitError:
        raise
    except Exception as exc:  # pragma: no cover - depends on ffmpeg codecs
        raise AudioError(PUBLIC_AUDIO_ERROR_MESSAGE) from exc

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
