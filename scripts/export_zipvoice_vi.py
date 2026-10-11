"""Export the pinned originating Vietnamese checkpoint with upstream ONNX code.

Prerequisites: .[zipvoice], onnx, tensorboard, and the official ZipVoice checkout
at the revision below in foundation/ZipVoice. Run setup_zipvoice.py first.
Only inference/export definitions are loaded from the pinned upstream exporter;
its training/tokenizer CLI imports are unnecessary for checkpoint conversion.
PyTorch's legacy exporter is selected explicitly because these official wrappers
are TorchScript-based. No model or code is downloaded by this script.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import logging
from pathlib import Path
import subprocess
import sys
from typing import Dict


UPSTREAM_REVISION = "2f7326fbfe999a3ad179e3f1af82a424d4a62819"
CHECKPOINT_SHA256 = "d0866f1a66c4fb3a2b5cb5f0fb5cbf6a9491a3fc305cf6467f6a655b5fdeea67"


def checksum(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def export(root: Path, component: str) -> None:
    upstream = root / "foundation/ZipVoice"
    revision = subprocess.check_output(["git", "-C", str(upstream), "rev-parse", "HEAD"], text=True).strip()
    if revision != UPSTREAM_REVISION:
        raise ValueError(f"Expected upstream ZipVoice {UPSTREAM_REVISION}, got {revision}")
    dirty = subprocess.check_output(["git", "-C", str(upstream), "status", "--porcelain"], text=True)
    if dirty.strip():
        raise ValueError("The upstream checkout must be unmodified for reproducible export")
    source = root / "models/source/tts/vi/zipvoice"
    checkpoint = source / "iter-525000-avg-2.pt"
    if checksum(checkpoint) != CHECKPOINT_SHA256:
        raise ValueError("Vietnamese checkpoint SHA256 does not match its originating author")
    sys.path.insert(0, str(upstream))
    import onnx
    import torch
    from zipvoice.models.zipvoice import ZipVoice
    from zipvoice.utils.scaling_converter import convert_scaled_to_non_scaled

    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    config = json.loads((source / "model.json").read_text(encoding="utf-8"))
    token_ids = {}
    for line in (source / "tokens.txt").read_text(encoding="utf-8").splitlines():
        symbol, index = line.rsplit("\t", 1)
        token_ids[symbol] = int(index)
    model = ZipVoice(**config["model"], vocab_size=len(token_ids), pad_id=token_ids["_"])
    # No arbitrary checkpoint objects are deserialized. mmap/assign avoid a
    # second in-memory copy of these ~491 MB weights during CPU export.
    state = torch.load(checkpoint, map_location="cpu", weights_only=True, mmap=True)["model"]
    state = {key.removeprefix("module."): value for key, value in state.items()}
    model.load_state_dict(state, strict=True, assign=True)
    del state
    model.eval()
    convert_scaled_to_non_scaled(model, inplace=True, is_onnx=True)

    exporter = upstream / "zipvoice/bin/onnx_export.py"
    tree = ast.parse(exporter.read_text(encoding="utf-8"), filename=str(exporter))
    names = {"add_meta_data", "OnnxTextModel", "OnnxFlowMatchingModel", "export_text_encoder", "export_fm_decoder"}
    definitions = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names]
    if {node.name for node in definitions} != names:
        raise ValueError("Pinned upstream exporter definitions do not match")
    selected = ast.Module(body=definitions, type_ignores=[])
    for node in ast.walk(selected):
        if isinstance(node, ast.Call) and ast.unparse(node.func) == "torch.onnx.export":
            node.keywords.extend([
                ast.keyword(arg="dynamo", value=ast.Constant(False)),
                ast.keyword(arg="external_data", value=ast.Constant(False)),
            ])
    ast.fix_missing_locations(selected)
    namespace = {"torch": torch, "onnx": onnx, "nn": torch.nn, "Tensor": torch.Tensor,
                 "Dict": Dict, "logging": logging}
    exec(compile(selected, str(exporter), "exec"), namespace)
    runtime = root / "models/runtime/tts/vi/zipvoice"
    runtime.mkdir(parents=True, exist_ok=True)
    filename = "text_model.onnx" if component == "text" else "flow_matching_model.onnx"
    path = runtime / filename
    with torch.inference_mode():
        if component == "text":
            namespace["export_text_encoder"](namespace["OnnxTextModel"](model), str(path))
        else:
            namespace["export_fm_decoder"](namespace["OnnxFlowMatchingModel"](model), str(path))
    record = {"file": filename, "sha256": checksum(path), "bytes": path.stat().st_size,
              "upstream_revision": revision, "checkpoint_sha256": CHECKPOINT_SHA256,
              "torch": torch.__version__, "onnx": onnx.__version__, "opset": 13,
              "exporter": "official wrappers with dynamo=False, external_data=False",
              "model_repository": "https://huggingface.co/hynt/ZipVoice-Vietnamese-2500h",
              "model_license": "CC-BY-NC-SA-4.0"}
    path.with_suffix(".provenance.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(record), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--component", choices=("text", "decoder", "both"), default="both")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.component == "both":
        # Separate processes bound retained tracing/ONNX memory per component.
        for component in ("text", "decoder"):
            subprocess.run([sys.executable, str(Path(__file__).resolve()), "--component", component], check=True)
    else:
        export(root, args.component)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
