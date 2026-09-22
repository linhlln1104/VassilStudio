from __future__ import annotations

import threading
import unicodedata
from dataclasses import dataclass

import numpy as np

from vvoice.core.brand import prepare_spoken_brand_text
from vvoice.core.config import RuntimeSettings, TtsModelSettings, TtsSettings
from vvoice.core.errors import ModelConfigurationError
from vvoice.domains.tts.parameters import validate_tts_parameters
from vvoice.domains.tts.text_frontend import ZipVoiceTextFrontend
from vvoice.domains.tts.zipvoice_onnx import ZipVoiceOnnxRuntime
from vvoice.shared.language import DEFAULT_LANGUAGE, normalize_language


@dataclass(frozen=True)
class GeneratedSpeech:
    samples: np.ndarray
    sample_rate: int
    duration_seconds: float


class ZipVoiceService:
    def __init__(self, settings: TtsSettings, runtime: RuntimeSettings) -> None:
        self._settings = settings
        self._runtime = runtime
        self._tts_by_language: dict[str, ZipVoiceOnnxRuntime] = {}
        self._locks = {language: threading.Lock() for language in settings.models}
        self._inference_locks = {language: threading.Lock() for language in settings.models}
        self._text_frontend = ZipVoiceTextFrontend()

    def synthesize(
        self,
        *,
        text: str,
        reference_audio: np.ndarray,
        reference_sample_rate: int,
        reference_text: str,
        language: str = DEFAULT_LANGUAGE,
        num_steps: int | None = None,
        speed: float | None = None,
    ) -> GeneratedSpeech:
        normalized_language = normalize_language(language)
        model_settings = self._model_settings(normalized_language)
        tts = self._get_tts(normalized_language)
        effective_num_steps = int(num_steps or model_settings.default_num_steps)
        effective_speed = float(speed or model_settings.default_speed)
        validate_tts_parameters(effective_num_steps, effective_speed)

        with self._inference_locks[normalized_language]:
            audio = tts.synthesize(
                text=prepare_spoken_brand_text(text),
                reference_audio=reference_audio,
                reference_sample_rate=reference_sample_rate,
                reference_text=prepare_spoken_brand_text(reference_text),
                num_steps=effective_num_steps,
                speed=effective_speed,
            )
        duration = float(len(audio.samples) / audio.sample_rate) if audio.sample_rate else 0.0
        return GeneratedSpeech(
            samples=audio.samples,
            sample_rate=audio.sample_rate,
            duration_seconds=duration,
        )

    @property
    def is_loaded(self) -> bool:
        return bool(self._tts_by_language)

    @property
    def loaded_languages(self) -> tuple[str, ...]:
        return tuple(sorted(self._tts_by_language))

    @property
    def configured_languages(self) -> tuple[str, ...]:
        return tuple(sorted(self._settings.models))

    def sample_rate_for(self, language: str | None = None) -> int:
        if not self._settings.enabled:
            raise ModelConfigurationError("TTS is disabled in this workspace")
        return self._model_settings(language).sample_rate

    def warmup(self, language: str | None = None) -> None:
        self._get_tts(normalize_language(language or self._settings.default_language))

    def warmup_all(self) -> None:
        if not self._settings.enabled:
            return
        for language in self.configured_languages:
            self.warmup(language)

    def _model_settings(self, language: str | None) -> TtsModelSettings:
        if not self._settings.enabled:
            raise ModelConfigurationError("TTS is disabled in this workspace")
        return self._settings.model_for(language)

    def _get_tts(self, language: str):
        normalized_language = normalize_language(language)
        if normalized_language in self._tts_by_language:
            return self._tts_by_language[normalized_language]

        lock = self._locks.setdefault(normalized_language, threading.Lock())
        with lock:
            if normalized_language not in self._tts_by_language:
                model_settings = self._model_settings(normalized_language)
                self._validate_files(model_settings)
                runtime = ZipVoiceOnnxRuntime(
                    model_settings=model_settings,
                    runtime_settings=self._runtime,
                    text_frontend=self._text_frontend,
                )
                runtime.load()
                self._tts_by_language[normalized_language] = runtime
                self._inference_locks.setdefault(normalized_language, threading.Lock())

        return self._tts_by_language[normalized_language]

    def _validate_files(self, model_settings: TtsModelSettings) -> None:
        missing = [
            path
            for path in [
                model_settings.tokens,
                model_settings.encoder,
                model_settings.decoder,
                model_settings.vocoder,
                model_settings.data_dir,
            ]
            if not path.exists()
        ]
        if missing:
            rendered = ", ".join(str(path) for path in missing)
            raise ModelConfigurationError(
                f"Missing ZipVoice model files for language '{model_settings.language}': {rendered}"
            )


def _normalize_zipvoice_text(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).strip().lower().split())
