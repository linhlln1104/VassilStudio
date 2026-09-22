from __future__ import annotations

import threading
from dataclasses import dataclass

import numpy as np

from vvoice.core.config import AsrModelSettings, AsrSettings, RuntimeSettings
from vvoice.core.errors import ModelConfigurationError
from vvoice.domains.asr.transcript import TranscriptSegment, timed_segments_from_result
from vvoice.shared.language import normalize_language


@dataclass(frozen=True)
class Transcription:
    text: str
    sample_rate: int
    segments: tuple[TranscriptSegment, ...] = ()


class AsrService:
    def __init__(self, settings: AsrSettings, runtime: RuntimeSettings) -> None:
        self._settings = settings
        self._runtime = runtime
        self._recognizers: dict[str, object] = {}
        self._locks = {language: threading.Lock() for language in settings.models}
        self._inference_locks = {language: threading.Lock() for language in settings.models}

    def transcribe(
        self,
        samples: np.ndarray,
        sample_rate: int,
        language: str | None = None,
    ) -> Transcription:
        normalized_language = normalize_language(language or self._settings.default_language)
        recognizer = self._get_recognizer(normalized_language)
        with self._inference_locks[normalized_language]:
            stream = recognizer.create_stream()
            stream.accept_waveform(sample_rate, samples)
            recognizer.decode_stream(stream)
        result = stream.result
        text = result.text.strip()
        audio_duration_seconds = len(samples) / sample_rate if sample_rate > 0 else 0.0
        return Transcription(
            text=text,
            sample_rate=sample_rate,
            segments=timed_segments_from_result(
                result,
                text=text,
                audio_duration_seconds=audio_duration_seconds,
            ),
        )

    @property
    def is_loaded(self) -> bool:
        return bool(self._recognizers)

    @property
    def loaded_languages(self) -> tuple[str, ...]:
        return tuple(sorted(self._recognizers))

    @property
    def configured_languages(self) -> tuple[str, ...]:
        return tuple(sorted(self._settings.models))

    def sample_rate_for(self, language: str | None = None) -> int:
        if not self._settings.enabled:
            raise ModelConfigurationError("ASR is disabled in this workspace")
        return self._settings.model_for(language).sample_rate

    def warmup(self, language: str | None = None) -> None:
        self._get_recognizer(normalize_language(language or self._settings.default_language))

    def warmup_all(self) -> None:
        if not self._settings.enabled:
            return
        for language in self.configured_languages:
            self.warmup(language)

    def _get_recognizer(self, language: str):
        if not self._settings.enabled:
            raise ModelConfigurationError("ASR is disabled in this workspace")
        normalized_language = normalize_language(language)
        if normalized_language in self._recognizers:
            return self._recognizers[normalized_language]

        lock = self._locks.setdefault(normalized_language, threading.Lock())
        with lock:
            if normalized_language not in self._recognizers:
                model_settings = self._settings.model_for(normalized_language)
                self._validate_files(model_settings)
                import sherpa_onnx

                self._recognizers[normalized_language] = sherpa_onnx.OfflineRecognizer.from_transducer(
                    encoder=str(model_settings.encoder),
                    decoder=str(model_settings.decoder),
                    joiner=str(model_settings.joiner),
                    tokens=str(model_settings.tokens),
                    num_threads=self._runtime.effective_asr_num_threads,
                    sample_rate=model_settings.sample_rate,
                    feature_dim=model_settings.feature_dim,
                    decoding_method=model_settings.decoding_method,
                    debug=self._runtime.debug,
                    provider=self._runtime.provider,
                )
                self._inference_locks.setdefault(normalized_language, threading.Lock())

        return self._recognizers[normalized_language]

    def _validate_files(self, model_settings: AsrModelSettings) -> None:
        missing = [
            path
            for path in [
                model_settings.encoder,
                model_settings.decoder,
                model_settings.joiner,
                model_settings.tokens,
            ]
            if not path.exists()
        ]
        if missing:
            rendered = ", ".join(str(path) for path in missing)
            raise ModelConfigurationError(
                f"Missing ASR model files for language '{model_settings.language}': {rendered}"
            )
