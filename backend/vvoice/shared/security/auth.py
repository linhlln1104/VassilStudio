from __future__ import annotations

import hashlib
import hmac
from collections.abc import Mapping, Sequence

from fastapi import Depends, HTTPException, Request, Security, WebSocket, status
from fastapi.security import APIKeyCookie, APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from vvoice.core.brand import API_BRAND_NAME
from vvoice.shared.security.principal import (
    ALL_SCOPES, ROLE_SCOPES, Principal,
    current_actor_id as current_actor_id,
    current_principal as current_principal,
    reset_current_principal as reset_current_principal,
    set_current_principal,
)


API_KEY_HEADER = "X-Vassil-API-Key"
LEGACY_API_KEY_HEADER = "X-VVoice-API-Key"
API_KEY_QUERY = "api_key"
_header_scheme = APIKeyHeader(name=API_KEY_HEADER, scheme_name="ApiKey", auto_error=False)
_bearer_scheme = HTTPBearer(scheme_name="BearerKey", auto_error=False)
_cookie_scheme = APIKeyCookie(name="vassil_session", scheme_name="StudioSession", auto_error=False)


async def require_api_key(
    request: Request,
    _header: str | None = Security(_header_scheme),
    _bearer: HTTPAuthorizationCredentials | None = Security(_bearer_scheme),
    _cookie: str | None = Security(_cookie_scheme),
) -> Principal:
    principal = getattr(request.state, "principal", None) or _resolve_principal(request)
    if principal is None:
        raise HTTPException(
            status_code=401, detail=f"Missing or invalid {API_BRAND_NAME} credential",
            headers={"WWW-Authenticate": "Bearer"},
        )
    request.state.principal = principal
    set_current_principal(principal)
    return principal


def require_scope(scope: str):
    if scope not in ALL_SCOPES:
        raise ValueError(f"Unknown permission scope: {scope}")

    async def permission(principal: Principal = Depends(require_api_key)) -> Principal:
        if not principal.has_scope(scope):
            raise HTTPException(status_code=403, detail=f"Permission required: {scope}")
        return principal
    return permission


def require_domain_scope(domain: str):
    async def permission(request: Request, principal: Principal = Depends(require_api_key)) -> Principal:
        scope = f"{domain}:{'read' if request.method in {'GET', 'HEAD', 'OPTIONS'} else 'write'}"
        if domain == "tts" and request.url.path.startswith("/api/v1/tts/models"):
            scope = "models:read" if request.method in {"GET", "HEAD", "OPTIONS"} else "models:manage"
        if not principal.has_scope(scope):
            raise HTTPException(status_code=403, detail=f"Permission required: {scope}")
        return principal
    return permission


def _resolve_principal(connection: Request | WebSocket) -> Principal | None:
    container = connection.app.state.container
    settings = container.settings.security
    auth = getattr(container, "auth", None)
    candidate = _candidate_from_mapping(connection.headers, connection.query_params)
    # Explicit keys win over cookies and anonymous local mode: revoked/scoped keys
    # cannot fall through into a more privileged browser session.
    if candidate:
        if auth is not None:
            principal = auth.principal_from_api_key(candidate)
            if principal is not None:
                return principal
        if _matches(candidate, settings.api_keys):
            digest = hashlib.sha256(candidate.encode()).hexdigest()[:16]
            return Principal(f"legacy-key:{digest}", "Configured API key", "legacy_key", "admin", ("*",))
        return None
    if auth is not None and getattr(settings, "auth_required", False):
        principal = studio_principal(connection)
        if principal is not None:
            return principal
    if not settings.api_keys and not getattr(settings, "auth_required", False):
        return Principal("local", "Local workspace", "local", "admin", ("*",))
    return None


def websocket_is_authorized(websocket: WebSocket) -> bool:
    principal = _resolve_principal(websocket)
    if principal is None or not principal.has_scope("asr:write"):
        return False
    websocket.state.principal = principal
    set_current_principal(principal)
    return True


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
    return studio_principal(request) is not None


def websocket_has_valid_session(websocket: WebSocket) -> bool:
    return studio_principal(websocket) is not None


def studio_principal(connection: Request | WebSocket) -> Principal | None:
    settings = connection.app.state.container.settings.security
    if not getattr(settings, "auth_required", False):
        return None
    auth = getattr(connection.app.state.container, "auth", None)
    if auth is None:
        return None
    token = connection.cookies.get(getattr(settings, "session_cookie_name", "vassil_session"))
    if not token:
        return None
    account = auth.account_from_session_token(token)
    if account is not None:
        return Principal(account.account_id, account.username, "user", account.role,
                         tuple(sorted(ROLE_SCOPES.get(account.role, frozenset()))))
    return auth.principal_from_key_session(token)


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
