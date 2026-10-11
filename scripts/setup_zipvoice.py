"""Download pinned ZipVoice research assets and record their provenance.

English has upstream ONNX graphs. The originating Vietnamese author provides a
PyTorch checkpoint, which must be exported separately with k2-fsa/ZipVoice.
These pretrained models have non-commercial terms; see the saved model cards.
No model download occurs without --download-assets.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import urllib.request


EN_REPO = "k2-fsa/ZipVoice"
EN_REVISION = "889dd609a42f0de9cf9aac335eae42677becb1b9"
VI_REPO = "hynt/ZipVoice-Vietnamese-2500h"
VI_REVISION = "d9792210a42a5d001843930f5cfabc1fe4e15407"
VOCODER_URL = (
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/"
    "vocoder-models/vocos_24khz.onnx"
)
VOCODER_SHA256 = "bcb3b970e384161c4d634f0bb9e999ff1c471b34c9bc0b1049a5014065ed3cc0"


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def download(url: str, target: Path, expected: str | None = None) -> dict:
    target.parent.mkdir(parents=True, exist_ok=True)
    if not (target.is_file() and expected and sha256(target) == expected):
        temporary = target.with_suffix(target.suffix + ".download")
        print(f"Downloading {target.name}", flush=True)
        try:
            with urllib.request.urlopen(url, timeout=120) as source, temporary.open("wb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)
            checksum = sha256(temporary)
            if expected and checksum != expected:
                raise ValueError(f"SHA256 mismatch for {target}")
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
    return {"file": target.name, "url": url, "sha256": sha256(target), "bytes": target.stat().st_size}


def prepare(root: Path, language: str) -> None:
    runtime = root / "models/runtime/tts" / language / "zipvoice"
    repo, revision = (EN_REPO, EN_REVISION) if language == "en" else (VI_REPO, VI_REVISION)
    base_url = f"https://huggingface.co/{repo}/resolve/{revision}/"
    if language == "en":
        directory = runtime
        files = [
            ("zipvoice/text_encoder.onnx", "text_model.onnx", "85e9b4c4a23e1464070fc72701d21a84b5df55aa182db3e5a24a33bed6cb831f"),
            ("zipvoice/fm_decoder.onnx", "flow_matching_model.onnx", "fb57eff934f18082f9e8af8bc217b2ec296d2ea763ad3f2907a7486ef51f7712"),
            ("zipvoice/tokens.txt", "tokens.txt", None),
            ("zipvoice/model.json", "model.json", None),
            ("README.md", "UPSTREAM_MODEL_CARD.md", None),
        ]
    else:
        directory = root / "models/source/tts/vi/zipvoice"
        files = [
            ("iter-525000-avg-2.pt", "iter-525000-avg-2.pt", "d0866f1a66c4fb3a2b5cb5f0fb5cbf6a9491a3fc305cf6467f6a655b5fdeea67"),
            ("tokens.txt", "tokens.txt", None),
            ("config.json", "model.json", None),
            ("README.md", "UPSTREAM_MODEL_CARD.md", None),
        ]
    records = [download(base_url + remote, directory / local, expected) for remote, local, expected in files]
    if language == "vi":
        runtime.mkdir(parents=True, exist_ok=True)
        shutil.copy2(directory / "tokens.txt", runtime / "tokens.txt")
    records.append(download(VOCODER_URL, runtime / "vocos_24khz.onnx", VOCODER_SHA256))
    manifest = {
        "language": language, "model_repository": repo, "model_revision": revision,
        "model_license": "CC-BY-NC (Emilia training data)" if language == "en" else "CC-BY-NC-SA-4.0",
        "reviewed_on": "2026-10-11", "purpose": "Local research and integration testing; no redistribution",
        "upstream_export_repository": "https://github.com/k2-fsa/ZipVoice",
        "upstream_export_revision": "2f7326fbfe999a3ad179e3f1af82a424d4a62819",
        "source_directory": str(directory.relative_to(root)),
        "runtime_directory": str(runtime.relative_to(root)), "files": records,
        "vocoder_source": "https://github.com/k2-fsa/sherpa-onnx/releases/tag/vocoder-models",
        "vocoder_original_model": "https://huggingface.co/charactr/vocos-mel-24khz",
        "vocoder_license": "MIT",
    }
    (directory / "provenance.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Prepared {language}: {directory}", flush=True)
    if language == "vi":
        print("Vietnamese checkpoint requires ONNX export before runtime is ready.", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--language", choices=("en", "vi", "both"), default="both")
    parser.add_argument("--download-assets", action="store_true")
    args = parser.parse_args()
    if not args.download_assets:
        print("No weights downloaded. Add --download-assets for local research assets.")
        return
    root = Path(__file__).resolve().parents[1]
    for language in ("en", "vi") if args.language == "both" else (args.language,):
        prepare(root, language)


if __name__ == "__main__":
    main()
