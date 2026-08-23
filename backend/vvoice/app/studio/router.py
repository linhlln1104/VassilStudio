from __future__ import annotations

from pathlib import Path
import secrets

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from starlette.staticfiles import StaticFiles

from vvoice.core.env import first_env
from vvoice.shared.security.auth import request_has_valid_session


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
STATIC_DIR_RESOLVED = STATIC_DIR.resolve()
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


@router.get("/", include_in_schema=False)
async def product_index(request: Request):
    return _studio_html_response(request)


@router.get("/login", include_in_schema=False)
async def login_page(request: Request):
    return _studio_html_response(request)


@router.get("/setup", include_in_schema=False)
async def setup_page(request: Request):
    return _studio_html_response(request)


@router.get("/privacy", include_in_schema=False)
async def privacy_page(request: Request):
    return _studio_html_response(request)


@router.get("/license", include_in_schema=False)
async def license_page(request: Request):
    return _studio_html_response(request)


@router.get("/support", include_in_schema=False)
async def support_page(request: Request):
    return _studio_html_response(request)


@router.get("/operations", include_in_schema=False)
async def operations_page(request: Request):
    return _studio_html_response(request)


@router.get("/changelog", include_in_schema=False)
async def changelog_page(request: Request):
    return _studio_html_response(request)


@router.get("/studio", include_in_schema=False)
async def studio_index(request: Request):
    redirect = _studio_auth_redirect(request)
    if redirect:
        return redirect

    return _studio_html_response(request)


@router.get("/studio/{path:path}", include_in_schema=False)
async def studio_static_file_or_index(request: Request, path: str):
    asset = _safe_static_path(path)
    if asset and asset.is_file():
        return FileResponse(str(asset))

    redirect = _studio_auth_redirect(request)
    if redirect:
        return redirect

    return _studio_html_response(request)


def _studio_html_response(request: Request) -> HTMLResponse:
    style_nonce = secrets.token_urlsafe(24)
    request.state.style_nonce = style_nonce
    page = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    nonce_meta = f'<meta name="csp-style-nonce" content="{style_nonce}" />'
    page = page.replace("</head>", f"    {nonce_meta}\n  </head>", 1)
    return HTMLResponse(page, headers={"Cache-Control": "no-store"})


def _safe_static_path(path: str) -> Path | None:
    candidate = (STATIC_DIR / path).resolve()
    try:
        candidate.relative_to(STATIC_DIR_RESOLVED)
    except ValueError:
        return None
    return candidate


def _studio_auth_redirect(request: Request) -> RedirectResponse | None:
    settings = request.app.state.container.settings.security
    if not getattr(settings, "auth_required", False):
        return None
    if request_has_valid_session(request):
        return None

    auth = getattr(request.app.state.container, "auth", None)
    target = "/setup" if auth and auth.setup_required else "/login"
    return RedirectResponse(url=target, status_code=303)
