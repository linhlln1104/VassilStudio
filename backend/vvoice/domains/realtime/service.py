from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from vvoice.core.config import RealtimeSettings
from vvoice.core.errors import VVoiceError


SUPPORTED_ENCODINGS = {"pcm_f32le", "pcm_s16le"}


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
        sample_rate = int(payload.get("sample_rate", self.sample_rate))
        if sample_rate != self.sample_rate:
            raise RealtimeProtocolError(
                f"Realtime ASR expects {self.sample_rate} Hz PCM, got {sample_rate} Hz"
            )

        self.encoding = str(payload.get("encoding", self.encoding))
        self.chunk_seconds = float(payload.get("chunk_seconds", self.chunk_seconds))
        self.min_chunk_seconds = float(payload.get("min_chunk_seconds", self.min_chunk_seconds))
        self.max_buffer_seconds = float(payload.get("max_buffer_seconds", self.max_buffer_seconds))
        self.silence_rms = float(payload.get("silence_rms", self.silence_rms))
        self._validate()

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

        if self._buffer.size > self._seconds_to_samples(self.max_buffer_seconds):
            self._buffer = self._buffer[-self._seconds_to_samples(self.max_buffer_seconds) :]

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
        if self.sample_rate <= 0:
            raise RealtimeProtocolError("Realtime sample_rate must be positive")
        if self.encoding not in SUPPORTED_ENCODINGS:
            raise RealtimeProtocolError(f"Unsupported realtime audio encoding: {self.encoding}")
        if self.chunk_seconds <= 0:
            raise RealtimeProtocolError("Realtime chunk_seconds must be positive")
        if self.min_chunk_seconds <= 0:
            raise RealtimeProtocolError("Realtime min_chunk_seconds must be positive")
        if self.max_buffer_seconds < self.chunk_seconds:
            raise RealtimeProtocolError("Realtime max_buffer_seconds must be >= chunk_seconds")
        if self.silence_rms < 0:
            raise RealtimeProtocolError("Realtime silence_rms must be non-negative")
