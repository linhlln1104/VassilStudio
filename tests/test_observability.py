import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from vvoice.core.observability import REQUEST_ID_HEADER, configure_logging
from vvoice.main import register_request_middleware
from vvoice.shared.security.headers import (
    API_DOCS_CONTENT_SECURITY_POLICY,
    APPLICATION_CONTENT_SECURITY_POLICY,
)


def test_request_id_middleware_echoes_valid_request_id() -> None:
    app = FastAPI()
    register_request_middleware(app)

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    response = TestClient(app).get("/ping", headers={REQUEST_ID_HEADER: "req-123"})

    assert response.status_code == 200
    assert response.headers[REQUEST_ID_HEADER] == "req-123"


def test_request_id_middleware_generates_request_id() -> None:
    app = FastAPI()
    register_request_middleware(app)

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    response = TestClient(app).get("/ping")

    assert response.status_code == 200
    assert len(response.headers[REQUEST_ID_HEADER]) == 32


def test_request_middleware_sets_restrictive_browser_security_headers() -> None:
    app = FastAPI()
    register_request_middleware(app)

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    response = TestClient(app).get("/ping")

    content_security_policy = response.headers["content-security-policy"]
    assert content_security_policy == APPLICATION_CONTENT_SECURITY_POLICY.replace(
        "connect-src 'self'",
        "connect-src 'self' ws://testserver",
    )
    assert "script-src 'self'" in content_security_policy
    assert "script-src-attr 'none'" in content_security_policy
    assert "connect-src 'self' ws://testserver" in content_security_policy
    assert " ws: " not in content_security_policy
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-dns-prefetch-control"] == "off"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["cross-origin-opener-policy"] == "same-origin"
    assert response.headers["cross-origin-resource-policy"] == "same-origin"
    assert response.headers["origin-agent-cluster"] == "?1"
    assert response.headers["permissions-policy"].startswith("microphone=(self)")
    assert "strict-transport-security" not in response.headers


def test_request_middleware_uses_scoped_api_docs_policy() -> None:
    app = FastAPI()
    register_request_middleware(app)
    client = TestClient(app)

    docs_response = client.get("/docs")
    redoc_response = client.get("/redoc")

    assert docs_response.headers["content-security-policy"] == API_DOCS_CONTENT_SECURITY_POLICY
    assert redoc_response.headers["content-security-policy"] == API_DOCS_CONTENT_SECURITY_POLICY
    assert "https://cdn.jsdelivr.net" in docs_response.headers["content-security-policy"]
    assert docs_response.headers["x-frame-options"] == "DENY"


def test_request_middleware_disables_auth_caching_and_enables_https_hsts() -> None:
    app = FastAPI()
    register_request_middleware(app)

    @app.get("/api/v1/auth/status")
    async def auth_status():
        return {"authenticated": False}

    response = TestClient(app, base_url="https://testserver").get("/api/v1/auth/status")

    assert response.headers["cache-control"] == "no-store"
    assert "connect-src 'self' wss://testserver" in response.headers["content-security-policy"]
    assert response.headers["strict-transport-security"] == (
        "max-age=31536000; includeSubDomains"
    )


def test_configure_logging_honors_explicit_log_level() -> None:
    logger = logging.getLogger("vvoice")
    access_logger = logging.getLogger("uvicorn.access")
    previous_level = logger.level
    previous_access_disabled = access_logger.disabled
    try:
        access_logger.disabled = False
        configure_logging(log_level="ERROR")
        assert logger.level == logging.ERROR
        assert access_logger.disabled is True
    finally:
        logger.setLevel(previous_level)
        access_logger.disabled = previous_access_disabled
