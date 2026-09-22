from __future__ import annotations

from pathlib import Path
import tempfile

try:
    from scripts._path import bootstrap_backend_path
    from scripts.isolated_workspace import isolated_environment
except ModuleNotFoundError:
    from _path import bootstrap_backend_path
    from isolated_workspace import isolated_environment

bootstrap_backend_path()

from fastapi.testclient import TestClient  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
USERNAME = "smoke-owner"
PASSWORD = "correct horse battery"
NEW_PASSWORD = "new correct horse battery"
API_KEY = "smoke-api-key"


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="vassil-auth-smoke-") as temp_dir:
        with isolated_environment(Path(temp_dir), {
            "VASSIL_AUTH_REQUIRED": "true",
            "VASSIL_SESSION_SECRET": "smoke-session-secret-with-enough-entropy",
            "VASSIL_API_KEYS": API_KEY,
        }):
            from vvoice.main import create_app

            with TestClient(create_app()) as client:
                assert_product_shell(client)
                assert_first_run_redirect(client)
                setup_owner(client)
                assert_session_allows_studio_and_api(client)
                assert_logout_redirects_to_login(client)
                assert_login_restores_session(client)
                assert_change_password(client)
                assert_api_key_still_allows_automation(client)

    print(
        "Auth/product smoke passed: setup, login, password change, "
        "protected Studio, API key automation",
    )


def assert_product_shell(client: TestClient) -> None:
    response = client.get("/")
    response.raise_for_status()
    if "VassilStudio" not in response.text:
        raise RuntimeError("Product shell did not render VassilStudio")


def assert_first_run_redirect(client: TestClient) -> None:
    response = client.get("/studio", follow_redirects=False)
    if response.status_code != 303 or response.headers.get("location") != "/setup":
        raise RuntimeError(f"Expected /studio to redirect to /setup, got {response.status_code} {response.headers}")

    status_response = client.get("/api/v1/auth/status")
    status_response.raise_for_status()
    payload = status_response.json()
    if not payload["auth_required"] or not payload["setup_required"]:
        raise RuntimeError(f"Unexpected first-run auth status: {payload}")


def setup_owner(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/setup",
        json={"username": USERNAME, "password": PASSWORD},
    )
    response.raise_for_status()
    cookie = response.headers.get("set-cookie", "").lower()
    if "httponly" not in cookie:
        raise RuntimeError("Setup response did not set an HttpOnly session cookie")


def assert_session_allows_studio_and_api(client: TestClient) -> None:
    studio_response = client.get("/studio")
    studio_response.raise_for_status()
    if "VassilStudio" not in studio_response.text:
        raise RuntimeError("Authenticated Studio did not render")

    status_response = client.get("/model-status")
    status_response.raise_for_status()
    if "runtime" not in status_response.json():
        raise RuntimeError("Session-authenticated model-status response missing runtime")


def assert_logout_redirects_to_login(client: TestClient) -> None:
    response = client.post("/api/v1/auth/logout")
    response.raise_for_status()

    studio_response = client.get("/studio", follow_redirects=False)
    if studio_response.status_code != 303 or studio_response.headers.get("location") != "/login":
        raise RuntimeError(
            f"Expected /studio to redirect to /login after logout, got {studio_response.status_code}",
        )


def assert_login_restores_session(client: TestClient) -> None:
    bad_response = client.post(
        "/api/v1/auth/login",
        json={"username": USERNAME, "password": "wrong password"},
    )
    if bad_response.status_code != 401:
        raise RuntimeError(f"Expected bad login to fail with 401, got {bad_response.status_code}")

    response = client.post(
        "/api/v1/auth/login",
        json={"username": USERNAME, "password": PASSWORD},
    )
    response.raise_for_status()
    me_response = client.get("/api/v1/auth/me")
    me_response.raise_for_status()
    if me_response.json()["username"] != USERNAME:
        raise RuntimeError(f"Unexpected authenticated user: {me_response.json()}")


def assert_change_password(client: TestClient) -> None:
    bad_response = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "wrong password", "new_password": NEW_PASSWORD},
    )
    if bad_response.status_code != 400:
        raise RuntimeError(
            f"Expected bad password change to fail with 400, got {bad_response.status_code}",
        )

    response = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
    )
    response.raise_for_status()
    payload = response.json()
    if not payload["password_changed"]:
        raise RuntimeError(f"Unexpected password change payload: {payload}")

    me_response = client.get("/api/v1/auth/me")
    me_response.raise_for_status()

    logout_response = client.post("/api/v1/auth/logout")
    logout_response.raise_for_status()

    old_password_response = client.post(
        "/api/v1/auth/login",
        json={"username": USERNAME, "password": PASSWORD},
    )
    if old_password_response.status_code != 401:
        raise RuntimeError(
            f"Expected old password to fail with 401, got {old_password_response.status_code}",
        )

    new_password_response = client.post(
        "/api/v1/auth/login",
        json={"username": USERNAME, "password": NEW_PASSWORD},
    )
    new_password_response.raise_for_status()


def assert_api_key_still_allows_automation(client: TestClient) -> None:
    logout_response = client.post("/api/v1/auth/logout")
    logout_response.raise_for_status()

    response = client.get("/model-status", headers={"X-Vassil-API-Key": API_KEY})
    response.raise_for_status()
    if "runtime" not in response.json():
        raise RuntimeError("API-key model-status response missing runtime")


if __name__ == "__main__":
    main()
