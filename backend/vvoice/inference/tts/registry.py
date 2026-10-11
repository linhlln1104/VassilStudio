from __future__ import annotations

from collections.abc import Callable

from vvoice.core.config import RuntimeSettings, TtsProfileSettings
from vvoice.core.errors import ModelConfigurationError
from vvoice.inference.tts.base import TtsAdapter


AdapterFactory = Callable[[TtsProfileSettings, RuntimeSettings], TtsAdapter]


class TtsRegistry:
    """Explicit factories; config never imports arbitrary Python module paths."""

    def __init__(self) -> None:
        self._factories: dict[str, AdapterFactory] = {}

    def register(self, engine: str, factory: AdapterFactory) -> None:
        if not engine or engine in self._factories:
            raise ValueError(f"TTS engine already registered or empty: {engine!r}")
        self._factories[engine] = factory

    def create(self, profile: TtsProfileSettings, runtime: RuntimeSettings) -> TtsAdapter:
        factory = self._factories.get(profile.engine)
        if factory is None:
            raise ModelConfigurationError(f"Unknown TTS engine '{profile.engine}'.")
        return factory(profile, runtime)


def default_registry() -> TtsRegistry:
    from vvoice.inference.tts.zipvoice.adapter import ZipVoiceAdapter
    from vvoice.inference.tts.vieneu import VieneuAdapter

    registry = TtsRegistry()
    registry.register("zipvoice", ZipVoiceAdapter)
    registry.register("vieneu", VieneuAdapter)
    return registry
