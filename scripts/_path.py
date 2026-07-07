from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"


def bootstrap_backend_path() -> None:
    backend_path = str(BACKEND)
    if backend_path not in sys.path:
        sys.path.insert(0, backend_path)
