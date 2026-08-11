import os

import pytest


@pytest.fixture(autouse=True)
def isolate_vassil_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in tuple(os.environ):
        if name.startswith(("VASSIL_", "VVOICE_")):
            monkeypatch.delenv(name, raising=False)
