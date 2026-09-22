from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import numpy as np

from vvoice.core.config import RealtimeSettings
from vvoice.core.errors import VVoiceError


SUPPORTED_ENCODINGS = {"pcm_f32le", "pcm_s16le"}
MIN_CHUNK_SECONDS = 0.05
MAX_CHUNK_SECONDS = 30.0
MAX_BUFFER_SECONDS = 60.0


class RealtimeProtocolError(VVoiceError):
    pass


@dataclass(frozen=True)
class RealtimeAudioChunk:
    samples: np.ndarray
    sample_rate: int
    duration_seconds: float
    rms: float
    is_silence: bool


class RealtimeAsrSession:
    def __init__(
        self,
        *,
        sample_rate: int,
        encoding: str,
        chunk_seconds: float,
        min_chunk_seconds: float,
        max_buffer_seconds: float,
        silence_rms: float,
    ) -> None:
        self.sample_rate = sample_rate
        self.encoding = encoding
        self.chunk_seconds = chunk_seconds
        self.min_chunk_seconds = min_chunk_seconds
        self.max_buffer_seconds = max_buffer_seconds
        self.silence_rms = silence_rms
        self._buffer = np.empty(0, dtype=np.float32)
        self._validate()
        self._buffer_limit = self.max_buffer_seconds

    @classmethod
    def from_settings(cls, settings: RealtimeSettings, sample_rate: int) -> RealtimeAsrSession:
        return cls(
            sample_rate=sample_rate,
            encoding=settings.encoding,
            chunk_seconds=settings.chunk_seconds,
            min_chunk_seconds=settings.min_chunk_seconds,
            max_buffer_seconds=settings.max_buffer_seconds,
            silence_rms=settings.silence_rms,
        )

    def apply_config(self, payload: dict[str, Any]) -> None:
        allowed = {"type", *self.describe()}
        if set(payload) - allowed:
            raise RealtimeProtocolError("Unknown realtime configuration field")
        sample_rate = payload.get("sample_rate", self.sample_rate)
        if isinstance(sample_rate, bool) or not isinstance(sample_rate, int):
            raise RealtimeProtocolError("Realtime sample_rate must be an integer")
        if sample_rate != self.sample_rate:
            raise RealtimeProtocolError(
                f"Realtime ASR expects {self.sample_rate} Hz PCM, got {sample_rate} Hz"
            )

        candidate = self.describe() | {key: value for key, value in payload.items() if key != "type"}
        validated = RealtimeAsrSession(**candidate)
        if validated.max_buffer_seconds > self._buffer_limit:
            raise RealtimeProtocolError("Realtime buffer exceeds the server session limit")
        if self._buffer.size and validated.encoding != self.encoding:
            raise RealtimeProtocolError("Flush or clear buffered audio before changing encoding")
        if self._buffer.size > self._seconds_to_samples(validated.max_buffer_seconds):
            raise RealtimeProtocolError("Flush or clear audio before reducing the buffer limit")
        for key, value in validated.describe().items():
            setattr(self, key, value)

    def describe(self) -> dict[str, Any]:
        return {
            "sample_rate": self.sample_rate,
            "encoding": self.encoding,
            "chunk_seconds": self.chunk_seconds,
            "min_chunk_seconds": self.min_chunk_seconds,
            "max_buffer_seconds": self.max_buffer_seconds,
            "silence_rms": self.silence_rms,
        }

    def append_binary(self, data: bytes) -> list[RealtimeAudioChunk]:
        bytes_per_sample = 4 if self.encoding == "pcm_f32le" else 2
        max_samples = self._seconds_to_samples(self.max_buffer_seconds)
        # A frame may complete a buffered chunk. Bound the incoming frame separately;
        # after draining, retained audio is strictly shorter than one chunk.
        if len(data) / bytes_per_sample > max_samples:
            raise RealtimeProtocolError("Realtime audio exceeds the session buffer limit")
        samples = self.decode_binary(data)
        if samples.size == 0:
            return []

        self._buffer = np.concatenate([self._buffer, samples])
        chunks: list[RealtimeAudioChunk] = []
        chunk_samples = self._seconds_to_samples(self.chunk_seconds)

        while self._buffer.size >= chunk_samples:
            chunk = self._buffer[:chunk_samples]
            self._buffer = self._buffer[chunk_samples:]
            chunks.append(self._make_chunk(chunk))

        return chunks

    def flush(self, *, force: bool = False) -> RealtimeAudioChunk | None:
        if self._buffer.size == 0:
            return None

        if not force and self._buffer.size < self._seconds_to_samples(self.min_chunk_seconds):
            return None

        chunk = self._buffer
        self._buffer = np.empty(0, dtype=np.float32)
        return self._make_chunk(chunk)

    def clear(self) -> None:
        self._buffer = np.empty(0, dtype=np.float32)

    def decode_binary(self, data: bytes) -> np.ndarray:
        if not data:
            return np.empty(0, dtype=np.float32)

        if self.encoding == "pcm_f32le":
            if len(data) % 4:
                raise RealtimeProtocolError("pcm_f32le payload length must be divisible by 4")
            samples = np.frombuffer(data, dtype="<f4").astype(np.float32, copy=True)
        elif self.encoding == "pcm_s16le":
            if len(data) % 2:
                raise RealtimeProtocolError("pcm_s16le payload length must be divisible by 2")
            samples = np.frombuffer(data, dtype="<i2").astype(np.float32) / 32768.0
        else:
            raise RealtimeProtocolError(f"Unsupported realtime audio encoding: {self.encoding}")

        if samples.size and not np.isfinite(samples).all():
            raise RealtimeProtocolError("Realtime audio contains non-finite samples")

        return np.clip(samples, -1.0, 1.0)

    def _make_chunk(self, samples: np.ndarray) -> RealtimeAudioChunk:
        samples = np.ascontiguousarray(samples, dtype=np.float32)
        rms = float(np.sqrt(np.mean(np.square(samples)))) if samples.size else 0.0
        return RealtimeAudioChunk(
            samples=samples,
            sample_rate=self.sample_rate,
            duration_seconds=float(samples.size / self.sample_rate),
            rms=rms,
            is_silence=rms < self.silence_rms,
        )

    def _seconds_to_samples(self, seconds: float) -> int:
        return max(1, int(round(seconds * self.sample_rate)))

    def _validate(self) -> None:
        if (
            isinstance(self.sample_rate, bool)
            or not isinstance(self.sample_rate, int)
            or not 8000 <= self.sample_rate <= 192000
        ):
            raise RealtimeProtocolError("Realtime sample_rate must be an integer from 8000 to 192000")
        if not isinstance(self.encoding, str) or self.encoding not in SUPPORTED_ENCODINGS:
            raise RealtimeProtocolError("Unsupported realtime audio encoding")
        for name, lower, upper in (
            ("chunk_seconds", MIN_CHUNK_SECONDS, MAX_CHUNK_SECONDS),
            ("min_chunk_seconds", MIN_CHUNK_SECONDS, MAX_CHUNK_SECONDS),
            ("max_buffer_seconds", MIN_CHUNK_SECONDS, MAX_BUFFER_SECONDS),
            ("silence_rms", 0, 1),
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or not lower <= value <= upper
            ):
                raise RealtimeProtocolError(f"Realtime {name} must be between {lower} and {upper}")
        if max(self.min_chunk_seconds, self.chunk_seconds) > self.max_buffer_seconds:
            raise RealtimeProtocolError("Realtime chunk durations must not exceed the buffer")
