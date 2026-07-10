import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from vvoice.core.observability import REQUEST_ID_HEADER, configure_logging
from vvoice.main import register_request_middleware


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


def test_configure_logging_honors_explicit_log_level() -> None:
    logger = logging.getLogger("vvoice")
    previous_level = logger.level
    try:
        configure_logging(log_level="ERROR")
        assert logger.level == logging.ERROR
    finally:
        logger.setLevel(previous_level)
