from __future__ import annotations

import logging
import threading
import unicodedata
from dataclasses import asdict, replace
from contextlib import contextmanager
from pathlib import Path
import re

import numpy as np

from vvoice.core.brand import prepare_spoken_brand_text
from vvoice.core.config import RuntimeSettings, TtsSettings, TtsProfileSettings
from vvoice.core.errors import ModelConfigurationError, VVoiceError
from vvoice.domains.tts.parameters import validate_tts_parameters
from vvoice.inference.tts.base import GeneratedSpeech as GeneratedSpeech
from vvoice.inference.tts.registry import TtsRegistry, default_registry
from vvoice.shared.language import normalize_language
from vvoice.inference.admission import DEFAULT_GATE
from vvoice.inference.deployments import DeploymentStore


logger = logging.getLogger("vvoice.models.tts")


class TtsService:
    """Route workflow requests to named adapters; never infer an engine from language."""

    def __init__(
        self, settings: TtsSettings, runtime: RuntimeSettings,
        registry: TtsRegistry | None = None,
        *, state_path: Path | None = None, admission=None,
    ) -> None:
        self._settings = settings
        self._runtime = runtime
        self._admission = admission or DEFAULT_GATE
        root = next(iter(settings.profiles.values())).root if settings.profiles else Path.cwd()
        self._deployments = DeploymentStore(state_path or root / 'data/model-deployments.sqlite3', settings.profiles)
        self._registry = registry or default_registry()
        profiles = dict(settings.profiles)
        for definition in self._deployments.registrations():
            profile = self._parse_import(definition, root)
            profiles[profile.model_id] = profile
        self._settings = replace(settings, profiles=profiles)
        self._deployments.profiles = profiles
        self._adapters = {
            model_id: self._registry.create(profile, runtime)
            for model_id, profile in profiles.items()
        }
        self._locks = {model_id: threading.RLock() for model_id in self._adapters}
        self._loaded: set[str] = set()
        self._loaded_versions: dict[str, str] = {}
        self._failed: set[str] = set()
        self._closed = threading.Event()
        self.max_resident_models = 1

    def resolve_model_id(self, language: str | None = None, model_id: str | None = None) -> str:
        self._ensure_open()
        if not self._settings.enabled:
            raise ModelConfigurationError("TTS is disabled in this workspace")
        language = normalize_language(language or self._settings.default_language)
        selected = (
            model_id.strip() if model_id is not None
            else self._settings.default_models.get(language)
        )
        profile = self._settings.profiles.get(selected or "")
        if profile is None:
            raise VVoiceError(f"TTS model '{selected or ''}' is not configured.")
        if language not in profile.languages:
            raise VVoiceError(
                f"TTS model '{selected}' does not support language '{language}'."
            )
        return profile.model_id

    def validate_request(
        self, *, language: str | None = None, model_id: str | None = None,
        num_steps: int | None = None, speed: float | None = None,
    ) -> str:
        selected = self.resolve_model_id(language, model_id)
        if not self._deployments.enabled(selected):
            raise ModelConfigurationError(f"TTS model '{selected}' is disabled by an operator.")
        validate_tts_parameters(num_steps, speed)
        capabilities = self._adapters[selected].capabilities
        if num_steps is not None and not capabilities.num_steps:
            raise VVoiceError(f"TTS model '{selected}' does not support num_steps.")
        if speed not in (None, 1.0) and not capabilities.speed:
            raise VVoiceError(f"TTS model '{selected}' does not support speed control.")
        return selected

    def synthesize(
        self, *, text: str, reference_audio: np.ndarray, reference_sample_rate: int,
        reference_text: str, language: str | None = None, model_id: str | None = None,
        num_steps: int | None = None, speed: float | None = None,
    ) -> GeneratedSpeech:
        language = normalize_language(language or self._settings.default_language)
        selected = self.validate_request(
            language=language, model_id=model_id, num_steps=num_steps, speed=speed,
        )
        with self._admission.enter(), self._locks[selected]:
            self._load(selected)
            audio = self._adapters[selected].synthesize(
                text=prepare_spoken_brand_text(text), reference_audio=reference_audio,
                reference_sample_rate=reference_sample_rate,
                reference_text=prepare_spoken_brand_text(reference_text), language=language,
                num_steps=num_steps, speed=speed,
            )
            samples = np.asarray(audio.samples, dtype=np.float32)
            expected_rate = self._settings.profiles[selected].sample_rate
            if (audio.sample_rate != expected_rate or samples.ndim != 1
                    or not samples.size or not np.isfinite(samples).all()):
                raise ModelConfigurationError(f"TTS model '{selected}' returned invalid audio.")
            return GeneratedSpeech(samples, audio.sample_rate, len(samples) / audio.sample_rate)

    def sample_rate_for(self, language: str | None = None, model_id: str | None = None) -> int:
        return self._settings.profiles[self.resolve_model_id(language, model_id)].sample_rate

    @property
    def is_loaded(self) -> bool:
        return bool(self._live_model_ids())

    def _live_model_ids(self) -> set[str]:
        if self._closed.is_set():
            return set()
        return {model_id for model_id in tuple(self._loaded)
                if getattr(self._adapters[model_id], "is_loaded", True)}

    @property
    def loaded_languages(self) -> tuple[str, ...]:
        return tuple(sorted({language for model_id in self._live_model_ids()
                             for language in self._settings.profiles[model_id].languages}))

    @property
    def configured_languages(self) -> tuple[str, ...]:
        return tuple(sorted(self._settings.default_models))

    def warmup(self, language: str | None = None, model_id: str | None = None) -> None:
        if language is None and model_id in self._settings.profiles:
            language = self._settings.profiles[model_id].languages[0]
        selected = self.resolve_model_id(language, model_id)
        if not self._deployments.enabled(selected):
            raise ModelConfigurationError(f"TTS model '{selected}' is disabled by an operator.")
        with self._admission.enter(), self._locks[selected]:
            self._load(selected)

    def unload(self, model_id: str) -> None:
        if model_id not in self._adapters:
            raise ModelConfigurationError('Unknown model deployment')
        with self._admission.enter(), self._locks[model_id]:
            self._close_adapter(model_id)
            self._loaded.discard(model_id)

    def set_enabled(self, model_id: str, enabled: bool) -> None:
        with self._admission.enter():
            if enabled:
                self._deployments.require_activation_before_enable(model_id)
            if not enabled:
                self.unload(model_id)
            self._deployments.set_enabled(model_id, enabled)

    def deployment_versions(self) -> dict:
        return self._deployments.list()

    def activate(self, model_id: str) -> dict:
        if model_id not in self._adapters:
            raise ModelConfigurationError('Unknown model deployment')
        with self._admission.enter():
            missing = [k for k, v in self._adapters[model_id].checks().items() if not v]
            if missing:
                raise ModelConfigurationError('Cannot activate model with missing assets/dependencies')
            self.unload(model_id)
            return self._deployments.activate(model_id)

    @staticmethod
    def _parse_import(definition, root):
        model_id = definition.get('model_id', '')
        if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}', model_id):
            raise VVoiceError('Model ID must contain 1–80 letters, numbers, dots, dashes or underscores')
        engine = definition.get('engine')
        if not isinstance(engine, str) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}', engine):
            raise VVoiceError('Engine must identify an explicitly registered adapter')
        languages = tuple(normalize_language(v) for v in definition.get('languages', []))
        if not languages:
            raise VVoiceError('At least one language is required')
        sample_rate = definition.get('sample_rate', 24000)
        if isinstance(sample_rate, bool) or not isinstance(sample_rate, int) or not 8000 <= sample_rate <= 192000:
            raise VVoiceError('Invalid model sample rate')
        options = definition.get('options', {})
        if not isinstance(options, dict):
            raise VVoiceError('Model options must be an object')
        return TtsProfileSettings(model_id=model_id, engine=engine,
            label=str(definition.get('label') or model_id)[:160], languages=languages,
            sample_rate=sample_rate, root=root, options=options)

    def import_profile(self, definition: dict) -> dict:
        root = next(iter(self._settings.profiles.values())).root
        profile = self._parse_import(definition, root)
        # Construction validates the explicit registered engine; never import arbitrary code.
        adapter = self._registry.create(profile, self._runtime)
        with self._admission.enter():
            if profile.model_id in self._adapters:
                self.unload(profile.model_id)
            profiles = {**self._settings.profiles, profile.model_id: profile}
            self._settings = replace(self._settings, profiles=profiles)
            self._deployments.profiles = profiles
            self._adapters[profile.model_id] = adapter
            self._locks.setdefault(profile.model_id, threading.RLock())
            self._failed.discard(profile.model_id)
            self._deployments.register(definition)
            # Imported/replaced profiles require an explicit activation after checks.
            self._deployments.set_enabled(profile.model_id, False)
        return self.model_catalog()

    def rollback(self, model_id: str, version: str) -> dict:
        saved = self._deployments.version(model_id, version)
        definition = saved.get('profile')
        if not definition:
            raise ModelConfigurationError('This legacy version has no restorable profile')
        root = self._settings.profiles[model_id].root
        profile = self._parse_import(definition, root)
        probe = DeploymentStore(self._deployments.path, {model_id: profile})
        if probe.snapshot(model_id, force=True)['deployment_version'] != version:
            raise ModelConfigurationError('Restore the recorded weights/runtime first; this version is no longer installed')
        self.import_profile(definition)
        self.activate(model_id)
        return self.model_catalog()

    def resolve_parameters(self, language=None, model_id=None, num_steps=None, speed=None) -> dict:
        selected = self.validate_request(language=language, model_id=model_id,
                                         num_steps=num_steps, speed=speed)
        adapter = self._adapters[selected]
        options = self._settings.profiles[selected].options
        snapshot = self._deployments.snapshot(selected)
        return {
            'model_id': selected, 'language': normalize_language(language or self._settings.default_language),
            'num_steps': (options.get('default_num_steps', 8) if num_steps is None else num_steps)
                         if adapter.capabilities.num_steps else None,
            'speed': (options.get('default_speed', 1.0) if speed is None else speed)
                     if adapter.capabilities.speed else None,
            'deployment_version': snapshot['deployment_version'], 'engine': snapshot['engine'],
            'runtime_version': snapshot['runtime_version'],
            'text_normalizer_version': snapshot['text_normalizer_version'],
            'model_manifest': snapshot,
        }

    def assert_deployment(self, model_id: str, version: str) -> None:
        if self._deployments.snapshot(model_id)['deployment_version'] != version:
            raise ModelConfigurationError('The accepted model assets changed. Restore that deployment or create a new take.')

    @contextmanager
    def deployment_guard(self, model_id: str, version: str | None):
        # Lifecycle actions cannot replace a deployment between validation and synthesis.
        with self._admission.enter():
            if version:
                self.assert_deployment(model_id, version)
            yield

    def warmup_all(self) -> None:
        if not self._settings.enabled:
            return
        # Optional alternatives must not block startup of the configured defaults.
        for selected in dict.fromkeys(self._settings.default_models.values()):
            profile = self._settings.profiles[selected]
            self.warmup(profile.languages[0], selected)

    def _load(self, selected: str) -> None:
        # The caller holds the model lock. A request admitted before shutdown may
        # still be preparing its reference audio when close() begins.
        self._ensure_open()
        version = self._deployments.snapshot(selected)['deployment_version']
        if selected in self._live_model_ids():
            if self._loaded_versions.get(selected) == version:
                return
            # On-disk changes must never be labelled as the old resident model.
            self._close_adapter(selected)
            self._loaded.discard(selected)
        for old in tuple(self._live_model_ids()):
            if old != selected and len(self._live_model_ids()) >= self.max_resident_models:
                with self._locks[old]:
                    self._close_adapter(old)
                    self._loaded.discard(old)
        self._loaded.discard(selected)
        try:
            self._adapters[selected].load()
        except Exception:
            self._failed.add(selected)
            logger.exception("tts_model_load_failed", extra={"model_id": selected})
            self._close_adapter(selected)
            raise
        self._loaded.add(selected)
        self._loaded_versions[selected] = version
        self._failed.discard(selected)

    def model_catalog(self) -> dict:
        models = []
        live_models = self._live_model_ids()
        for model_id, profile in self._settings.profiles.items():
            adapter = self._adapters[model_id]
            checks = adapter.checks()
            missing = [name for name, ok in checks.items() if not ok]
            loaded = model_id in live_models
            enabled = self._settings.enabled and self._deployments.enabled(model_id)
            if not enabled:
                status, message = "disabled", "TTS is disabled in this workspace."
            elif missing:
                status = ("missing_dependency" if any(name.startswith("dependency_")
                          for name in missing) else "missing_assets")
                message = "Missing: " + ", ".join(missing) + ". See the model setup guide."
            elif model_id in self._failed:
                status, message = "error", "Model initialization failed. Check the server logs."
            else:
                status = "loaded" if loaded else "available"
                message = None if loaded else "Ready to load on the first request."
            models.append({
                "model_id": model_id, "engine": profile.engine, "label": profile.label,
                "languages": list(profile.languages), "sample_rate": profile.sample_rate,
                "capabilities": asdict(adapter.capabilities), "checks": checks,
                "ready": enabled and not missing and model_id not in self._failed,
                "loaded": loaded, "status": status, "message": message,
            })
        return {"default_models": dict(self._settings.default_models), "models": models}

    def readiness_checks(self) -> dict[str, bool]:
        if not self._settings.enabled:
            return {}
        defaults = set(self._settings.default_models.values())
        return {
            f"tts_{model['model_id']}_{name}": ok
            for model in self.model_catalog()["models"] if model["model_id"] in defaults
            for name, ok in {**model["checks"], "enabled": model["status"] != "disabled",
                             "initialization": model["status"] != "error"}.items()
        }

    def close(self) -> None:
        self._closed.set()
        for model_id in self._adapters:
            with self._locks[model_id]:
                self._close_adapter(model_id)
        self._loaded.clear()

    def _ensure_open(self) -> None:
        if self._closed.is_set():
            raise ModelConfigurationError("TTS service is shutting down.")

    def _close_adapter(self, model_id: str) -> None:
        try:
            self._adapters[model_id].close()
        except Exception:
            logger.exception("tts_model_cleanup_failed", extra={"model_id": model_id})


# Backward-compatible imports; new code depends on the engine-neutral service.
ZipVoiceService = TtsService


def _normalize_zipvoice_text(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).strip().lower().split())
