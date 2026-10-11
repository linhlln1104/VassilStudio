from __future__ import annotations

import io
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import runpy
import sys
import time
from types import SimpleNamespace

import numpy as np
import pytest

from vvoice.core.config import RuntimeSettings, TtsProfileSettings
from vvoice.core.errors import ModelConfigurationError, InferenceTransientError, InferenceDeadlineError
from vvoice.inference.tts import vieneu
from vvoice.inference.tts.vieneu import CODEC_FILES, CODEC_REPO, GRAPH_FILES, VieneuAdapter
from vvoice.inference.tts import vieneu_worker


def _adapter(tmp_path: Path, **options) -> VieneuAdapter:
    profile = TtsProfileSettings(
        model_id="vieneu-v3-turbo", engine="vieneu", label="VieNeu v3 Turbo",
        languages=("vi", "en"), sample_rate=48_000, root=tmp_path, options=options,
    )
    runtime = RuntimeSettings("local", "127.0.0.1", "INFO", "cpu", 2, False, False)
    return VieneuAdapter(profile, runtime)


def _file(path: Path, value: str = "asset") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def _prepare_assets(adapter: VieneuAdapter) -> None:
    _file(adapter._python)
    site = adapter._environment / "Lib/site-packages"
    _file(site / "vieneu-3.8.3.dist-info/METADATA")
    _file(site / "vieneu/v3turbo.py")
    _file(site / "sea_g2p/sea_g2p.bin")
    for name in GRAPH_FILES:
        _file(adapter._onnx_dir / name)
    _file(adapter._model_dir / "speaker_encoder.onnx")
    _file(adapter._model_dir / "denoiser.onnx")
    repo = adapter._cache_dir / "hub" / f"models--{CODEC_REPO.replace('/', '--')}"
    _file(repo / "refs/main", "a" * 40)
    for name in CODEC_FILES:
        _file(repo / "snapshots" / ("a" * 40) / name)


def test_catalog_checks_are_offline_and_require_all_assets(tmp_path, monkeypatch):
    adapter = _adapter(tmp_path)
    monkeypatch.setattr(vieneu.subprocess, "Popen", lambda *a, **k: pytest.fail("spawned worker"))
    assert not any(adapter.checks()[key] for key in ("dependency_vieneu", "model_graphs"))
    _prepare_assets(adapter)
    assert all(adapter.checks().values())
    (adapter._onnx_dir / "vieneu_backbone_shared.data").write_bytes(b"")
    assert not adapter.checks()["model_graphs"]
    assert "vieneu.v3turbo" not in sys.modules


def test_missing_assets_fail_before_starting_process(tmp_path, monkeypatch):
    adapter = _adapter(tmp_path)
    monkeypatch.setattr(vieneu.subprocess, "Popen", lambda *a, **k: pytest.fail("spawned worker"))
    with pytest.raises(ModelConfigurationError, match="setup_vieneu.py"):
        adapter.load()


@pytest.mark.parametrize("overrides", [{"speed": 1.5}, {"num_steps": 4}])
def test_unsupported_controls_are_not_silently_ignored(tmp_path, overrides):
    adapter = _adapter(tmp_path)
    with pytest.raises(ModelConfigurationError, match="does not support"):
        adapter.synthesize(
            text="Xin chào", reference_audio=np.zeros(240), reference_sample_rate=24_000,
            reference_text="", language="vi", **overrides,
        )


