from dataclasses import replace
from datetime import UTC, datetime, timedelta
import json
import sqlite3
from types import SimpleNamespace

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
import pytest

from vvoice.app.auth.iam import IamError
from vvoice.app.auth.router import router as auth_router
from vvoice.app.auth.service import LocalAuthService
from vvoice.app.system.router import router as system_router
from vvoice.core.config import SecuritySettings
from vvoice.domains.asr.router import router as asr_router
from vvoice.domains.tts.router import router as tts_router
from vvoice.domains.voices.router import router as voices_router
from vvoice.main import register_exception_handlers, register_openapi, register_request_middleware
from vvoice.shared.security.auth import (
    current_actor_id, current_principal, require_api_key, require_domain_scope, require_scope,
)


def security(tmp_path, *, auth_required=True):
    return SecuritySettings(api_keys=("bootstrap-key",), auth_required=auth_required,
                            auth_db_path=tmp_path / "auth.sqlite3", session_cookie_name="test_session",
                            session_ttl_seconds=3600, session_secret="test-secret", secure_cookies=False)


def make_app(settings):
    app = FastAPI()
    app.state.container = SimpleNamespace(settings=SimpleNamespace(security=settings), auth=LocalAuthService(settings))
    app.include_router(auth_router, prefix="/api/v1/auth")

    @app.get("/identity")
    async def identity(principal=Depends(require_api_key)):
        return {"actor_id": current_actor_id(), "principal_id": principal.principal_id}

    @app.post("/produce", dependencies=[Depends(require_scope("production:write"))])
    def produce():
        return {"actor_id": current_actor_id()}

    @app.post("/approve", dependencies=[Depends(require_scope("production:review"))])
    def approve():
        return {"approved": True}

    register_exception_handlers(app)
    register_request_middleware(app)
    register_openapi(app, settings.session_cookie_name)
    return app


def issue(auth, role="editor", scopes=None):
    account = auth.create_service_account(f"Test {role}", role, scopes)
    result = auth.create_api_key(account["principal_id"], "CI key")
    return account, result


def test_keys_are_durable_hashed_revocable_and_never_listed_in_plaintext(tmp_path):
    settings = security(tmp_path)
    auth = LocalAuthService(settings)
    account, issued = issue(auth)
    token = issued["token"]
    assert auth.principal_from_api_key(token).principal_id == account["principal_id"]
    with sqlite3.connect(settings.auth_db_path) as db:
        row = db.execute("select token_hash from api_keys").fetchone()
        assert len(row[0]) == 64 and token not in row[0]
    assert token.encode() not in settings.auth_db_path.read_bytes()
    restarted = LocalAuthService(settings)
    assert restarted.principal_from_api_key(token) is not None
    assert token not in json.dumps(restarted.list_api_keys())
    assert restarted.list_api_keys()[0]["last_used_at"] is not None
    assert restarted.revoke_api_key(issued["key"]["key_id"])
    assert LocalAuthService(settings).principal_from_api_key(token) is None


def test_disable_account_revokes_all_keys_and_prevents_new_keys(tmp_path):
    auth = LocalAuthService(security(tmp_path))
    account, first = issue(auth)
    second = auth.create_api_key(account["principal_id"], "Second")
    auth.disable_service_account(account["principal_id"])
    assert auth.principal_from_api_key(first["token"]) is None
    assert auth.principal_from_api_key(second["token"]) is None
    assert all(key["revoked_at"] for key in auth.list_api_keys())
    with pytest.raises(IamError, match="Active service"):
        auth.create_api_key(account["principal_id"], "Third")


def test_scopes_cannot_exceed_role_and_narrow_admin_does_not_bypass_acl(tmp_path):
    auth = LocalAuthService(security(tmp_path))
    for scopes in (["iam:manage"], ["*"], ["unknown"], []):
        with pytest.raises(IamError):
            auth.create_service_account("Bad editor", "editor", scopes)
    _, key = issue(auth, role="admin", scopes=["production:read"])
    principal = auth.principal_from_api_key(key["token"])
    assert principal.has_scope("production:read")
    assert not principal.has_scope("production:write") and not principal.is_admin


