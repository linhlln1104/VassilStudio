from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from vvoice.core.env import first_env
from vvoice.core.errors import VVoiceError
from vvoice.shared.language import DEFAULT_LANGUAGE, normalize_language


PACKAGE_PROJECT_ROOT = Path(__file__).resolve().parents[3]
PROJECT_ROOT = Path(first_env("VASSIL_ROOT", "VVOICE_ROOT") or PACKAGE_PROJECT_ROOT).resolve()
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "vassil.example.json"
LEGACY_DEFAULT_CONFIG = PROJECT_ROOT / "config" / "vvoice.example.json"


@dataclass(frozen=True)
class PathSettings:
    models_root: Path
    data_root: Path
    logs_root: Path


@dataclass(frozen=True)
class RuntimeSettings:
    provider: str
    num_threads: int
    debug: bool


@dataclass(frozen=True)
class AsrModelSettings:
    language: str
    sample_rate: int
    feature_dim: int
    decoding_method: str
    encoder: Path
    decoder: Path
    joiner: Path
    tokens: Path


@dataclass(frozen=True)
class AsrSettings:
    enabled: bool
    default_language: str
    models: dict[str, AsrModelSettings]

    @property
    def default_model(self) -> AsrModelSettings:
        return self.model_for(self.default_language)

    def model_for(self, language: str | None) -> AsrModelSettings:
        normalized = normalize_language(language)
        model = self.models.get(normalized)
        if model is None:
            configured = ", ".join(sorted(self.models)) or "none"
            raise VVoiceError(
                f"ASR language '{normalized}' is not configured. "
                f"Configured ASR languages: {configured}. "
                f"Add a model profile under asr.models.{normalized}."
            )
        return model

    @property
    def sample_rate(self) -> int:
        return self.default_model.sample_rate

    @property
    def feature_dim(self) -> int:
        return self.default_model.feature_dim

    @property
    def decoding_method(self) -> str:
        return self.default_model.decoding_method

    @property
    def encoder(self) -> Path:
        return self.default_model.encoder

    @property
    def decoder(self) -> Path:
        return self.default_model.decoder

    @property
    def joiner(self) -> Path:
        return self.default_model.joiner

    @property
    def tokens(self) -> Path:
        return self.default_model.tokens


@dataclass(frozen=True)
class TtsModelSettings:
    language: str
    label: str
    sample_rate: int
    default_num_steps: int
    default_speed: float
    min_char_in_sentence: int
    tokens: Path
    encoder: Path
    decoder: Path
    vocoder: Path
    data_dir: Path
    lexicon: Path


@dataclass(frozen=True)
class TtsSettings:
    enabled: bool
    sample_rate: int
    default_language: str
    models: dict[str, TtsModelSettings]

    @property
    def default_model(self) -> TtsModelSettings:
        return self.model_for(self.default_language)

    def model_for(self, language: str | None) -> TtsModelSettings:
        normalized = normalize_language(language)
        model = self.models.get(normalized)
        if model is None:
            configured = ", ".join(sorted(self.models)) or "none"
            raise VVoiceError(
                f"TTS language '{normalized}' is not configured. "
                f"Configured TTS languages: {configured}. "
                f"Add a model profile under tts.models.{normalized}."
            )
        return model

    @property
    def default_num_steps(self) -> int:
        return self.default_model.default_num_steps

    @property
    def default_speed(self) -> float:
        return self.default_model.default_speed

    @property
    def min_char_in_sentence(self) -> int:
        return self.default_model.min_char_in_sentence

    @property
    def tokens(self) -> Path:
        return self.default_model.tokens

    @property
    def encoder(self) -> Path:
        return self.default_model.encoder

    @property
    def decoder(self) -> Path:
        return self.default_model.decoder

    @property
    def vocoder(self) -> Path:
        return self.default_model.vocoder

    @property
    def data_dir(self) -> Path:
        return self.default_model.data_dir

    @property
    def lexicon(self) -> Path:
        return self.default_model.lexicon


@dataclass(frozen=True)
class StorageSettings:
    data_dir: Path
    voices_dir: Path
    asr_jobs_dir: Path
    tts_jobs_dir: Path
    uploads_dir: Path
    outputs_dir: Path
    logs_dir: Path


@dataclass(frozen=True)
class SecuritySettings:
    api_keys: tuple[str, ...]


@dataclass(frozen=True)
class RealtimeSettings:
    enabled: bool
    encoding: str
    chunk_seconds: float
    min_chunk_seconds: float
    max_buffer_seconds: float
    silence_rms: float


