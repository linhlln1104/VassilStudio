from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.browser_qa import ROOT, prepare_workspace, wait_for_server


def test_browser_workspace_ignores_host_config_and_disables_models(tmp_path: Path) -> None:
    environment = prepare_workspace(tmp_path, {
        "PATH": "test-path", "VASSIL_ROOT": "private-root", "VVOICE_CONFIG": "private-config",
        "VASSIL_API_KEYS": "private-key", "VASSIL_AUTH_DB_PATH": "private-auth",
        "VASSIL_WARMUP_ON_STARTUP": "true", "PYTHONPATH": "private-imports",
    })
    assert environment["PATH"] == "test-path"
    assert environment["VASSIL_ROOT"] == str(tmp_path)
    assert environment["PYTHONPATH"] == str(ROOT / "backend")
    assert "VVOICE_CONFIG" not in environment
    assert "VASSIL_AUTH_DB_PATH" not in environment
    assert "VASSIL_API_KEYS" not in environment
    config = json.loads(Path(environment["VASSIL_CONFIG"]).read_text(encoding="utf-8"))
    assert not config["asr"]["enabled"]
    assert not config["tts"]["enabled"]
    assert not config["runtime"]["warmup_on_startup"]
    assert config["storage"]["voices_dir"] == "data/voices"


def test_isolated_server_starts_on_its_own_port_and_uses_empty_storage(tmp_path: Path) -> None:
    pytest.importorskip("uvicorn")
    from urllib.request import urlopen

    environment = prepare_workspace(tmp_path, dict(os.environ))
    address = tmp_path / "port.txt"
    process = subprocess.Popen(
        [sys.executable, str(ROOT / "scripts/browser_qa.py"), "--serve", str(address)],
        env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    try:
        base_url = wait_for_server(process, address)
        with urlopen(f"{base_url}/api/v1/voices", timeout=5) as response:
            assert json.load(response) == []
        assert (tmp_path / "data/auth.sqlite3").is_file()
    finally:
        process.terminate()
        process.wait(timeout=10)


@pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell launcher regression")
def test_node_resolution_repairs_missing_path_for_child_scripts(tmp_path: Path) -> None:
    node_directory = tmp_path / "Node installation with spaces"
    node_directory.mkdir()
    node = node_directory / "node.exe"
    node.touch()
    (node_directory / "npm.cmd").touch()
    environment = dict(os.environ)
    environment["VASSIL_NODE_PATH"] = str(node)
    environment["VASSIL_TOOLCHAIN_TEST_PS"] = str(ROOT / "scripts/node_toolchain.ps1")
    command = (
        '. $env:VASSIL_TOOLCHAIN_TEST_PS; $env:PATH = ""; '
        '$resolvedTools = Resolve-NodeToolchain; '
        '@{Node=$resolvedTools.Node; Npm=$resolvedTools.Npm; Path=$env:PATH} | ConvertTo-Json'
    )
    encoded = base64.b64encode(command.encode("utf-16le")).decode("ascii")
    result = subprocess.run(
        ["powershell", "-NoProfile", "-EncodedCommand", encoded],
        env=environment, capture_output=True, text=True, check=True, timeout=15,
    )
    resolved = json.loads(result.stdout)
    assert Path(resolved["Node"]) == node
    assert Path(resolved["Npm"]) == node_directory / "npm.cmd"
    assert resolved["Path"].split(os.pathsep)[0] == str(node_directory)
