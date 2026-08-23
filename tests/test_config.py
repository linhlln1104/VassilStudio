import json
from pathlib import Path

import pytest

from vvoice.app.auth.service import LocalAuthService
from vvoice.core.config import load_settings, parse_settings
from vvoice.core.container import AppContainer


ROOT = Path(__file__).resolve().parents[1]


def _minimal_settings_raw() -> dict:
    return {
        "runtime": {"provider": "cpu", "num_threads": 2, "debug": False},
        "asr": {
            "encoder": "models/asr/encoder.onnx",
            "decoder": "models/asr/decoder.onnx",
            "joiner": "models/asr/joiner.onnx",
            "tokens": "models/asr/tokens.txt",
        },
        "tts": {
            "tokens": "models/tts/tokens.txt",
            "encoder": "models/tts/text_model.onnx",
            "decoder": "models/tts/flow_matching_model.onnx",
            "vocoder": "models/tts/vocos_24khz.onnx",
            "data_dir": "models/tts/espeak-ng-data",
        },
        "storage": {
            "voices_dir": "data/voices",
            "asr_jobs_dir": "data/jobs/asr",
            "tts_jobs_dir": "data/jobs/tts",
        },
        "security": {"api_keys": []},
    }


def test_env_example_points_to_existing_default_config() -> None:
    env_example = ROOT / ".env.example"
    values = {}
    for line in env_example.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        values[name] = value

    config_path = ROOT / values["VASSIL_CONFIG"]

    assert config_path.is_file()


def test_run_api_loads_local_env_file() -> None:
    script = ROOT.joinpath("scripts", "run_api.ps1").read_text(encoding="utf-8")

    assert "Import-LocalEnvFile" in script
    assert 'Join-Path $root ".env"' in script
    assert "--host $BindAddress" in script


def test_parse_settings_resolves_paths() -> None:
    root = Path("C:/workspace/Vassil-Studio")
    settings = parse_settings(
        {
            "paths": {
                "models_root": "models",
                "data_root": "data",
                "logs_root": "logs",
            },
            "runtime": {"provider": "cpu", "num_threads": 2, "debug": False},
            "asr": {
                "enabled": True,
                "sample_rate": 16000,
                "feature_dim": 80,
                "decoding_method": "greedy_search",
                "encoder": "models/runtime/asr/vi/zipformer/encoder.onnx",
                "decoder": "models/runtime/asr/vi/zipformer/decoder.onnx",
                "joiner": "models/runtime/asr/vi/zipformer/joiner.onnx",
                "tokens": "models/runtime/asr/vi/zipformer/tokens.txt",
            },
            "tts": {
                "enabled": True,
                "sample_rate": 24000,
                "default_num_steps": 4,
                "default_speed": 1.0,
                "min_char_in_sentence": 30,
                "tokens": "models/runtime/tts/vi/zipvoice/tokens.txt",
                "encoder": "models/runtime/tts/vi/zipvoice/text_model.onnx",
                "decoder": "models/runtime/tts/vi/zipvoice/flow_matching_model.onnx",
                "vocoder": "models/runtime/tts/vi/zipvoice/vocos_24khz.onnx",
                "data_dir": "models/runtime/tts/vi/zipvoice/espeak-ng-data",
                "lexicon": "models/runtime/tts/vi/zipvoice/pinyin_stub.txt",
            },
            "realtime": {
                "enabled": True,
                "encoding": "pcm_f32le",
                "chunk_seconds": 3.0,
                "min_chunk_seconds": 0.6,
                "max_buffer_seconds": 12.0,
                "silence_rms": 0.003,
            },
            "storage": {
                "data_dir": "data",
                "voices_dir": "data/voices",
                "asr_jobs_dir": "data/jobs/asr",
                "tts_jobs_dir": "data/jobs/tts",
                "uploads_dir": "data/uploads",
                "outputs_dir": "data/outputs",
                "logs_dir": "logs",
            },
            "security": {"api_keys": ["secret-1"]},
        },
        root,
    )

    assert settings.runtime.num_threads == 2
    assert settings.runtime.effective_asr_num_threads == 2
    assert settings.runtime.effective_tts_num_threads == 2
    assert settings.runtime.environment == "local"
    assert settings.runtime.bind_address == "127.0.0.1"
    assert settings.runtime.log_level == "INFO"
    assert settings.runtime.warmup_on_startup is False
    assert settings.paths.models_root == root / "models"
    assert settings.paths.data_root == root / "data"
    assert settings.paths.logs_root == root / "logs"
    assert settings.asr.encoder == root / "models/runtime/asr/vi/zipformer/encoder.onnx"
    assert settings.tts.vocoder == root / "models/runtime/tts/vi/zipvoice/vocos_24khz.onnx"
    assert settings.tts.default_language == "vi"
    assert settings.tts.model_for("vietnamese").language == "vi"
    assert settings.realtime.encoding == "pcm_f32le"
    assert settings.storage.data_dir == root / "data"
    assert settings.storage.asr_jobs_dir == root / "data/jobs/asr"
    assert settings.storage.tts_jobs_dir == root / "data/jobs/tts"
    assert settings.storage.uploads_dir == root / "data/uploads"
    assert settings.storage.outputs_dir == root / "data/outputs"
    assert settings.storage.logs_dir == root / "logs"
    assert settings.jobs.asr_max_workers == 1
    assert settings.jobs.tts_max_workers == 1
    assert settings.security.api_keys == ("secret-1",)
    assert settings.security.auth_required is False
    assert settings.security.auth_db_path == root / "data/auth.sqlite3"
    assert settings.security.session_cookie_name == "vassil_session"
    assert settings.security.session_ttl_seconds == 604800
    assert settings.security.secure_cookies is False


