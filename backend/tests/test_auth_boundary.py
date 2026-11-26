"""Unconfigured authentication stays unavailable and rejects forged browser origins."""

from app.core.config import Settings
from app.main import create_app
from fastapi.testclient import TestClient


def test_disabled_source_has_explicit_configuration_and_never_accepts_a_login() -> None:
    with TestClient(create_app(Settings(local_identity_config_ref=None))) as client:
        assert client.get("/api/v1/auth/chat/config").json() == {"mode": "unavailable"}
        response = client.post(
            "/api/v1/auth/chat/login",
            headers={"Origin": "http://127.0.0.1:5173"},
            json={"username": "account", "password": "private-password"},
        )
        assert response.status_code == 503
        assert "private-password" not in response.text
        assert client.get("/api/v1/auth/chat/me").status_code == 503
        assert client.get("/api/v1/auth/not-an-app/config").status_code == 422


def test_csrf_boundary_rejects_missing_foreign_and_cross_application_origins() -> None:
    with TestClient(create_app(Settings(local_identity_config_ref=None))) as client:
        for headers in (
            {},
            {"Origin": "http://127.0.0.1:5174"},
            {"Origin": "https://untrusted.example"},
            {"Origin": "http://127.0.0.1:5173", "Sec-Fetch-Site": "cross-site"},
        ):
            assert (
                client.post(
                    "/api/v1/auth/chat/login",
                    headers=headers,
                    json={"username": "account", "password": "private-password"},
                ).status_code
                == 403
            )
