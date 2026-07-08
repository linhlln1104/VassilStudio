from __future__ import annotations

import hmac
from collections.abc import Mapping, Sequence

from fastapi import HTTPException, Request, WebSocket, status

from vvoice.core.brand import API_BRAND_NAME


API_KEY_HEADER = "X-Vassil-API-Key"
LEGACY_API_KEY_HEADER = "X-VVoice-API-Key"
API_KEY_QUERY = "api_key"


async def require_api_key(request: Request) -> None:
    settings = request.app.state.container.settings.security
    keys = settings.api_keys
    if request_has_valid_session(request):
        return
    if not keys and not getattr(settings, "auth_required", False):
        return

    candidate = _candidate_from_mapping(request.headers, request.query_params)
    if keys and _matches(candidate, keys):
        return

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=f"Missing or invalid {API_BRAND_NAME} credential",
        headers={"WWW-Authenticate": "Bearer"},
    )


def websocket_is_authorized(websocket: WebSocket) -> bool:
    settings = websocket.app.state.container.settings.security
    keys = settings.api_keys
    if websocket_has_valid_session(websocket):
        return True
    if not keys and not getattr(settings, "auth_required", False):
        return True

    candidate = _candidate_from_mapping(websocket.headers, websocket.query_params)
    return _matches(candidate, keys)


async def require_studio_session(request: Request) -> None:
    settings = request.app.state.container.settings.security
    if not getattr(settings, "auth_required", False):
        return
    if request_has_valid_session(request):
        return

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing or invalid Studio session.",
    )


def request_has_valid_session(request: Request) -> bool:
    settings = request.app.state.container.settings.security
    if not getattr(settings, "auth_required", False):
        return False
    auth = getattr(request.app.state.container, "auth", None)
    if auth is None:
        return False

    token = request.cookies.get(getattr(settings, "session_cookie_name", "vassil_session"))
    return auth.account_from_session_token(token) is not None


def websocket_has_valid_session(websocket: WebSocket) -> bool:
    settings = websocket.app.state.container.settings.security
    if not getattr(settings, "auth_required", False):
        return False
    auth = getattr(websocket.app.state.container, "auth", None)
    if auth is None:
        return False

    token = websocket.cookies.get(getattr(settings, "session_cookie_name", "vassil_session"))
    return auth.account_from_session_token(token) is not None


def _candidate_from_mapping(headers: Mapping[str, str], query: Mapping[str, str]) -> str | None:
    for header in (API_KEY_HEADER, LEGACY_API_KEY_HEADER):
        header_value = headers.get(header)
        if header_value:
            return header_value.strip()

    authorization = headers.get("Authorization") or headers.get("authorization")
    if authorization:
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() == "bearer" and value.strip():
            return value.strip()

    query_value = query.get(API_KEY_QUERY)
    return query_value.strip() if query_value else None


def _matches(candidate: str | None, keys: Sequence[str]) -> bool:
    if not candidate:
        return False
    return any(hmac.compare_digest(candidate, key) for key in keys)
