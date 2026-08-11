from scripts.doctor import EXPECTED_RUNTIME_VERSIONS, _version_matches


def test_doctor_accepts_cpu_local_version_suffix() -> None:
    assert _version_matches("2.11.0+cpu", "2.11.0")
    assert not _version_matches("2.12.1+cpu", "2.11.0")


def test_doctor_guards_the_pinned_model_runtime() -> None:
    assert EXPECTED_RUNTIME_VERSIONS == {
        "espeakng_loader": "0.2.4",
        "onnxruntime": "1.27.0",
        "phonemizer": "3.3.2",
        "sherpa_onnx": "1.13.3",
        "torch": "2.11.0",
        "torchaudio": "2.11.0",
    }
