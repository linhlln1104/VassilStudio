import json
from pathlib import Path

from vvoice.core.config import load_settings, parse_settings


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


def test_parse_settings_supports_job_worker_limits(tmp_path) -> None:
    raw = _minimal_settings_raw()
    raw["jobs"] = {"asr_max_workers": 2, "tts_max_workers": 3}

    settings = parse_settings(raw, tmp_path)

    assert settings.jobs.asr_max_workers == 2
    assert settings.jobs.tts_max_workers == 3


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