@dataclass(frozen=True)
class JobSettings:
    asr_max_workers: int
    tts_max_workers: int


@dataclass(frozen=True)
class Settings:
    root: Path
    paths: PathSettings
    runtime: RuntimeSettings
    asr: AsrSettings
    tts: TtsSettings
    realtime: RealtimeSettings
    jobs: JobSettings
    storage: StorageSettings
    security: SecuritySettings


def load_settings(config_path: str | os.PathLike[str] | None = None) -> Settings:
    root = _settings_root()
    selected = Path(
        config_path
        or first_env("VASSIL_CONFIG", "VVOICE_CONFIG")
        or _default_config_for(root)
    )
    if not selected.is_absolute():
        selected = root / selected

    raw = json.loads(selected.read_text(encoding="utf-8"))
    return parse_settings(raw, _settings_root(selected))


def _default_config_for(root: Path) -> Path:
    canonical = root / "config" / "vassil.example.json"
    if canonical.is_file():
        return canonical
    return root / "config" / "vvoice.example.json"


def parse_settings(raw: dict[str, Any], root: Path) -> Settings:
    paths_raw = raw.get("paths", {})
    runtime = raw["runtime"]
    asr = raw["asr"]
    tts = raw["tts"]
    realtime = raw.get("realtime", {})
    jobs = raw.get("jobs", {})
    storage = raw["storage"]
    security = raw.get("security", {})
    paths = PathSettings(
        models_root=_resolve(root, paths_raw.get("models_root", "models")),
        data_root=_resolve(root, paths_raw.get("data_root", "data")),
        logs_root=_resolve(root, paths_raw.get("logs_root", "logs")),
    )

    return Settings(
        root=root,
        paths=paths,
        runtime=RuntimeSettings(
            provider=str(runtime.get("provider", "cpu")),
            num_threads=int(runtime.get("num_threads", 1)),
            debug=bool(runtime.get("debug", False)),
        ),
        asr=_parse_asr_settings(asr, root),
        tts=_parse_tts_settings(tts, root),
        realtime=RealtimeSettings(
            enabled=bool(realtime.get("enabled", True)),
            encoding=str(realtime.get("encoding", "pcm_f32le")),
            chunk_seconds=float(realtime.get("chunk_seconds", 3.0)),
            min_chunk_seconds=float(realtime.get("min_chunk_seconds", 0.6)),
            max_buffer_seconds=float(realtime.get("max_buffer_seconds", 12.0)),
            silence_rms=float(realtime.get("silence_rms", 0.003)),
        ),
        jobs=JobSettings(
            asr_max_workers=_positive_int(jobs.get("asr_max_workers", 1), "jobs.asr_max_workers"),
            tts_max_workers=_positive_int(jobs.get("tts_max_workers", 1), "jobs.tts_max_workers"),
        ),
        storage=StorageSettings(
            data_dir=_resolve(root, storage.get("data_dir", paths.data_root)),
            voices_dir=_resolve(root, storage.get("voices_dir", paths.data_root / "voices")),
            asr_jobs_dir=_resolve(root, storage.get("asr_jobs_dir", paths.data_root / "jobs" / "asr")),
            tts_jobs_dir=_resolve(root, storage.get("tts_jobs_dir", paths.data_root / "jobs" / "tts")),
            uploads_dir=_resolve(root, storage.get("uploads_dir", paths.data_root / "uploads")),
            outputs_dir=_resolve(root, storage.get("outputs_dir", paths.data_root / "outputs")),
            logs_dir=_resolve(root, storage.get("logs_dir", paths.logs_root)),
        ),
        security=SecuritySettings(
            api_keys=_parse_api_keys(security.get("api_keys", [])),
        ),
    )


