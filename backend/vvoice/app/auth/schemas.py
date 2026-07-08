from __future__ import annotations

from pydantic import BaseModel, Field


class AuthUser(BaseModel):
    account_id: str
    username: str
    role: str


class AuthStatusResponse(BaseModel):
    auth_required: bool
    setup_required: bool
    authenticated: bool
    api_key_auth_enabled: bool
    user: AuthUser | None


class AuthSetupRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=8, max_length=512)


class AuthLoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=1, max_length=512)


class AuthSessionResponse(BaseModel):
    authenticated: bool
    user: AuthUser
    expires_at: str


class AuthLogoutResponse(BaseModel):
    logged_out: bool
