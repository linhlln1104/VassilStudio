from __future__ import annotations

from dataclasses import asdict
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from vvoice.app.auth.iam import IamError
from vvoice.shared.security.auth import Principal, require_api_key, require_scope


router = APIRouter()


class ServiceAccountInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    role: Literal["admin", "operator", "editor", "reviewer"] = "operator"
    scopes: list[str] | None = None


class ApiKeyInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    expires_at: str | None = None


class PrincipalResponse(BaseModel):
    principal_id: str
    name: str
    kind: str
    role: str
    scopes: list[str]


class ServiceAccountResponse(BaseModel):
    principal_id: str
    name: str
    role: str
    scopes: list[str]
    created_at: str
    disabled_at: str | None


class ApiKeyResponse(BaseModel):
    key_id: str
    principal_id: str
    name: str
    prefix: str
    created_at: str
    expires_at: str | None
    revoked_at: str | None
    last_used_at: str | None


class IssuedKeyResponse(BaseModel):
    key: ApiKeyResponse
    token: str


class AuditEventResponse(BaseModel):
    event_id: int
    created_at: str
    actor_id: str | None
    actor_name: str | None
    actor_kind: str | None
    action: str
    resource_type: str
    resource_id: str
    request_id: str | None
    details: dict


@router.get("/principal", response_model=PrincipalResponse)
async def principal_info(principal: Principal = Depends(require_api_key)):
    return asdict(principal)


@router.get("/service-accounts", response_model=list[ServiceAccountResponse], dependencies=[Depends(require_scope("iam:manage"))])
def service_accounts(request: Request):
    return request.app.state.container.auth.list_service_accounts()


@router.post("/service-accounts", status_code=201, response_model=ServiceAccountResponse)
def create_service_account(payload: ServiceAccountInput, request: Request,
                           principal: Principal = Depends(require_scope("iam:manage"))):
    auth = request.app.state.container.auth
    try:
        result = auth.create_service_account(payload.name, payload.role, payload.scopes)
    except IamError as exc:
        raise HTTPException(400, str(exc)) from exc
    _audit(request, principal, "iam.service_account.created", "service_account", result["principal_id"])
    return result


@router.post("/service-accounts/{principal_id}/disable", response_model=ServiceAccountResponse)
def disable_service_account(principal_id: str, request: Request,
                            principal: Principal = Depends(require_scope("iam:manage"))):
    try:
        result = request.app.state.container.auth.disable_service_account(principal_id)
    except IamError as exc:
        raise HTTPException(404, str(exc)) from exc
    _audit(request, principal, "iam.service_account.disabled", "service_account", principal_id)
    return result


@router.get("/api-keys", response_model=list[ApiKeyResponse], dependencies=[Depends(require_scope("iam:manage"))])
def api_keys(request: Request):
    return request.app.state.container.auth.list_api_keys()


@router.post("/service-accounts/{principal_id}/keys", status_code=201, response_model=IssuedKeyResponse)
def issue_api_key(principal_id: str, payload: ApiKeyInput, request: Request, response: Response,
                  principal: Principal = Depends(require_scope("iam:manage"))):
    try:
        result = request.app.state.container.auth.create_api_key(principal_id, payload.name, payload.expires_at)
    except IamError as exc:
        raise HTTPException(400, str(exc)) from exc
    response.headers["Cache-Control"] = "no-store"
    _audit(request, principal, "iam.api_key.created", "api_key", result["key"]["key_id"])
    return result


@router.delete("/api-keys/{key_id}")
def revoke_api_key(key_id: str, request: Request,
                   principal: Principal = Depends(require_scope("iam:manage"))):
    try:
        request.app.state.container.auth.revoke_api_key(key_id)
    except IamError as exc:
        raise HTTPException(404, str(exc)) from exc
    _audit(request, principal, "iam.api_key.revoked", "api_key", key_id)
    return {"revoked": True}


@router.get("/audit", response_model=list[AuditEventResponse], dependencies=[Depends(require_scope("audit:read"))])
def audit_events(request: Request, limit: int = Query(100, ge=1, le=500),
                 offset: int = Query(0, ge=0), actor_id: str | None = None):
    return request.app.state.container.auth.list_audit(limit, offset, actor_id)


def _audit(request: Request, principal: Principal, action: str, resource_type: str, resource_id: str):
    request.app.state.container.auth.record_audit(
        principal, action, resource_type, resource_id, getattr(request.state, "request_id", None),
    )
