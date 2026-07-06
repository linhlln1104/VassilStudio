from __future__ import annotations

import argparse
import json
from pathlib import Path

from vvoice.main import create_app


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "contracts" / "openapi" / "vassil.openapi.json"
LEGACY_OUTPUT = ROOT / "contracts" / "openapi" / "vvoice.openapi.json"


def export_openapi(output: Path) -> Path:
    app = create_app()
    schema = app.openapi()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="Export the Vassil Studio OpenAPI contract.")
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