def test_worker_uses_public_sdk_api_and_keeps_stdout_for_protocol(tmp_path, monkeypatch):
    calls = []

    class FakeEngine:
        sample_rate = 48_000

        @staticmethod
        def _preclean_reference_audio(ref_audio, *, out_path=None):
            return str(out_path or ref_audio)

        def __init__(self, **kwargs):
            calls.append(kwargs)
            print("SDK startup logging")

        def infer(self, text, **kwargs):
            calls.append((text, kwargs))
            print("SDK inference logging")
            return np.ones(480, dtype=np.float32)

        def close(self):
            calls.append("closed")

    monkeypatch.setitem(sys.modules, "vieneu", SimpleNamespace(Vieneu=FakeEngine))
    output = tmp_path / "speech.npy"
    requests = [
        {"operation": "load", "model_dir": "model", "onnx_dir": "model/onnx_update",
         "threads": 2, "scratch_dir": str(tmp_path / "sdk-reference")},
        {"operation": "synthesize", "text": "Xin chào", "reference_path": "ref.wav",
         "output_path": str(output), "denoise": True},
    ]
    stdin = io.StringIO("".join(json.dumps(item) + "\n" for item in requests))
    stdout, stderr = io.StringIO(), io.StringIO()
    monkeypatch.setattr(sys, "stdin", stdin)
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", stderr)
    vieneu_worker.main()
    responses = [json.loads(line) for line in stdout.getvalue().splitlines()]
    assert responses == [{"ok": True}, {"ok": True, "sample_rate": 48_000}]
    assert "SDK startup logging" in stderr.getvalue()
    assert calls[0] == {
        "mode": "v3turbo", "backend": "onnx", "device": "cpu", "precision": "fp32",
        "backbone_repo": "model", "onnx_dir": "model/onnx_update", "threads": 2,
    }
    assert calls[1] == ("Xin chào", {"ref_audio": "ref.wav", "denoise": True})
    assert calls[-1] == "closed"
    assert np.load(output).size == 480


def _fake_worker(tmp_path: Path, monkeypatch, *, stall: bool = False) -> None:
    script = '''
import json, os, sys, time
import numpy as np
assert os.environ["HF_HUB_OFFLINE"] == "1"
assert os.environ["HF_HUB_CACHE"] == os.path.join(os.environ["HF_HOME"], "hub")
assert "PYTHONPATH" not in os.environ
assert sys.flags.isolated
for line in sys.stdin:
    request = json.loads(line)
    if request["operation"] == "load":
        print(json.dumps({"ok": True}), flush=True)
    else:
        if STALL:
            time.sleep(30)
        np.save(request["output_path"], np.ones(480, dtype=np.float32))
        print(json.dumps({"ok": True, "sample_rate": 48000}), flush=True)
'''.replace("STALL", repr(stall))
    (tmp_path / "vieneu_worker.py").write_text(script, encoding="utf-8")
    monkeypatch.setattr(vieneu, "__file__", str(tmp_path / "vieneu.py"))


def test_subprocess_is_offline_persistent_and_closed(tmp_path, monkeypatch):
    _fake_worker(tmp_path, monkeypatch)
    monkeypatch.setenv("HF_HUB_OFFLINE", "0")
    monkeypatch.setenv("HF_HOME", "parent-cache-must-not-change")
    monkeypatch.setenv("PYTHONPATH", "parent-imports")
    adapter = _adapter(tmp_path, python_executable=sys.executable)
    monkeypatch.setattr(adapter, "checks", lambda: {"ready": True})
    try:
        adapter.load()
        worker = adapter._process
        for _ in range(2):
            speech = adapter.synthesize(
                text="Xin chào", reference_audio=np.zeros(240), reference_sample_rate=24_000,
                reference_text="", language="vi",
            )
            assert speech.sample_rate == 48_000
            assert speech.duration_seconds == 0.01
            assert adapter._process is worker
        assert os.environ["HF_HUB_OFFLINE"] == "0"
        assert os.environ["HF_HOME"] == "parent-cache-must-not-change"
        assert list(Path(adapter._temporary.name).glob("*.wav")) == []
    finally:
        adapter.close()
    assert worker.poll() is not None
    assert adapter._temporary is None


def test_timeout_stops_worker_and_discards_temporary_audio(tmp_path, monkeypatch):
    _fake_worker(tmp_path, monkeypatch, stall=True)
    adapter = _adapter(tmp_path, python_executable=sys.executable, inference_timeout_seconds=0.1)
    monkeypatch.setattr(adapter, "checks", lambda: {"ready": True})
    adapter.load()
    worker = adapter._process
    with pytest.raises(InferenceDeadlineError, match="timed out"):
        adapter.synthesize(
            text="Xin chào", reference_audio=np.zeros(240), reference_sample_rate=24_000,
            reference_text="", language="vi",
        )
    assert worker.poll() is not None
    assert adapter._temporary is None


