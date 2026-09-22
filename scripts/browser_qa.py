"""Run Studio browser checks against a model-free, disposable local workspace."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import URLError
from urllib.request import urlopen

try:
    from scripts.isolated_workspace import prepare_workspace
except ModuleNotFoundError:
    from isolated_workspace import prepare_workspace

ROOT = Path(__file__).resolve().parents[1]
STUDIO = ROOT / "frontend/studio-react"
QA_SCRIPTS = (
    "qa-landing.mjs",
    "qa-audio-workflows.mjs",
    "qa-jobs.mjs",
    "qa-voice-intake.mjs",
    "qa-transcript-review.mjs",
    "qa-settings.mjs",
    "qa-regressions.mjs",
)


def serve(address_path: Path) -> None:
    import uvicorn

    # Binding port 0 in the child avoids racing another process for a guessed free port.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        address_path.write_text(str(listener.getsockname()[1]), encoding="ascii")
        config = uvicorn.Config(
            "vvoice.main:create_app", factory=True, host="127.0.0.1",
            access_log=False, log_level="warning", ws="none",
        )
        uvicorn.Server(config).run(sockets=[listener])


def wait_for_server(process: subprocess.Popen, address_path: Path, timeout: float = 30) -> str:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Isolated QA server exited; inspect server.log in the QA output.")
        if address_path.exists():
            port = address_path.read_text(encoding="ascii").strip()
            if port:
                base_url = f"http://127.0.0.1:{int(port)}"
                try:
                    with urlopen(f"{base_url}/livez", timeout=1) as response:
                        if response.status == 200:
                            return base_url
                except (URLError, TimeoutError, ConnectionError):
                    pass
        time.sleep(0.1)
    raise TimeoutError("Isolated QA server did not start within 30 seconds.")


def run_checks(node: str, output_dir: Path, *, install_browser: bool = False) -> None:
    if not (STUDIO / "dist/index.html").is_file():
        raise RuntimeError("Build React Studio before browser QA: npm run build")
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="vassil-browser-qa-") as temporary:
        workspace = Path(temporary)
        environment = prepare_workspace(workspace, dict(os.environ))
        if install_browser:
            subprocess.run(
                [node, str(STUDIO / "node_modules/playwright/cli.js"), "install", "chromium"],
                cwd=STUDIO, env=environment, check=True, timeout=300,
            )
            environment["PLAYWRIGHT_CHANNEL"] = "chromium"
            environment.pop("PLAYWRIGHT_EXECUTABLE_PATH", None)
        address_path = workspace / "port.txt"
        with (output_dir / "server.log").open("w", encoding="utf-8") as server_log:
            process = subprocess.Popen(
                [sys.executable, str(Path(__file__).resolve()), "--serve", str(address_path)],
                cwd=ROOT, env=environment, stdout=server_log, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            try:
                base_url = wait_for_server(process, address_path)
                environment["VASSIL_QA_BASE_URL"] = base_url
                for script in QA_SCRIPTS:
                    environment["VASSIL_QA_OUTPUT_DIR"] = str(output_dir / Path(script).stem)
                    print(f"Browser QA: {script} ({base_url})", flush=True)
                    subprocess.run(
                        [node, str(STUDIO / "scripts" / script)], cwd=STUDIO,
                        env=environment, check=True, timeout=180,
                    )
            finally:
                if process.poll() is None:
                    process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node", default="node")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "artifacts/ui-qa/gate")
    parser.add_argument("--install-browser", action="store_true")
    parser.add_argument("--serve", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.serve:
        serve(args.serve)
    else:
        run_checks(args.node, args.output_dir.resolve(), install_browser=args.install_browser)


if __name__ == "__main__":
    main()
