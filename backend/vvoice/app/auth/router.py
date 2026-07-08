from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status

from vvoice.app.auth.schemas import (
    AuthChangePasswordRequest,
    AuthLoginRequest,
    AuthLogoutResponse,
    AuthPasswordChangeResponse,
    AuthSessionResponse,
    AuthSetupRequest,
    AuthStatusResponse,
    AuthUser,
)
from vvoice.app.auth.service import Account, AuthError, CreatedSession, LocalAuthService


router = APIRouter()


@router.get("/status", response_model=AuthStatusResponse)
async def auth_status(request: Request) -> AuthStatusResponse:
    auth = _auth_service(request)
    settings = request.app.state.container.settings.security
    account = auth.account_from_session_token(_session_cookie(request)) if auth.auth_required else None
    return AuthStatusResponse(
        auth_required=auth.auth_required,
        setup_required=auth.setup_required,
        authenticated=account is not None,
        api_key_auth_enabled=bool(settings.api_keys),
        user=_auth_user(account) if account else None,
    )


@router.post("/setup", response_model=AuthSessionResponse, status_code=status.HTTP_201_CREATED)
async def setup_owner(
    payload: AuthSetupRequest,
    request: Request,
    response: Response,
) -> AuthSessionResponse:
    auth = _auth_service(request)
    if not auth.auth_required:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Local account setup is disabled because Studio auth is not required.",
        )
    if not auth.setup_required:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Local owner account already exists.",
        )

    try:
        account = auth.create_owner(payload.username, payload.password)
        session = auth.create_session(account, user_agent=request.headers.get("user-agent"))
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    _set_session_cookie(request, response, session)
    return AuthSessionResponse(
        authenticated=True,
        user=_auth_user(account),
        expires_at=session.expires_at,
    )


@router.post(
    "/login",
    response_model=AuthSessionResponse,
    responses={429: {"description": "Too many login attempts."}},
)
async def login(
    payload: AuthLoginRequest,
    request: Request,
    response: Response,
) -> AuthSessionResponse:
    auth = _auth_service(request)
    if not auth.auth_required:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Studio auth is not required for this workspace.",
        )
    if auth.setup_required:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Create the local owner account before logging in.",
        )

    rate_limit_key = _rate_limit_identifier(request, payload.username)
    retry_after = auth.record_login_attempt(rate_limit_key)
    if retry_after is not None:
        _raise_rate_limited(retry_after, "Too many login attempts. Try again later.")

    account = auth.authenticate(payload.username, payload.password)
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )

    auth.clear_login_attempts(rate_limit_key)
    session = auth.create_session(account, user_agent=request.headers.get("user-agent"))
    _set_session_cookie(request, response, session)
    return AuthSessionResponse(
        authenticated=True,
        user=_auth_user(account),
        expires_at=session.expires_at,
    )


@router.post("/logout", response_model=AuthLogoutResponse)
async def logout(request: Request, response: Response) -> AuthLogoutResponse:
    auth = _auth_service(request)
    auth.revoke_session(_session_cookie(request))
    settings = request.app.state.container.settings.security
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        samesite="lax",
        secure=settings.secure_cookies,
        httponly=True,
    )
    return AuthLogoutResponse(logged_out=True)


@router.get("/me", response_model=AuthUser)
async def me(request: Request) -> AuthUser:
    auth = _auth_service(request)
    account = auth.account_from_session_token(_session_cookie(request)) if auth.auth_required else None
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Studio session.",
        )
    return _auth_user(account)


@router.post(
    "/change-password",
    response_model=AuthPasswordChangeResponse,
    responses={429: {"description": "Too many password change attempts."}},
)
async def change_password(
    payload: AuthChangePasswordRequest,
    request: Request,
) -> AuthPasswordChangeResponse:
    auth = _auth_service(request)
    token = _session_cookie(request)
    account = auth.account_from_session_token(token) if auth.auth_required else None
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Studio session.",
        )

    rate_limit_key = _rate_limit_identifier(request, account.username)
    retry_after = auth.record_password_change_attempt(rate_limit_key)
    if retry_after is not None:
        _raise_rate_limited(retry_after, "Too many password change attempts. Try again later.")

    try:
        revoked_count = auth.change_password(
            account.account_id,
            payload.current_password,
            payload.new_password,
            current_session_token=token,
        )
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    auth.clear_password_change_attempts(rate_limit_key)
    return AuthPasswordChangeResponse(password_changed=True, other_sessions_revoked=revoked_count)


def _auth_service(request: Request) -> LocalAuthService:
    return request.app.state.container.auth


def _session_cookie(request: Request) -> str | None:
    name = request.app.state.container.settings.security.session_cookie_name
    return request.cookies.get(name)


def _set_session_cookie(request: Request, response: Response, session: CreatedSession) -> None:
    settings = request.app.state.container.settings.security
    response.set_cookie(
        key=settings.session_cookie_name,
        value=session.token,
        max_age=settings.session_ttl_seconds,
        expires=settings.session_ttl_seconds,
        path="/",
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
    )


def _rate_limit_identifier(request: Request, username: str) -> str:
    host = request.client.host if request.client else "unknown"
    normalized = username.strip().lower()[:80] or "blank"
    return f"{host}:{normalized}"


def _raise_rate_limited(retry_after_seconds: int, detail: str) -> None:
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=detail,
        headers={"Retry-After": str(retry_after_seconds)},
    )


def _auth_user(account: Account) -> AuthUser:
    return AuthUser(
        account_id=account.account_id,
        username=account.username,
        role=account.role,
    )
