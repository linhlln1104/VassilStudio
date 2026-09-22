from __future__ import annotations

import hashlib
import io
from pathlib import Path

import pytest

from scripts import download_vocoder


MODEL = b"pinned public test model bytes"
DIGEST = hashlib.sha256(MODEL).hexdigest()


def download(target: Path) -> str:
    return download_vocoder.download_verified(
        target, expected_size=len(MODEL), expected_sha256=DIGEST,
    )


def test_verified_existing_model_never_downloads(monkeypatch, tmp_path: Path) -> None:
    target = tmp_path / "model.onnx"
    target.write_bytes(MODEL)

    def unexpected_download(*args, **kwargs):
        pytest.fail("A verified existing model must not be downloaded again")

    monkeypatch.setattr(download_vocoder, "urlopen", unexpected_download)
    assert download(target) == "Already verified"
    assert target.read_bytes() == MODEL


def test_download_promotes_only_verified_bytes(monkeypatch, tmp_path: Path) -> None:
    target = tmp_path / "model.onnx"
    target.write_bytes(b"interrupted previous download")
    monkeypatch.setattr(download_vocoder, "urlopen", lambda *a, **k: io.BytesIO(MODEL))
    assert download(target) == "Downloaded and verified"
    assert target.read_bytes() == MODEL
    assert list(tmp_path.glob("*.part")) == []


@pytest.mark.parametrize("received", [MODEL[:-1], b"x" * len(MODEL), MODEL + b"extra"])
def test_bad_download_preserves_existing_file_and_cleans_partial(
    monkeypatch, tmp_path: Path, received: bytes,
) -> None:
    target = tmp_path / "model.onnx"
    original = b"existing file remains available until successful replacement"
    target.write_bytes(original)
    monkeypatch.setattr(download_vocoder, "urlopen", lambda *a, **k: io.BytesIO(received))
    with pytest.raises(ValueError, match="pinned"):
        download(target)
    assert target.read_bytes() == original
    assert list(tmp_path.glob("*.part")) == []


def test_interrupted_stream_leaves_no_model_or_partial(monkeypatch, tmp_path: Path) -> None:
    class InterruptedStream(io.BytesIO):
        def read(self, size=-1):
            if self.tell():
                raise ConnectionError("connection dropped")
            return super().read(3)

    target = tmp_path / "model.onnx"
    monkeypatch.setattr(download_vocoder, "urlopen", lambda *a, **k: InterruptedStream(MODEL))
    with pytest.raises(ConnectionError):
        download(target)
    assert not target.exists()
    assert list(tmp_path.glob("*.part")) == []
