"""Offline VieNeu v3 Turbo adapter, isolated from the application's dependencies.

The SDK's public constructor does not forward a local codec directory. A worker
with its own Hugging Face cache and offline environment therefore loads the
official SDK without changing process-wide settings in the API server.
"""

from __future__ import annotations

import json
import logging
import math
import os
from pathlib import Path
import queue
import subprocess
import tempfile
import threading
import time
from typing import TYPE_CHECKING

import numpy as np

from vvoice.core.errors import ModelConfigurationError, InferenceTransientError, InferenceDeadlineError
from vvoice.inference.tts.base import GeneratedSpeech, TtsCapabilities

if TYPE_CHECKING:
    from vvoice.core.config import RuntimeSettings, TtsProfileSettings


SDK_VERSION = "3.8.3"
MODEL_REPO = "pnnbao-ump/VieNeu-TTS-v3-Turbo"
CODEC_REPO = "OpenMOSS-Team/MOSS-Audio-Tokenizer-Nano-ONNX"
GRAPH_FILES = (
    "vieneu_prefill.onnx", "vieneu_decode_step.onnx", "vieneu_acoustic_cached.onnx",
    "vieneu_backbone_shared.data", "vieneu_v3_heads.npz", "config.json", "tokenizer.json",
)
CODEC_FILES = (
    "moss_audio_tokenizer_decode_full.onnx", "moss_audio_tokenizer_decode_shared.data",
    "moss_audio_tokenizer_decode_step.onnx", "codec_browser_onnx_meta.json",
    "moss_audio_tokenizer_encode.onnx", "moss_audio_tokenizer_encode.data",
)
_DEFAULT_MODELS = "models/runtime/tts/vieneu-v3-turbo"
logger = logging.getLogger(__name__)