def test_key_expiry_enforced_and_requires_timezone(tmp_path):
    settings = security(tmp_path)
    auth = LocalAuthService(settings)
    account = auth.create_service_account("Expiring", "reviewer")
    for expiry in ("yesterday", "2001-01-01T00:00:00Z", "2099-01-01T00:00:00"):
        with pytest.raises(IamError):
            auth.create_api_key(account["principal_id"], "Invalid", expiry)
    key = auth.create_api_key(account["principal_id"], "Valid", (datetime.now(UTC) + timedelta(days=1)).isoformat())
    assert auth.principal_from_api_key(key["token"])
    with sqlite3.connect(settings.auth_db_path) as db:
        db.execute("update api_keys set expires_at = '2001-01-01T00:00:00Z'")
    assert auth.principal_from_api_key(key["token"]) is None


def test_http_roles_enforced_with_actor_trace_and_persistent_audit(tmp_path):
    app = make_app(security(tmp_path))
    account, key = issue(app.state.container.auth, "editor")
    client = TestClient(app)
    headers = {"X-Vassil-API-Key": key["token"], "X-Request-ID": "trace-job-123"}
    response = client.post("/produce", headers=headers)
    assert response.status_code == 200
    assert response.json()["actor_id"] == account["principal_id"]
    denied = client.post("/approve", headers=headers)
    assert denied.status_code == 403
    assert denied.json()["request_id"] == "trace-job-123"
    assert denied.json()["error"] == "http_403"
    assert client.get("/api/v1/auth/service-accounts", headers=headers).status_code == 403
    assert client.get("/identity").status_code == 401
    audit = LocalAuthService(app.state.container.settings.security).list_audit()
    mutation = next(event for event in audit if event["resource_id"] == "/produce")
    assert mutation["actor_id"] == account["principal_id"]
    assert mutation["request_id"] == "trace-job-123"
    assert key["token"] not in json.dumps(audit)
    assert current_principal() is None


def test_explicit_key_never_falls_back_to_owner_cookie_or_local_admin(tmp_path):
    app = make_app(security(tmp_path))
    owner = app.state.container.auth.create_owner("owner", "correct horse battery")
    session = app.state.container.auth.create_session(owner)
    _, key = issue(app.state.container.auth, "reviewer")
    client = TestClient(app)
    client.cookies.set("test_session", session.token)
    assert client.post("/produce").status_code == 200
    assert client.post("/produce", headers={"Authorization": f"Bearer {key['token']}"}).status_code == 403
    app.state.container.auth.revoke_api_key(key["key"]["key_id"])
    assert client.post("/produce", headers={"Authorization": f"Bearer {key['token']}"}).status_code == 401
    local = TestClient(make_app(replace(security(tmp_path / "local", auth_required=False), api_keys=())))
    assert local.post("/produce").status_code == 200
    assert local.post("/produce", headers={"X-Vassil-API-Key": "invalid"}).status_code == 401


def test_management_api_issues_once_and_audits_without_secrets(tmp_path):
    app = make_app(security(tmp_path))
    client = TestClient(app, headers={"X-Vassil-API-Key": "bootstrap-key"})
    account = client.post("/api/v1/auth/service-accounts", json={"name": "Review bot", "role": "reviewer"})
    assert account.status_code == 201
    principal_id = account.json()["principal_id"]
    response = client.post(f"/api/v1/auth/service-accounts/{principal_id}/keys", json={"name": "Review key"})
    assert response.status_code == 201 and response.headers["cache-control"] == "no-store"
    token = response.json()["token"]
    assert token not in client.get("/api/v1/auth/api-keys").text
    events = client.get("/api/v1/auth/audit").json()
    assert any(event["action"] == "iam.api_key.created" for event in events)
    assert token not in json.dumps(events)
    assert client.post("/approve", headers={"X-Vassil-API-Key": token}).status_code == 200
    assert client.delete(f"/api/v1/auth/api-keys/{response.json()['key']['key_id']}").status_code == 200
    assert client.post("/approve", headers={"X-Vassil-API-Key": token}).status_code == 401