def test_load_settings_uses_vvoice_root_for_relative_paths(tmp_path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_path = config_dir / "vvoice.example.json"
    config_path.write_text(
        json.dumps(
            {
                "runtime": {"provider": "cpu", "num_threads": 2, "debug": False},
                "asr": {
                    "enabled": True,
                    "sample_rate": 16000,
                    "feature_dim": 80,
                    "decoding_method": "greedy_search",
                    "encoder": "models/asr/encoder.onnx",
                    "decoder": "models/asr/decoder.onnx",
                    "joiner": "models/asr/joiner.onnx",
                    "tokens": "models/asr/tokens.txt",
                },
                "tts": {
                    "enabled": True,
                    "sample_rate": 24000,
                    "default_num_steps": 4,
                    "default_speed": 1.0,
                    "min_char_in_sentence": 30,
                    "tokens": "models/tts/tokens.txt",
                    "encoder": "models/tts/text_model.onnx",
                    "decoder": "models/tts/flow_matching_model.onnx",
                    "vocoder": "models/tts/vocos_24khz.onnx",
                    "data_dir": "models/tts/espeak-ng-data",
                    "lexicon": "models/tts/pinyin_stub.txt",
                },
                "storage": {
                    "voices_dir": "data/voices",
                    "asr_jobs_dir": "data/jobs/asr",
                    "tts_jobs_dir": "data/jobs/tts",
                },
                "security": {"api_keys": []},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("VVOICE_ROOT", str(tmp_path))

    settings = load_settings(config_path)

    assert settings.root == tmp_path
    assert settings.asr.encoder == tmp_path / "models/asr/encoder.onnx"
    assert settings.storage.voices_dir == tmp_path / "data/voices"


def test_load_settings_uses_vassil_root_for_relative_paths(tmp_path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_path = config_dir / "vassil.example.json"
    config_path.write_text(
        json.dumps(
            {
                "runtime": {"provider": "cpu", "num_threads": 2, "debug": False},
                "asr": {
                    "encoder": "models/asr/encoder.onnx",
                    "decoder": "models/asr/decoder.onnx",
                    "joiner": "models/asr/joiner.onnx",
                    "tokens": "models/asr/tokens.txt",
                },
                "tts": {
                    "tokens": "models/tts/tokens.txt",
                    "encoder": "models/tts/text_model.onnx",
                    "decoder": "models/tts/flow_matching_model.onnx",
                    "vocoder": "models/tts/vocos_24khz.onnx",
                    "data_dir": "models/tts/espeak-ng-data",
                },
                "storage": {
                    "voices_dir": "data/voices",
                    "asr_jobs_dir": "data/jobs/asr",
                    "tts_jobs_dir": "data/jobs/tts",
                },
                "security": {"api_keys": []},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("VASSIL_ROOT", str(tmp_path))

    settings = load_settings(config_path)

    assert settings.root == tmp_path
    assert settings.asr.encoder == tmp_path / "models/asr/encoder.onnx"
    assert settings.storage.voices_dir == tmp_path / "data/voices"


def test_load_settings_uses_vassil_default_config(tmp_path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_dir.joinpath("vassil.example.json").write_text(
        json.dumps(_minimal_settings_raw()),
        encoding="utf-8",
    )

    monkeypatch.setenv("VASSIL_ROOT", str(tmp_path))

    settings = load_settings()

    assert settings.root == tmp_path
    assert settings.asr.encoder == tmp_path / "models/asr/encoder.onnx"
    assert settings.storage.voices_dir == tmp_path / "data/voices"


def test_load_settings_uses_vassil_config_env(tmp_path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_path = config_dir / "vassil.local.json"
    config_path.write_text(json.dumps(_minimal_settings_raw()), encoding="utf-8")

    monkeypatch.setenv("VASSIL_CONFIG", str(config_path))

    settings = load_settings()

    assert settings.root == tmp_path
    assert settings.asr.encoder == tmp_path / "models/asr/encoder.onnx"
    assert settings.storage.voices_dir == tmp_path / "data/voices"


def test_parse_settings_appends_vassil_api_keys(tmp_path, monkeypatch) -> None:
    raw = _minimal_settings_raw()
    raw["security"] = {"api_keys": ["file-secret"]}

    monkeypatch.setenv("VASSIL_API_KEYS", "env-secret-1, env-secret-2")

    settings = parse_settings(raw, tmp_path)

    assert settings.security.api_keys == ("file-secret", "env-secret-1", "env-secret-2")


def test_parse_settings_supports_local_auth_security_options(tmp_path, monkeypatch) -> None:
    raw = _minimal_settings_raw()
    raw["security"] = {
        "api_keys": [],
        "auth_required": False,
        "auth_db_path": "data/custom-auth.sqlite3",
        "session_cookie_name": "custom_session",
        "session_ttl_seconds": 120,
        "secure_cookies": False,
    }

    monkeypatch.setenv("VASSIL_AUTH_REQUIRED", "true")
    monkeypatch.setenv("VASSIL_SESSION_SECRET", "env-session-secret-with-at-least-32-chars")
    monkeypatch.setenv("VASSIL_SECURE_COOKIES", "1")

    settings = parse_settings(raw, tmp_path)

    assert settings.security.auth_required is True
    assert settings.security.auth_db_path == tmp_path / "data/custom-auth.sqlite3"
    assert settings.security.session_cookie_name == "custom_session"
    assert settings.security.session_ttl_seconds == 120
    assert settings.security.session_secret == "env-session-secret-with-at-least-32-chars"
    assert settings.security.secure_cookies is True


def test_parse_settings_applies_runtime_environment_overrides(tmp_path, monkeypatch) -> None:
    raw = _minimal_settings_raw()

    monkeypatch.setenv("VASSIL_ENV", "docker")
    monkeypatch.setenv("VASSIL_LOG_LEVEL", "warning")
    monkeypatch.setenv("VASSIL_ASR_NUM_THREADS", "3")
    monkeypatch.setenv("VASSIL_TTS_NUM_THREADS", "7")
    monkeypatch.setenv("VASSIL_WARMUP_ON_STARTUP", "true")

    settings = parse_settings(raw, tmp_path)

    assert settings.runtime.environment == "docker"
    assert settings.runtime.log_level == "WARNING"
    assert settings.runtime.effective_asr_num_threads == 3
    assert settings.runtime.effective_tts_num_threads == 7
    assert settings.runtime.warmup_on_startup is True


def test_parse_settings_requires_strong_session_secret_when_auth_is_enabled(tmp_path) -> None:
    raw = _minimal_settings_raw()
    raw["security"] = {
        "auth_required": True,
        "session_secret": "too-short",
    }

    with pytest.raises(ValueError, match="at least 32 characters"):
        parse_settings(raw, tmp_path)


def test_parse_settings_rejects_documented_session_secret_placeholder(tmp_path) -> None:
    raw = _minimal_settings_raw()
    raw["security"] = {
        "auth_required": True,
        "session_secret": "replace-with-random-32-plus-character-secret",
    }

    with pytest.raises(ValueError, match="documented placeholder"):
        parse_settings(raw, tmp_path)


@pytest.mark.parametrize("environment", ["production", "PRODUCTION"])
def test_parse_settings_accepts_hardened_production_profile(tmp_path, environment) -> None:
    raw = _minimal_settings_raw()
    raw["runtime"]["environment"] = environment
    raw["security"] = {
        "auth_required": True,
        "session_secret": "production-session-secret-0123456789",
        "secure_cookies": True,
    }

    settings = parse_settings(raw, tmp_path)

    assert settings.runtime.environment == "production"
    assert settings.security.auth_required is True
    assert settings.security.secure_cookies is True


def test_parse_settings_rejects_unsafe_production_profile(tmp_path) -> None:
    raw = _minimal_settings_raw()
    raw["runtime"]["environment"] = "production"

    with pytest.raises(ValueError, match="auth_required must be true"):
        parse_settings(raw, tmp_path)


@pytest.mark.parametrize("bind_address", ["0.0.0.0", "::", "192.168.1.20", "studio.local"])
def test_parse_settings_rejects_anonymous_non_loopback_bind(tmp_path, bind_address) -> None:
    raw = _minimal_settings_raw()
    raw["runtime"]["bind_address"] = bind_address

    with pytest.raises(ValueError, match="non-loopback.*requires owner authentication"):
        parse_settings(raw, tmp_path)


@pytest.mark.parametrize("bind_address", ["127.0.0.1", "127.10.20.30", "::1", "localhost"])
def test_parse_settings_allows_anonymous_loopback_bind(tmp_path, bind_address) -> None:
    raw = _minimal_settings_raw()
    raw["runtime"]["bind_address"] = bind_address

    settings = parse_settings(raw, tmp_path)

    assert settings.runtime.bind_address == bind_address


def test_parse_settings_allows_api_key_protected_non_loopback_bind(tmp_path) -> None:
    raw = _minimal_settings_raw()
    raw["runtime"]["bind_address"] = "0.0.0.0"
    raw["security"] = {"api_keys": ["automation-secret"]}

    settings = parse_settings(raw, tmp_path)

    assert settings.runtime.bind_address == "0.0.0.0"
    assert settings.security.api_keys == ("automation-secret",)


def test_parse_settings_allows_owner_auth_protected_non_loopback_bind(tmp_path) -> None:
    raw = _minimal_settings_raw()
    raw["runtime"]["bind_address"] = "0.0.0.0"
    raw["security"] = {
        "auth_required": True,
        "session_secret": "lan-session-secret-with-at-least-32-chars",
    }

    settings = parse_settings(raw, tmp_path)

    assert settings.runtime.bind_address == "0.0.0.0"
    assert settings.security.auth_required is True


def test_app_container_rejects_remote_first_owner_setup(tmp_path) -> None:
    raw = _minimal_settings_raw()
    raw["runtime"]["bind_address"] = "0.0.0.0"
    raw["security"] = {
        "auth_required": True,
        "auth_db_path": "data/auth.sqlite3",
        "session_secret": "lan-session-secret-with-at-least-32-chars",
    }
    settings = parse_settings(raw, tmp_path)

    with pytest.raises(ValueError, match="Complete owner setup on a loopback bind"):
        AppContainer(settings)


def test_app_container_allows_non_loopback_after_owner_setup(tmp_path) -> None:
    raw = _minimal_settings_raw()
    raw["runtime"]["bind_address"] = "0.0.0.0"
    raw["security"] = {
        "auth_required": True,
        "auth_db_path": "data/auth.sqlite3",
        "session_secret": "lan-session-secret-with-at-least-32-chars",
    }
    settings = parse_settings(raw, tmp_path)
    LocalAuthService(settings.security).create_owner("owner", "correct horse battery")

    container = AppContainer(settings)
    try:
        assert container.auth.setup_required is False
    finally:
        container.shutdown()


@pytest.mark.parametrize(
    ("runtime_patch", "security_patch", "message"),
    [
        ({"debug": True}, {}, "runtime.debug must be false"),
        ({}, {"secure_cookies": False}, "secure_cookies must be true"),
    ],
)
def test_parse_settings_enforces_production_runtime_invariants(
    tmp_path,
    runtime_patch,
    security_patch,
    message,
) -> None:
    raw = _minimal_settings_raw()
    raw["runtime"].update({"environment": "production", **runtime_patch})
    raw["security"] = {
        "auth_required": True,
        "session_secret": "production-session-secret-0123456789",
        "secure_cookies": True,
        **security_patch,
    }

    with pytest.raises(ValueError, match=message):
        parse_settings(raw, tmp_path)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("environment", "staging", "runtime.environment must be one of"),
        ("log_level", "verbose", "runtime.log_level must be one of"),
    ],
)
def test_parse_settings_rejects_unknown_runtime_options(tmp_path, field, value, message) -> None:
    raw = _minimal_settings_raw()
    raw["runtime"][field] = value

    with pytest.raises(ValueError, match=message):
        parse_settings(raw, tmp_path)


def test_parse_settings_supports_job_worker_limits(tmp_path) -> None:
    raw = _minimal_settings_raw()
    raw["jobs"] = {
        "asr_max_workers": 2,
        "tts_max_workers": 3,
        "asr_max_attempts": 4,
        "tts_max_attempts": 5,
        "retry_backoff_seconds": 0.25,
    }

    settings = parse_settings(raw, tmp_path)

    assert settings.jobs.asr_max_workers == 2
    assert settings.jobs.tts_max_workers == 3
    assert settings.jobs.asr_max_attempts == 4
    assert settings.jobs.tts_max_attempts == 5
    assert settings.jobs.retry_backoff_seconds == 0.25


def test_parse_settings_supports_request_limits(tmp_path) -> None:
    raw = _minimal_settings_raw()
    raw["limits"] = {
        "max_upload_bytes": 1024,
        "max_tts_text_chars": 120,
        "max_reference_text_chars": 80,
        "max_voice_name_chars": 32,
        "max_realtime_frame_bytes": 512,
    }

    settings = parse_settings(raw, tmp_path)

    assert settings.limits.max_upload_bytes == 1024
    assert settings.limits.max_tts_text_chars == 120
    assert settings.limits.max_reference_text_chars == 80
    assert settings.limits.max_voice_name_chars == 32
    assert settings.limits.max_realtime_frame_bytes == 512


def test_parse_settings_supports_startup_warmup(tmp_path) -> None:
    raw = _minimal_settings_raw()
    raw["runtime"]["warmup_on_startup"] = True

    settings = parse_settings(raw, tmp_path)

    assert settings.runtime.warmup_on_startup is True


def test_parse_settings_supports_tts_model_registry() -> None:
    root = Path("C:/workspace/Vassil-Studio")
    settings = parse_settings(
        {
            "runtime": {"provider": "cpu", "num_threads": 2, "debug": False},
            "asr": {
                "encoder": "models/asr/encoder.onnx",
                "decoder": "models/asr/decoder.onnx",
                "joiner": "models/asr/joiner.onnx",
                "tokens": "models/asr/tokens.txt",
            },
            "tts": {
                "enabled": True,
                "sample_rate": 24000,
                "default_language": "vi",
                "default_num_steps": 4,
                "default_speed": 1.0,
                "min_char_in_sentence": 30,
                "models": {
                    "vi": {
                        "label": "Vietnamese ZipVoice",
                        "tokens": "models/tts/vi/tokens.txt",
                        "encoder": "models/tts/vi/text_model.onnx",
                        "decoder": "models/tts/vi/flow_matching_model.onnx",
                        "vocoder": "models/tts/vi/vocos_24khz.onnx",
                        "data_dir": "models/tts/vi/espeak-ng-data",
                        "lexicon": "models/tts/vi/pinyin_stub.txt",
                    },
                    "en": {
                        "label": "English ZipVoice",
                        "sample_rate": 22050,
                        "default_num_steps": 8,
                        "tokens": "models/tts/en/tokens.txt",
                        "encoder": "models/tts/en/text_model.onnx",
                        "decoder": "models/tts/en/flow_matching_model.onnx",
                        "vocoder": "models/tts/en/vocos_24khz.onnx",
                        "data_dir": "models/tts/en/espeak-ng-data",
                        "lexicon": "models/tts/en/lexicon.txt",
                    },
                },
            },
            "storage": {
                "voices_dir": "data/voices",
                "asr_jobs_dir": "data/jobs/asr",
                "tts_jobs_dir": "data/jobs/tts",
            },
            "security": {"api_keys": []},
        },
        root,
    )

    assert settings.tts.default_language == "vi"
    assert settings.tts.sample_rate == 24000
    assert settings.tts.model_for("en-us").sample_rate == 22050
    assert settings.tts.model_for("en").default_num_steps == 8
    assert settings.tts.model_for("vi").encoder == root / "models/tts/vi/text_model.onnx"


def test_parse_settings_supports_asr_model_registry() -> None:
    root = Path("C:/workspace/Vassil-Studio")
    settings = parse_settings(
        {
            "runtime": {"provider": "cpu", "num_threads": 2, "debug": False},
            "asr": {
                "enabled": True,
                "sample_rate": 16000,
                "feature_dim": 80,
                "decoding_method": "greedy_search",
                "default_language": "vi",
                "models": {
                    "vi": {
                        "encoder": "models/asr/vi/encoder.onnx",
                        "decoder": "models/asr/vi/decoder.onnx",
                        "joiner": "models/asr/vi/joiner.onnx",
                        "tokens": "models/asr/vi/tokens.txt",
                    },
                    "en": {
                        "encoder": "models/asr/en/encoder.onnx",
                        "decoder": "models/asr/en/decoder.onnx",
                        "joiner": "models/asr/en/joiner.onnx",
                        "tokens": "models/asr/en/tokens.txt",
                    },
                },
            },
            "tts": {
                "enabled": True,
                "sample_rate": 24000,
                "tokens": "models/tts/tokens.txt",
                "encoder": "models/tts/text_model.onnx",
                "decoder": "models/tts/flow_matching_model.onnx",
                "vocoder": "models/tts/vocos_24khz.onnx",
                "data_dir": "models/tts/espeak-ng-data",
            },
            "storage": {
                "voices_dir": "data/voices",
                "asr_jobs_dir": "data/jobs/asr",
                "tts_jobs_dir": "data/jobs/tts",
            },
            "security": {"api_keys": []},
        },
        root,
    )

    assert settings.asr.default_language == "vi"
    assert settings.asr.model_for("en-us").encoder == root / "models/asr/en/encoder.onnx"
    assert settings.asr.encoder == root / "models/asr/vi/encoder.onnx"


def test_parse_settings_tts_lexicon_defaults_to_tokens() -> None:
    root = Path("C:/workspace/Vassil-Studio")
    settings = parse_settings(
        {
            "runtime": {"provider": "cpu", "num_threads": 2, "debug": False},
            "asr": {
                "encoder": "models/asr/encoder.onnx",
                "decoder": "models/asr/decoder.onnx",
                "joiner": "models/asr/joiner.onnx",
                "tokens": "models/asr/tokens.txt",
            },
            "tts": {
                "enabled": True,
                "sample_rate": 24000,
                "tokens": "models/tts/tokens.txt",
                "encoder": "models/tts/text_model.onnx",
                "decoder": "models/tts/flow_matching_model.onnx",
                "vocoder": "models/tts/vocos_24khz.onnx",
                "data_dir": "models/tts/espeak-ng-data",
            },
            "storage": {
                "voices_dir": "data/voices",
                "asr_jobs_dir": "data/jobs/asr",
                "tts_jobs_dir": "data/jobs/tts",
            },
            "security": {"api_keys": []},
        },
        root,
    )

    assert settings.tts.lexicon == root / "models/tts/tokens.txt"
