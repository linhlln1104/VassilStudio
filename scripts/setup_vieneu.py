"""Install VieNeu v3 Turbo's isolated SDK; optionally download inference assets.

Run with Python 3.12+ from the repository. This script intentionally performs
network operations; model weights require the explicit --download-assets flag.
The API server and model catalog never invoke this script.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys


MODEL_REVISION = "61b85e3d937fbbacb387714180e8182823512523"
CODEC_REVISION = "ceff0d0749bfb3fa2d61149794ec6feef0d1e1ae"


PREFETCH = r'''
import hashlib
import json
import sys
from pathlib import Path
from huggingface_hub import snapshot_download
from importlib.metadata import version

root = Path(sys.argv[1]).resolve()
model_revision, codec_revision = sys.argv[2:4]
sdk_version = version("vieneu")
if sdk_version != "3.8.3":
    raise RuntimeError("Expected vieneu==3.8.3; rerun setup without --skip-install")
model_repo = "pnnbao-ump/VieNeu-TTS-v3-Turbo"
codec_repo = "OpenMOSS-Team/MOSS-Audio-Tokenizer-Nano-ONNX"
model_files = [
    "onnx_update/vieneu_prefill.onnx", "onnx_update/vieneu_decode_step.onnx",
    "onnx_update/vieneu_acoustic_cached.onnx", "onnx_update/vieneu_backbone_shared.data",
    "onnx_update/vieneu_v3_heads.npz", "onnx_update/config.json",
    "onnx_update/tokenizer.json", "speaker_encoder.onnx", "denoiser.onnx",
]
codec_files = [
    "moss_audio_tokenizer_decode_full.onnx", "moss_audio_tokenizer_decode_shared.data",
    "moss_audio_tokenizer_decode_step.onnx", "codec_browser_onnx_meta.json",
    "moss_audio_tokenizer_encode.onnx", "moss_audio_tokenizer_encode.data",
]
snapshot_download(
    model_repo, revision=model_revision, local_dir=root / "model",
    allow_patterns=model_files + ["voices_v3_turbo.json", "LICENSE", "README.md"],
)
cache = root / "hf-cache" / "hub"
codec_snapshot = Path(snapshot_download(
    codec_repo, revision=codec_revision, cache_dir=cache,
    allow_patterns=codec_files + ["LICENSE", "README.md"],
)).resolve()
codec_cache = cache / ("models--" + codec_repo.replace("/", "--"))
expected_snapshot = (codec_cache / "snapshots" / codec_revision).resolve()
if codec_snapshot != expected_snapshot:
    raise RuntimeError("Codec download returned a snapshot outside the managed pinned cache")
required = [root / "model" / name for name in model_files]
required += [codec_snapshot / name for name in codec_files]
missing = [str(path) for path in required if not path.is_file() or path.stat().st_size == 0]
if missing:
    raise RuntimeError("Incomplete VieNeu download: " + ", ".join(missing))
from sea_g2p import SEAPipeline
assert SEAPipeline(lang="vi").run("Xin chào, hello world."), "Text frontend is unavailable"

# SDK 3.8.3 requests the codec's default `main` even when offline. A download
# pinned by commit may not create this ref. Publish the alias only after all
# required artifacts were verified, in this profile's cache (never global HF).
refs = codec_cache / "refs"
refs.mkdir(parents=True, exist_ok=True)
pending_ref = refs / "main.vassil-download"
pending_ref.write_text(codec_revision, encoding="utf-8")
pending_ref.replace(refs / "main")

artifacts = []
for base, names in (
    (root / "model", model_files + ["voices_v3_turbo.json", "LICENSE", "README.md"]),
    (codec_snapshot, codec_files + ["LICENSE", "README.md"]),
):
    for name in names:
        path = base / name
        if path.is_file():
            with path.open("rb") as stream:
                checksum = hashlib.file_digest(stream, "sha256").hexdigest()
            artifacts.append({"path": path.relative_to(root).as_posix(),
                              "bytes": path.stat().st_size, "sha256": checksum})
manifest = {
    "format_version": 1, "sdk": {"package": "vieneu", "version": sdk_version},
    "backend": "onnx", "device": "cpu", "precision": "fp32",
    "sources": [{"repo_id": model_repo, "revision": model_revision},
                {"repo_id": codec_repo, "revision": codec_revision}],
    "codec_offline_alias": "main", "files": artifacts,
    "payload_bytes": sum(item["bytes"] for item in artifacts),
}
pending_manifest = root / "manifest.json.download"
pending_manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
pending_manifest.replace(root / "manifest.json")
print("VieNeu", sdk_version, "assets are ready for offline CPU inference.")
print("Provenance and SHA256 checksums:", root / "manifest.json")
'''


def _revision(value: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{40}", value):
        raise argparse.ArgumentTypeError("A revision must be a complete lowercase commit SHA")
    return value


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment-dir", type=Path, default=root / ".venv-vieneu")
    parser.add_argument(
        "--model-root", type=Path, default=root / "models/runtime/tts/vieneu-v3-turbo",
    )
    parser.add_argument("--skip-install", action="store_true", help="Reuse the prepared environment")
    parser.add_argument(
        "--download-assets", action="store_true", help="Explicitly download model/codec weights",
    )
    parser.add_argument("--model-revision", type=_revision, default=MODEL_REVISION)
    parser.add_argument("--codec-revision", type=_revision, default=CODEC_REVISION)
    args = parser.parse_args()
    environment_dir = args.environment_dir.resolve()
    python = environment_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not args.skip_install:
        if not python.is_file():
            subprocess.run([sys.executable, "-m", "venv", str(environment_dir)], check=True)
        subprocess.run(
            [str(python), "-m", "pip", "install", "vieneu==3.8.3"], check=True,
        )
    if not python.is_file():
        parser.error(f"No Python environment at {environment_dir}; omit --skip-install")
    if not args.download_assets:
        print("SDK environment ready. No model weights downloaded.")
        print("Next: python scripts/setup_vieneu.py --skip-install --download-assets")
        return
    environment = os.environ.copy()
    for variable in ("HF_HUB_OFFLINE", "HF_DATASETS_OFFLINE", "TRANSFORMERS_OFFLINE"):
        environment.pop(variable, None)
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    environment["PYTHONUTF8"] = "1"
    environment["HF_HOME"] = str(args.model_root.resolve() / "hf-cache")
    subprocess.run(
        [str(python), "-I", "-X", "utf8", "-c", PREFETCH, str(args.model_root.resolve()),
         args.model_revision, args.codec_revision],
        env=environment, check=True,
    )


if __name__ == "__main__":
    main()
