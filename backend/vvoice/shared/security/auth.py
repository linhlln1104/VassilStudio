from __future__ import annotations

import hmac
from collections.abc import Mapping, Sequence

from fastapi import HTTPException, Request, WebSocket, status

from vvoice.core.brand import API_BRAND_NAME


API_KEY_HEADER = "X-Vassil-API-Key"
LEGACY_API_KEY_HEADER = "X-VVoice-API-Key"
API_KEY_QUERY = "api_key"


async def require_api_key(request: Request) -> None:
    keys = request.app.state.container.settings.security.api_keys
    if not keys:
        return

    candidate = _candidate_from_mapping(request.headers, request.query_params)
    if not _matches(candidate, keys):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Missing or invalid {API_BRAND_NAME} key",
            headers={"WWW-Authenticate": "Bearer"},
        )


def websocket_is_authorized(websocket: WebSocket) -> bool:
    keys = websocket.app.state.container.settings.security.api_keys
    if not keys:
        return True

    candidate = _candidate_from_mapping(websocket.headers, websocket.query_params)
    return _matches(candidate, keys)


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