def _nonempty_file(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


class VieneuAdapter:
    capabilities = TtsCapabilities(reference_audio=True, num_steps=False, speed=False)

    def __init__(self, profile: TtsProfileSettings, runtime: RuntimeSettings) -> None:
        self._profile = profile
        self._runtime = runtime
        self._options = profile.options
        self._environment = self._path("environment_dir", ".venv-vieneu")
        executable = "Scripts/python.exe" if os.name == "nt" else "bin/python"
        # Resolving a POSIX venv's python symlink would select the system Python
        # and lose the isolated environment's installed dependencies.
        self._python = self._path(
            "python_executable", str(self._environment / executable), resolve_symlinks=False,
        )
        self._model_dir = self._path("model_dir", f"{_DEFAULT_MODELS}/model")
        self._onnx_dir = self._path("onnx_dir", str(self._model_dir / "onnx_update"))
        self._cache_dir = self._path("cache_dir", f"{_DEFAULT_MODELS}/hf-cache")
        self._lock = threading.RLock()
        self._process: subprocess.Popen | None = None
        self._responses: queue.Queue = queue.Queue()
        self._temporary: tempfile.TemporaryDirectory | None = None
        self._log = None

    def _path(self, name: str, default: str, *, resolve_symlinks: bool = True) -> Path:
        path = Path(str(self._options.get(name, default))).expanduser()
        path = path if path.is_absolute() else self._profile.root / path
        return path.resolve() if resolve_symlinks else Path(os.path.abspath(path))

    @property
    def is_loaded(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def _timeout(self, name: str, default: float) -> float:
        try:
            value = float(self._options.get(name, default))
            if math.isfinite(value) and 0 < value <= 3600:
                return value
        except (TypeError, ValueError):
            pass
        raise ModelConfigurationError(f"VieNeu {name} must be greater than 0 and at most 3600.")

    def _site_packages(self) -> tuple[Path, ...]:
        # No subprocess, SDK import, or model loading in catalog/health checks.
        environment = self._python.parent.parent
        return (
            environment / "Lib" / "site-packages",
            *environment.glob("lib/python*/site-packages"),
            *environment.glob("lib64/python*/site-packages"),
        )

    def checks(self) -> dict[str, bool]:
        sites = self._site_packages()
        sdk = any(
            (site / f"vieneu-{SDK_VERSION}.dist-info" / "METADATA").is_file()
            and (site / "vieneu" / "v3turbo.py").is_file()
            for site in sites
        )
        repo_cache = self._cache_dir / "hub" / f"models--{CODEC_REPO.replace('/', '--')}"
        try:
            revision = (repo_cache / "refs" / "main").read_text(encoding="utf-8").strip()
            # HF revisions are commit hashes, never relative filesystem paths.
            valid_revision = len(revision) == 40 and all(c in "0123456789abcdef" for c in revision)
            snapshot = repo_cache / "snapshots" / revision if valid_revision else None
        except OSError:
            snapshot = None
        checks = {
            "dependency_python": self._python.is_file(),
            "dependency_vieneu": sdk,
            "text_frontend_assets": any(
                _nonempty_file(site / "sea_g2p" / "sea_g2p.bin") for site in sites
            ),
            "model_graphs": all(_nonempty_file(self._onnx_dir / name) for name in GRAPH_FILES),
            "speaker_encoder": _nonempty_file(self._model_dir / "speaker_encoder.onnx"),
            "codec_assets": snapshot is not None and all(
                _nonempty_file(snapshot / name) for name in CODEC_FILES
            ),
            "sample_rate": self._profile.sample_rate == 48_000,
        }
        if self._options.get("denoise", True):
            checks["denoiser"] = _nonempty_file(self._model_dir / "denoiser.onnx")
        return checks

    def load(self) -> None:
        with self._lock:
            if self.is_loaded:
                return
            self.close()
            missing = [name for name, present in self.checks().items() if not present]
            if missing:
                raise ModelConfigurationError(
                    "VieNeu v3 Turbo is not ready: " + ", ".join(missing)
                    + ". Run scripts/setup_vieneu.py to install the isolated SDK, then "
                    "scripts/setup_vieneu.py --skip-install --download-assets to download models; "
                    "or configure the existing local paths."
                )
            self._temporary = tempfile.TemporaryDirectory(prefix="vassil-vieneu-")
            self._log = (Path(self._temporary.name) / "worker.log").open("w", encoding="utf-8")
            environment = os.environ.copy()
            environment.update({
                "HF_HOME": str(self._cache_dir),
                "HF_HUB_CACHE": str(self._cache_dir / "hub"),
                "HUGGINGFACE_HUB_CACHE": str(self._cache_dir / "hub"),
                "HF_HUB_OFFLINE": "1",
                "HF_DATASETS_OFFLINE": "1",
                "TRANSFORMERS_OFFLINE": "1",
                "HF_HUB_DISABLE_TELEMETRY": "1",
                "PYTHONUTF8": "1",
            })
            # The separate environment must not inherit the API's import paths.
            environment.pop("PYTHONPATH", None)
            environment.pop("PYTHONHOME", None)
            try:
                self._process = subprocess.Popen(
                    # Isolated mode omits the script directory from sys.path:
                    # this adapter is itself named vieneu.py and must never
                    # shadow the SDK installed in the worker environment.
                    [str(self._python), "-I", "-X", "utf8", "-u",
                     str(Path(__file__).with_name("vieneu_worker.py"))],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self._log,
                    text=True, encoding="utf-8", env=environment,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
                self._responses = queue.Queue()
                threading.Thread(
                    target=self._read_responses,
                    args=(self._process.stdout, self._responses), daemon=True,
                ).start()
                self._request({
                    "operation": "load", "model_dir": str(self._model_dir),
                    "onnx_dir": str(self._onnx_dir),
                    "threads": int(self._options.get("threads", 0)),
                    "scratch_dir": str(Path(self._temporary.name) / "sdk-reference"),
                }, timeout=self._timeout("load_timeout_seconds", 180))
            except Exception:
                logger.exception("Failed to load VieNeu profile %s", self._profile.model_id)
                self.close()
                raise

    @staticmethod
    def _read_responses(stream, responses: queue.Queue) -> None:
        try:
            for line in stream:
                responses.put(line)
        finally:
            responses.put(None)

    def _request(self, payload: dict, *, timeout: float) -> dict:
        try:
            if self._process is None or self._process.poll() is not None:
                self.close()
                raise InferenceTransientError("VieNeu worker stopped; retry to reload the model.")
            self._process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
            self._process.stdin.flush()
            raw = self._responses.get(timeout=max(0.1, timeout))
            if raw is None:
                self.close()
                raise InferenceTransientError("VieNeu worker exited before returning audio.")
            response = json.loads(raw)
            if not response.get("ok"):
                detail = str(response.get("error", "failed"))
                logger.error("VieNeu profile %s worker failed: %s", self._profile.model_id, detail)
                raise ModelConfigurationError("VieNeu worker: " + detail)
            return response
        except queue.Empty as exc:
            self.close()
            raise InferenceDeadlineError("VieNeu worker timed out; increase its timeout or shorten the text.") from exc
        except (BrokenPipeError, OSError, json.JSONDecodeError) as exc:
            self.close()
            raise InferenceTransientError("VieNeu worker communication failed; retry to reload.") from exc

    def synthesize(
        self, *, text: str, reference_audio: np.ndarray, reference_sample_rate: int,
        reference_text: str, language: str, num_steps: int | None = None,
        speed: float | None = None,
    ) -> GeneratedSpeech:
        # These ZipVoice controls are not implemented by the v3 Turbo SDK. Its
        # **kwargs would silently swallow them, giving misleading UI behavior.
        if num_steps is not None or speed not in (None, 1.0):
            raise ModelConfigurationError("VieNeu v3 Turbo does not support num_steps or speed.")
        with self._lock:
            self.load()
            import soundfile as sf

            directory = Path(self._temporary.name)
            reference_path = directory / "reference.wav"
            output_path = directory / "speech.npy"
            try:
                sf.write(reference_path, reference_audio, reference_sample_rate, subtype="FLOAT")
                response = self._request({
                    "operation": "synthesize", "text": text,
                    "reference_path": str(reference_path), "output_path": str(output_path),
                    "denoise": bool(self._options.get("denoise", True)),
                }, timeout=self._timeout("inference_timeout_seconds", 600))
                samples = np.load(output_path, allow_pickle=False)
                if (
                    samples.ndim != 1 or not 0 < samples.size <= 32_000_000
                    or not np.isfinite(samples).all() or response.get("sample_rate") != 48_000
                ):
                    raise ModelConfigurationError("VieNeu returned invalid audio.")
                samples = np.asarray(samples, dtype=np.float32)
                return GeneratedSpeech(
                    samples=samples, sample_rate=48_000, duration_seconds=len(samples) / 48_000,
                )
            finally:
                reference_path.unlink(missing_ok=True)
                output_path.unlink(missing_ok=True)
                (directory / "sdk-reference" / "reference-cleaned.wav").unlink(missing_ok=True)

    def close(self) -> None:
        with self._lock:
            process, self._process = self._process, None
            if process is not None:
                if process.stdin:
                    try:
                        process.stdin.close()
                    except OSError:
                        pass
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    if os.name == "nt":
                        # A Windows venv python.exe can be a redirector with
                        # the real SDK interpreter as its child. Killing only
                        # Popen's PID leaves that child and its model alive.
                        subprocess.run(
                            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, timeout=10, check=False,
                            creationflags=subprocess.CREATE_NO_WINDOW,
                        )
                    if process.poll() is None:
                        process.kill()
                    process.wait(timeout=5)
                if process.stdout:
                    process.stdout.close()
            if self._log:
                self._log.close()
                self._log = None
            if self._temporary:
                # taskkill can return before Windows has released inherited
                # log/audio handles in the real interpreter. Keep cleanup
                # bounded while waiting for that asynchronous teardown.
                deadline = time.monotonic() + 5
                while True:
                    try:
                        self._temporary.cleanup()
                        break
                    except PermissionError:
                        if os.name != "nt" or time.monotonic() >= deadline:
                            raise
                        time.sleep(0.05)
                self._temporary = None
