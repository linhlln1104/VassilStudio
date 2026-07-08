from types import SimpleNamespace

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from vvoice.app.auth.router import router as auth_router
from vvoice.app.auth.service import LocalAuthService
from vvoice.core.config import SecuritySettings
from vvoice.shared.security.auth import _candidate_from_mapping, _matches
from vvoice.shared.security.auth import require_api_key


def test_auth_accepts_api_key_header() -> None:
    candidate = _candidate_from_mapping({"X-Vassil-API-Key": "secret"}, {})

    assert candidate == "secret"
    assert _matches(candidate, ["secret"])


def test_auth_accepts_legacy_api_key_header() -> None:
    candidate = _candidate_from_mapping({"X-VVoice-API-Key": "secret"}, {})

    assert candidate == "secret"
    assert _matches(candidate, ["secret"])


def test_auth_accepts_bearer_header() -> None:
    candidate = _candidate_from_mapping({"Authorization": "Bearer secret"}, {})

    assert candidate == "secret"
    assert _matches(candidate, ["secret"])


def test_auth_accepts_query_key_for_websocket() -> None:
    candidate = _candidate_from_mapping({}, {"api_key": "secret"})

    assert candidate == "secret"
    assert _matches(candidate, ["secret"])


def test_auth_rejects_missing_or_wrong_key() -> None:
    assert _candidate_from_mapping({}, {}) is None
    assert not _matches(None, ["secret"])
    assert not _matches("wrong", ["secret"])


def test_local_auth_setup_login_logout_and_session_protection(tmp_path) -> None:
    settings = make_security_settings(tmp_path, auth_required=True)
    app = make_auth_app(settings)
    client = TestClient(app)

    status_response = client.get("/api/v1/auth/status")
    assert status_response.status_code == 200
    assert status_response.json()["setup_required"] is True

    blocked_response = client.get("/protected")
    assert blocked_response.status_code == 401

    setup_response = client.post(
        "/api/v1/auth/setup",
        json={"username": "Owner@Local", "password": "correct horse battery"},
    )
    assert setup_response.status_code == 201
    assert setup_response.json()["user"]["username"] == "owner@local"
    assert "httponly" in setup_response.headers["set-cookie"].lower()

    duplicate_setup_response = client.post(
        "/api/v1/auth/setup",
        json={"username": "second", "password": "correct horse battery"},
    )
    assert duplicate_setup_response.status_code == 409

    protected_response = client.get("/protected")
    assert protected_response.status_code == 200
    assert protected_response.json() == {"ok": True}

    logout_response = client.post("/api/v1/auth/logout")
    assert logout_response.status_code == 200
    assert logout_response.json() == {"logged_out": True}

    blocked_after_logout = client.get("/protected")
    assert blocked_after_logout.status_code == 401

    bad_login_response = client.post(
        "/api/v1/auth/login",
        json={"username": "owner@local", "password": "wrong password"},
    )
    assert bad_login_response.status_code == 401

    login_response = client.post(
        "/api/v1/auth/login",
        json={"username": "owner@local", "password": "correct horse battery"},
    )
    assert login_response.status_code == 200
    assert client.get("/api/v1/auth/me").json()["username"] == "owner@local"


def test_api_key_still_authorizes_when_local_auth_is_required(tmp_path) -> None:
    settings = make_security_settings(tmp_path, auth_required=True, api_keys=("api-secret",))
    app = make_auth_app(settings)
    client = TestClient(app)

    response = client.get("/protected", headers={"X-Vassil-API-Key": "api-secret"})

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_local_auth_is_disabled_by_default_for_unprotected_local_runs(tmp_path) -> None:
    settings = make_security_settings(tmp_path, auth_required=False)
    app = make_auth_app(settings)
    client = TestClient(app)

    status_response = client.get("/api/v1/auth/status")
    protected_response = client.get("/protected")
    setup_response = client.post(
        "/api/v1/auth/setup",
        json={"username": "owner", "password": "correct horse battery"},
    )

    assert status_response.json()["auth_required"] is False
    assert protected_response.status_code == 200
    assert setup_response.status_code == 409


def make_security_settings(
    tmp_path,
    *,
    auth_required: bool,
    api_keys: tuple[str, ...] = (),
) -> SecuritySettings:
    return SecuritySettings(
        api_keys=api_keys,
        auth_required=auth_required,
        auth_db_path=tmp_path / "auth.sqlite3",
        session_cookie_name="vassil_session",
        session_ttl_seconds=3600,
        session_secret="test-session-secret",
        secure_cookies=False,
    )


def make_auth_app(settings: SecuritySettings) -> FastAPI:
    app = FastAPI()
    app.state.container = SimpleNamespace(
        settings=SimpleNamespace(security=settings),
        auth=LocalAuthService(settings),
    )
    app.include_router(auth_router, prefix="/api/v1/auth")

    @app.get("/protected", dependencies=[Depends(require_api_key)])
    async def protected_route():
        return {"ok": True}

    return app
