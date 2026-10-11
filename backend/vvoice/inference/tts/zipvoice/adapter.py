from __future__ import annotations

from vvoice.core.config import RuntimeSettings, TtsProfileSettings, _parse_tts_model_settings
from vvoice.core.errors import ModelConfigurationError, VVoiceError
from vvoice.domains.tts.parameters import validate_tts_parameters
from vvoice.inference.tts.base import (
    GeneratedSpeech, TtsCapabilities, module_available, usable_file,
)
from vvoice.inference.tts.zipvoice.runtime import ZipVoiceOnnxRuntime
from vvoice.inference.tts.zipvoice.text import ZipVoiceTextFrontend


class ZipVoiceAdapter:
    capabilities = TtsCapabilities(num_steps=True, speed=True)

    def __init__(self, profile: TtsProfileSettings, runtime: RuntimeSettings) -> None:
        if len(profile.languages) != 1:
            raise ModelConfigurationError("Each ZipVoice profile requires exactly one language.")
        self.model = _parse_tts_model_settings(
            profile.options, root=profile.root, language=profile.languages[0],
            label=profile.label,
            defaults={"sample_rate": profile.sample_rate, "default_num_steps": 8,
                      "default_speed": 1.0, "min_char_in_sentence": 30},
        )
        if self.model.sample_rate != profile.sample_rate:
            raise ModelConfigurationError("ZipVoice sample_rate must match the profile sample rate.")
        try:
            validate_tts_parameters(self.model.default_num_steps, self.model.default_speed)
        except VVoiceError as exc:
            raise ModelConfigurationError(f"Invalid ZipVoice defaults: {exc}") from exc
        self._runtime = ZipVoiceOnnxRuntime(
            model_settings=self.model, runtime_settings=runtime,
            text_frontend=ZipVoiceTextFrontend(),
        )

    def checks(self) -> dict[str, bool]:
        return {
            **{name: usable_file(getattr(self.model, name)) for name in (
                "tokens", "encoder", "decoder", "vocoder",
            )},
            # The direct frontend uses espeakng_loader's packaged library/data.
            # Legacy sherpa lexicon/data_dir paths remain parseable config only.
            **{f"dependency_{name}": module_available(name) for name in (
                "onnxruntime", "torch", "torchaudio", "phonemizer", "espeakng_loader",
            )},
        }

    def load(self) -> None:
        missing = [name for name, ok in self.checks().items() if not ok]
        if missing:
            raise ModelConfigurationError(
                "ZipVoice is not ready: " + ", ".join(missing)
                + '. Install .[zipvoice] and configure the model assets.'
            )
        self._runtime.load()

    def synthesize(self, *, language: str, num_steps=None, speed=None, **kwargs) -> GeneratedSpeech:
        audio = self._runtime.synthesize(
            **kwargs,
            num_steps=self.model.default_num_steps if num_steps is None else num_steps,
            speed=self.model.default_speed if speed is None else speed,
        )
        return GeneratedSpeech(audio.samples, audio.sample_rate, len(audio.samples) / audio.sample_rate)

    def close(self) -> None:
        self._runtime.close()
