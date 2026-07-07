from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse
from starlette.staticfiles import StaticFiles

from vvoice.core.env import first_env


def _resolve_studio_dir() -> Path:
    candidates: list[Path] = []
    configured = first_env("VASSIL_STUDIO_DIR", "VVOICE_STUDIO_DIR")
    if configured:
        candidates.append(Path(configured))

    current_file = Path(__file__).resolve()
    for parent in current_file.parents:
        candidates.append(parent / "frontend" / "studio-react" / "dist")
        candidates.append(parent / "frontend" / "studio")

    candidates.append(current_file.parent / "static")

    for candidate in candidates:
        if (candidate / "index.html").is_file():
            return candidate

    raise RuntimeError("VassilStudio assets were not found. Set VASSIL_STUDIO_DIR.")


router = APIRouter()
STATIC_DIR = _resolve_studio_dir()
ASSETS_DIR = STATIC_DIR / "assets"

if ASSETS_DIR.is_dir():
    router.mount(
        "/studio/assets",
        StaticFiles(directory=str(ASSETS_DIR)),
        name="studio-assets",
    )
else:
    router.mount(
        "/studio/assets",
        StaticFiles(directory=str(STATIC_DIR)),
        name="studio-assets",
    )


@router.get("/studio", include_in_schema=False)
async def studio_index():
    return FileResponse(str(STATIC_DIR / "index.html"))


@router.get("/studio/{path:path}", include_in_schema=False)
async def studio_static_file_or_index(path: str):
    asset = STATIC_DIR / path
    if asset.is_file():
        return FileResponse(str(asset))

    return FileResponse(str(STATIC_DIR / "index.html"))