@pytest.mark.parametrize("failure", ["timeout", "crash"])
def test_sdk_reference_scratch_is_removed_after_worker_failure(tmp_path, monkeypatch, failure):
    # Run the real worker with a small SDK stand-in that reproduces the SDK's
    # out_path hook and leaves its WAV open to cleanup by the parent on failure.
    # The marker proves preprocessing happened before the forced timeout/crash.
    actual_worker = Path(vieneu_worker.__file__).resolve()
    marker = tmp_path / "scratch-path.txt"
    wrapper = '''
import os, runpy, sys, time
from pathlib import Path
from types import SimpleNamespace
import soundfile as sf
class FakeEngine:
    sample_rate = 48000
    def __init__(self, **kwargs):
        pass
    @staticmethod
    def _preclean_reference_audio(ref_audio, *, out_path=None):
        if out_path is None:
            raise AssertionError("SDK home scratch must never be used")
        samples, sr = sf.read(ref_audio)
        sf.write(out_path, samples, sr)
        Path(MARKER).write_text(str(out_path), encoding="utf-8")
        Path(MARKER).with_suffix(".pid").write_text(str(os.getpid()), encoding="ascii")
        return str(out_path)
    def infer(self, text, ref_audio, **kwargs):
        self._preclean_reference_audio(ref_audio)
        if FAILURE == "crash":
            os._exit(7)
        time.sleep(30)
    def close(self):
        pass
sys.modules["vieneu"] = SimpleNamespace(Vieneu=FakeEngine)
runpy.run_path(WORKER, run_name="__main__")
'''.replace("MARKER", repr(str(marker))).replace("FAILURE", repr(failure)).replace(
        "WORKER", repr(str(actual_worker)),
    )
    (tmp_path / "vieneu_worker.py").write_text(wrapper, encoding="utf-8")
    monkeypatch.setattr(vieneu, "__file__", str(tmp_path / "vieneu.py"))
    home_before = {key: os.environ.get(key) for key in ("HOME", "USERPROFILE")}
    adapter = _adapter(tmp_path, python_executable=sys.executable, inference_timeout_seconds=0.5)
    monkeypatch.setattr(adapter, "checks", lambda: {"ready": True})
    adapter.load()
    worker = adapter._process
    scratch_root = Path(adapter._temporary.name)
    try:
        with pytest.raises((InferenceDeadlineError, InferenceTransientError), match="timed out|exited"):
            adapter.synthesize(
                text="Xin chào", reference_audio=np.ones(480), reference_sample_rate=24_000,
                reference_text="", language="vi",
            )
        generated_scratch = Path(marker.read_text(encoding="utf-8"))
        assert generated_scratch.is_relative_to(scratch_root)
        assert not generated_scratch.exists()
        assert not scratch_root.exists()
        assert worker.poll() is not None
        assert not adapter.is_loaded
        assert adapter._temporary is None
        actual_worker_pid = int(marker.with_suffix(".pid").read_text(encoding="ascii"))
        # Windows TerminateProcess is asynchronous; wait for the interpreter
        # object to signal, not just for its venv redirector to finish.
        deadline = time.monotonic() + 5
        while _process_running(actual_worker_pid) and time.monotonic() < deadline:
            time.sleep(0.02)
        assert not _process_running(actual_worker_pid)
        assert home_before == {key: os.environ.get(key) for key in ("HOME", "USERPROFILE")}
    finally:
        adapter.close()


def _process_running(pid: int) -> bool:
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE, read-only
        if not handle:
            return False
        try:
            return kernel.WaitForSingleObject(handle, 0) == 258  # WAIT_TIMEOUT
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def test_setup_requires_explicit_flag_for_model_downloads(tmp_path, monkeypatch):
    script = Path(__file__).resolve().parents[1] / "scripts/setup_vieneu.py"
    namespace = runpy.run_path(str(script))
    executable = tmp_path / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    _file(executable)
    calls = []
    monkeypatch.setattr(vieneu.subprocess, "run", lambda args, **kwargs: calls.append(args))
    monkeypatch.setattr(sys, "argv", [str(script), "--environment-dir", str(tmp_path)])
    namespace["main"]()
    assert len(calls) == 1
    assert calls[0][1:4] == ["-m", "pip", "install"]
    assert calls[0][-1] == "vieneu==3.8.3"


