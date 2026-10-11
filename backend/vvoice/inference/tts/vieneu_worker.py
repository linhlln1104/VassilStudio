"""Private JSON-lines worker; run only through VieneuAdapter's isolated Python.

Stdout is reserved for protocol responses. SDK logs go to the parent's log file.
Hugging Face offline/cache variables must be configured before this process starts.
This file deliberately does not import the API package or its dependencies.
"""

from __future__ import annotations

from contextlib import redirect_stdout
from functools import partial
import json
from pathlib import Path
import sys
import traceback


def _use_managed_reference_scratch(engine, directory: str) -> None:
    """Keep the pinned SDK's cleaned reference inside parent-owned scratch.

    v3.8.3 normally writes this WAV to Path.home()/.cache/vieneu/tmp. Its own
    finally block cannot run after a worker hard-kill, so the parent must own
    the file's lifetime. Bind the SDK's existing out_path hook on this instance
    only; do not modify the SDK class, pathlib, or the user's home settings.
    The worker processes one request at a time, so this path is not shared by
    concurrent inference calls.
    """
    scratch = Path(directory)
    scratch.mkdir(parents=True, exist_ok=True, mode=0o700)
    engine._preclean_reference_audio = partial(
        engine._preclean_reference_audio, out_path=scratch / "reference-cleaned.wav",
    )


def main() -> None:
    protocol = sys.stdout
    engine = None
    try:
        for line in sys.stdin:
            try:
                request = json.loads(line)
                with redirect_stdout(sys.stderr):
                    if request["operation"] == "load":
                        from vieneu import Vieneu

                        engine = Vieneu(
                            mode="v3turbo", backend="onnx", device="cpu", precision="fp32",
                            backbone_repo=request["model_dir"], onnx_dir=request["onnx_dir"],
                            threads=request["threads"],
                        )
                        _use_managed_reference_scratch(engine, request["scratch_dir"])
                        response = {"ok": True}
                    elif request["operation"] == "synthesize" and engine is not None:
                        import numpy as np

                        audio = engine.infer(
                            request["text"], ref_audio=request["reference_path"],
                            denoise=request["denoise"],
                        )
                        np.save(request["output_path"], np.asarray(audio, dtype=np.float32))
                        response = {"ok": True, "sample_rate": int(engine.sample_rate)}
                    else:
                        raise ValueError("Invalid VieNeu worker operation")
            except Exception as exc:
                traceback.print_exc(file=sys.stderr)
                response = {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:1000]}
            protocol.write(json.dumps(response, ensure_ascii=False) + "\n")
            protocol.flush()
    finally:
        if engine is not None:
            with redirect_stdout(sys.stderr):
                engine.close()


if __name__ == "__main__":
    main()
