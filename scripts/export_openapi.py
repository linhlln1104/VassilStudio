from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile

try:
    from scripts._path import ROOT, bootstrap_backend_path
    from scripts.isolated_workspace import isolated_environment
except ModuleNotFoundError:
    from _path import ROOT, bootstrap_backend_path
    from isolated_workspace import isolated_environment

bootstrap_backend_path()

DEFAULT_OUTPUT = ROOT / "contracts" / "openapi" / "vassil.openapi.json"
LEGACY_OUTPUT = ROOT / "contracts" / "openapi" / "vvoice.openapi.json"


def export_openapi(output: Path) -> Path:
    with tempfile.TemporaryDirectory(prefix="vassil-openapi-") as temporary:
        with isolated_environment(Path(temporary)):
            from vvoice.main import create_app

            app = create_app()
            try:
                schema = app.openapi()
            finally:
                app.state.container.shutdown()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="Export the VassilStudio OpenAPI contract.")
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Output JSON path. Defaults to contracts/openapi/vassil.openapi.json.",
    )
    args = parser.parse_args()

    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output

    written = export_openapi(output)
    print(f"OpenAPI contract written: {written}")
    if output.resolve() == DEFAULT_OUTPUT.resolve():
        legacy = export_openapi(LEGACY_OUTPUT)
        print(f"Legacy OpenAPI contract written: {legacy}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