def test_explicit_setup_download_passes_tested_revisions(tmp_path, monkeypatch):
    script = Path(__file__).resolve().parents[1] / "scripts/setup_vieneu.py"
    namespace = runpy.run_path(str(script))
    executable = tmp_path / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    _file(executable)
    calls = []
    monkeypatch.setattr(vieneu.subprocess, "run", lambda args, **kwargs: calls.append((args, kwargs)))
    monkeypatch.setattr(sys, "argv", [
        str(script), "--environment-dir", str(tmp_path), "--model-root", str(tmp_path / "model"),
        "--skip-install", "--download-assets",
    ])
    namespace["main"]()
    assert len(calls) == 1
    command, kwargs = calls[0]
    assert command[-2:] == [namespace["MODEL_REVISION"], namespace["CODEC_REVISION"]]
    assert command[1:6] == ["-I", "-X", "utf8", "-c", namespace["PREFETCH"]]
    assert kwargs["env"]["HF_HOME"] == str(tmp_path / "model" / "hf-cache")


@pytest.mark.parametrize("incomplete", [False, True])
def test_pinned_prefetch_publishes_managed_alias_only_after_validation(
    tmp_path, monkeypatch, incomplete,
):
    script = Path(__file__).resolve().parents[1] / "scripts/setup_vieneu.py"
    namespace = runpy.run_path(str(script))
    root = tmp_path / "models"
    cache = root / "hf-cache" / "hub"
    codec_cache = cache / f"models--{CODEC_REPO.replace('/', '--')}"
    managed_ref = codec_cache / "refs" / "main"
    global_ref = tmp_path / "global-hf" / "refs" / "main"
    _file(managed_ref, "b" * 40)
    _file(global_ref, "c" * 40)
    monkeypatch.setenv("HF_HOME", str(tmp_path / "global-hf"))
    calls = []

    def snapshot_download(repo_id, *, revision, allow_patterns, **kwargs):
        calls.append((repo_id, revision, kwargs))
        destination = (
            Path(kwargs["local_dir"]) if "local_dir" in kwargs
            else Path(kwargs["cache_dir"]) / f"models--{repo_id.replace('/', '--')}"
            / "snapshots" / revision
        )
        for name in allow_patterns:
            if incomplete and name == "moss_audio_tokenizer_encode.data":
                continue
            _file(destination / name, repo_id + name + revision)
        return str(destination)

    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(
        snapshot_download=snapshot_download,
    ))
    monkeypatch.setitem(sys.modules, "sea_g2p", SimpleNamespace(
        SEAPipeline=lambda **kwargs: SimpleNamespace(run=lambda text: "phonemes"),
    ))
    monkeypatch.setattr(importlib.metadata, "version", lambda name: "3.8.3")
    monkeypatch.setattr(sys, "argv", [
        "prefetch", str(root), namespace["MODEL_REVISION"], namespace["CODEC_REVISION"],
    ])
    if incomplete:
        with pytest.raises(RuntimeError, match="Incomplete VieNeu download"):
            exec(namespace["PREFETCH"], {"__name__": "__main__"})
        assert managed_ref.read_text() == "b" * 40
        assert not (root / "manifest.json").exists()
    else:
        exec(namespace["PREFETCH"], {"__name__": "__main__"})
        assert managed_ref.read_text() == namespace["CODEC_REVISION"]
        manifest = json.loads((root / "manifest.json").read_text())
        assert manifest["sdk"]["version"] == "3.8.3"
        assert [source["revision"] for source in manifest["sources"]] == [
            namespace["MODEL_REVISION"], namespace["CODEC_REVISION"],
        ]
        assert manifest["payload_bytes"] == sum(item["bytes"] for item in manifest["files"])
        for item in manifest["files"]:
            content = (root / item["path"]).read_bytes()
            assert item["sha256"] == hashlib.sha256(content).hexdigest()
    assert calls[0][1] == namespace["MODEL_REVISION"]
    assert calls[1][1] == namespace["CODEC_REVISION"]
    assert calls[1][2]["cache_dir"] == cache.resolve()
    assert global_ref.read_text() == "c" * 40