def test_openapi_documents_auth_binary_media_and_trace_headers(tmp_path):
    app = make_app(security(tmp_path))
    app.include_router(tts_router, prefix="/api/v1/tts", dependencies=[Depends(require_domain_scope("tts"))])
    app.include_router(asr_router, prefix="/api/v1/asr", dependencies=[Depends(require_domain_scope("asr"))])
    app.include_router(voices_router, prefix="/api/v1/voices", dependencies=[Depends(require_domain_scope("voices"))])
    app.include_router(system_router)
    schema = app.openapi()
    schemes = schema["components"]["securitySchemes"]
    assert schemes["ApiKey"]["name"] == "X-Vassil-API-Key"
    assert schemes["StudioSession"]["name"] == "test_session"
    assert schemes["BearerKey"]["scheme"] == "bearer"
    for path, method, media in (
        ("/api/v1/tts/synthesize", "post", "audio/wav"),
        ("/api/v1/tts/jobs/{job_id}/audio", "get", "audio/wav"),
        ("/api/v1/asr/jobs/{job_id}/audio", "get", "audio/wav"),
        ("/api/v1/voices/{voice_id}/reference-audio", "get", "audio/wav"),
        ("/diagnostics/bundle", "get", "application/zip"),
    ):
        operation = schema["paths"][path][method]
        assert operation["security"]
        assert set(operation["responses"]["200"]["content"]) == {media}
        assert operation["responses"]["200"]["content"][media]["schema"]["format"] == "binary"
        assert "X-Request-ID" in operation["responses"]["200"]["headers"]


def test_model_management_scope_does_not_require_tts_write(tmp_path):
    app = make_app(security(tmp_path))
    events = []
    app.state.container.tts = SimpleNamespace(
        unload=lambda model_id: events.append(model_id),
        model_catalog=lambda: {"default_models": {}, "models": []},
    )
    app.include_router(tts_router, prefix="/api/v1/tts", dependencies=[Depends(require_domain_scope("tts"))])
    _, key = issue(app.state.container.auth, "operator", ["models:manage"])
    response = TestClient(app).post("/api/v1/tts/models/demo/unload", headers={"X-Vassil-API-Key": key["token"]})
    assert response.status_code == 200 and events == ["demo"]


def test_key_login_cookie_has_role_and_live_revocation_without_storing_raw_key(tmp_path):
    settings = security(tmp_path)
    app = make_app(settings)
    account, key = issue(app.state.container.auth, "reviewer")
    client = TestClient(app)
    response = client.post("/api/v1/auth/key-login", json={"api_key": key["token"]})
    assert response.status_code == 200
    assert "httponly" in response.headers["set-cookie"].lower()
    assert key["token"] not in response.headers["set-cookie"]
    assert client.get("/api/v1/auth/status").json()["authenticated"]
    assert client.get("/api/v1/auth/me").json()["role"] == "reviewer"
    assert client.get("/api/v1/auth/principal").json()["principal_id"] == account["principal_id"]
    assert client.post("/approve").status_code == 200
    assert client.post("/produce").status_code == 403
    # Cookie survives API recreation but remains bound to the key's current state.
    app.state.container.auth = LocalAuthService(settings)
    assert client.post("/approve").status_code == 200
    app.state.container.auth.revoke_api_key(key["key"]["key_id"])
    assert client.post("/approve").status_code == 401
    assert not client.get("/api/v1/auth/status").json()["authenticated"]
    assert key["token"].encode() not in settings.auth_db_path.read_bytes()


def test_key_session_logout_and_account_disable_invalidate_sessions(tmp_path):
    app = make_app(security(tmp_path))
    account, key = issue(app.state.container.auth, "editor")
    client = TestClient(app)
    assert client.post("/api/v1/auth/key-login", json={"api_key": "bad"}).status_code == 401
    assert client.post("/api/v1/auth/key-login", json={"api_key": key["token"]}).status_code == 200
    saved_cookie = client.cookies.get("test_session")
    assert client.post("/api/v1/auth/logout").status_code == 200
    client.cookies.set("test_session", saved_cookie)
    assert client.post("/produce").status_code == 401
    client.cookies.clear()
    client.post("/api/v1/auth/key-login", json={"api_key": key["token"]})
    app.state.container.auth.disable_service_account(account["principal_id"])
    assert client.post("/produce").status_code == 401