def _resolve(root: Path, value: str | os.PathLike[str]) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def _positive_int(value: Any, name: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise ValueError(f"{name} must be greater than 0.")
    return parsed


def _parse_asr_settings(raw: dict[str, Any], root: Path) -> AsrSettings:
    default_language = normalize_language(raw.get("default_language", DEFAULT_LANGUAGE))
    defaults = {
        "sample_rate": int(raw.get("sample_rate", 16000)),
        "feature_dim": int(raw.get("feature_dim", 80)),
        "decoding_method": str(raw.get("decoding_method", "greedy_search")),
    }

    raw_models = raw.get("models")
    if raw_models:
        models = {
            normalize_language(language): _parse_asr_model_settings(
                model_raw,
                root=root,
                language=language,
                defaults=defaults,
            )
            for language, model_raw in raw_models.items()
        }
    else:
        models = {
            default_language: _parse_asr_model_settings(
                raw,
                root=root,
                language=default_language,
                defaults=defaults,
            )
        }

    if default_language not in models:
        configured = ", ".join(sorted(models)) or "none"
        raise ValueError(
            f"asr.default_language '{default_language}' is not configured. "
            f"Configured ASR languages: {configured}."
        )

    return AsrSettings(
        enabled=bool(raw.get("enabled", True)),
        default_language=default_language,
        models=models,
    )


def _parse_asr_model_settings(
    raw: dict[str, Any],
    *,
    root: Path,
    language: str,
    defaults: dict[str, int | str],
) -> AsrModelSettings:
    return AsrModelSettings(
        language=normalize_language(language),
        sample_rate=int(raw.get("sample_rate", defaults["sample_rate"])),
        feature_dim=int(raw.get("feature_dim", defaults["feature_dim"])),
        decoding_method=str(raw.get("decoding_method", defaults["decoding_method"])),
        encoder=_resolve(root, raw["encoder"]),
        decoder=_resolve(root, raw["decoder"]),
        joiner=_resolve(root, raw["joiner"]),
        tokens=_resolve(root, raw["tokens"]),
    )


def _parse_tts_settings(raw: dict[str, Any], root: Path) -> TtsSettings:
    default_language = normalize_language(raw.get("default_language", DEFAULT_LANGUAGE))
    default_sample_rate = int(raw.get("sample_rate", 24000))
    defaults = {
        "sample_rate": default_sample_rate,
        "default_num_steps": int(raw.get("default_num_steps", 16)),
        "default_speed": float(raw.get("default_speed", 1.0)),
        "min_char_in_sentence": int(raw.get("min_char_in_sentence", 30)),
    }

    raw_models = raw.get("models")
    if raw_models:
        models = {
            normalize_language(language): _parse_tts_model_settings(
                model_raw,
                root=root,
                language=language,
                label=str(model_raw.get("label", f"{normalize_language(language).upper()} ZipVoice")),
                defaults=defaults,
            )
            for language, model_raw in raw_models.items()
        }
    else:
        models = {
            default_language: _parse_tts_model_settings(
                raw,
                root=root,
                language=default_language,
                label=str(raw.get("label", f"{default_language.upper()} ZipVoice")),
                defaults=defaults,
            )
        }

    if default_language not in models:
        configured = ", ".join(sorted(models)) or "none"
        raise ValueError(
            f"tts.default_language '{default_language}' is not configured. "
            f"Configured TTS languages: {configured}."
        )

    return TtsSettings(
        enabled=bool(raw.get("enabled", True)),
        sample_rate=models[default_language].sample_rate,
        default_language=default_language,
        models=models,
    )


def _parse_tts_model_settings(
    raw: dict[str, Any],
    *,
    root: Path,
    language: str,
    label: str,
    defaults: dict[str, int | float],
) -> TtsModelSettings:
    return TtsModelSettings(
        language=normalize_language(language),
        label=label,
        sample_rate=int(raw.get("sample_rate", defaults["sample_rate"])),
        default_num_steps=int(raw.get("default_num_steps", defaults["default_num_steps"])),
        default_speed=float(raw.get("default_speed", defaults["default_speed"])),
        min_char_in_sentence=int(raw.get("min_char_in_sentence", defaults["min_char_in_sentence"])),
        tokens=_resolve(root, raw["tokens"]),
        encoder=_resolve(root, raw["encoder"]),
        decoder=_resolve(root, raw["decoder"]),
        vocoder=_resolve(root, raw["vocoder"]),
        data_dir=_resolve(root, raw["data_dir"]),
        lexicon=_resolve(root, raw.get("lexicon", raw["tokens"])),
    )


def _settings_root(config_path: Path | None = None) -> Path:
    configured = first_env("VASSIL_ROOT", "VVOICE_ROOT")
    if configured:
        return Path(configured).resolve()

    if config_path and config_path.is_absolute() and config_path.parent.name == "config":
        return config_path.parent.parent

    return PACKAGE_PROJECT_ROOT


def _parse_api_keys(value: Any) -> tuple[str, ...]:
    raw_keys: list[str] = []
    if isinstance(value, str):
        raw_keys.extend(value.split(","))
    elif isinstance(value, list | tuple):
        raw_keys.extend(str(item) for item in value)

    env_value = first_env("VASSIL_API_KEYS", "VVOICE_API_KEYS") or ""
    if env_value:
        raw_keys.extend(env_value.split(","))

    return tuple(key.strip() for key in raw_keys if key.strip())
