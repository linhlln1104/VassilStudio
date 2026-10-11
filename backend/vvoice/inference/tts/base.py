from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from pathlib import Path
from typing import Protocol

import numpy as np


@dataclass(frozen=True)
class GeneratedSpeech:
    samples: np.ndarray
    sample_rate: int
    duration_seconds: float


@dataclass(frozen=True)
class TtsCapabilities:
    reference_audio: bool = True
    num_steps: bool = False
    speed: bool = False


class TtsAdapter(Protocol):
    capabilities: TtsCapabilities

    def checks(self) -> dict[str, bool]: ...

    def load(self) -> None: ...

    def close(self) -> None: ...

    def synthesize(
        self, *, text: str, reference_audio: np.ndarray, reference_sample_rate: int,
        reference_text: str, language: str, num_steps: int | None = None,
        speed: float | None = None,
    ) -> GeneratedSpeech: ...


def usable_file(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def module_available(name: str) -> bool:
    """Probe optional dependencies without importing their model runtimes."""
    try:
        return find_spec(name) is not None
    except (ImportError, ValueError, AttributeError):
        return False
