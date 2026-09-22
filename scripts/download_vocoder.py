"""Download the pinned public vocoder without ever promoting incomplete bytes."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import tempfile
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
VOCODER_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/"
    "vocoder-models/vocos_24khz.onnx"
)
# GitHub release asset 284752173; digest/size verified against the official release API
# https://api.github.com/repos/k2-fsa/sherpa-onnx/releases/tags/vocoder-models
# and the accepted RC model fingerprint, on 2026-09-22.
VOCODER_SHA256 = "bcb3b970e384161c4d634f0bb9e999ff1c471b34c9bc0b1049a5014065ed3cc0"
VOCODER_SIZE = 54_157_409
DEFAULT_TARGET = ROOT / "models/runtime/tts/vi/zipvoice/vocos_24khz.onnx"


def file_matches(path: Path, expected_size: int, expected_sha256: str) -> bool:
    if not path.is_file() or path.stat().st_size != expected_size:
        return False
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest() == expected_sha256


def download_verified(
    target: Path,
    *,
    url: str = VOCODER_URL,
    expected_sha256: str = VOCODER_SHA256,
    expected_size: int = VOCODER_SIZE,
) -> str:
    if file_matches(target, expected_size, expected_sha256):
        return "Already verified"
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=target.parent, prefix=f".{target.name}.", suffix=".part", delete=False
        ) as output:
            temporary_path = Path(output.name)
            request = Request(url, headers={"User-Agent": "VassilStudio-vocoder-installer"})
            with urlopen(request, timeout=60) as response:
                received = 0
                while chunk := response.read(1024 * 1024):
                    received += len(chunk)
                    if received > expected_size:
                        raise ValueError("Vocoder exceeds its pinned release size.")
                    output.write(chunk)
        if not file_matches(temporary_path, expected_size, expected_sha256):
            raise ValueError("Vocoder size or SHA256 does not match the pinned release asset.")
        temporary_path.replace(target)
        return "Downloaded and verified"
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    args = parser.parse_args()
    print(f"{download_verified(args.target)}: {args.target}")


if __name__ == "__main__":
    main()
