"""Exercise the assembled HTTP application and startup configuration."""

import pytest
from app.core.config import Settings
from app.main import create_app
from fastapi.testclient import TestClient
from pydantic import ValidationError


def test_liveness_and_openapi_are_served() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/health/live")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        assert "/health/live" in client.get("/openapi.json").json()["paths"]


@pytest.mark.parametrize("origin,allowed", [("http://127.0.0.1:5173", True), ("https://untrusted.example", False)])
def test_cors_preflight_only_allows_configured_origins(origin: str, allowed: bool) -> None:
    with TestClient(create_app()) as client:
        response = client.options(
            "/health/live",
            headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
        )
        if allowed:
            assert response.status_code == 200
            assert response.headers["access-control-allow-origin"] == origin
        else:
            assert response.status_code == 400
            assert "access-control-allow-origin" not in response.headers


def test_invalid_environment_stops_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENTERPRISE_RAG_ENVIRONMENT", "unknown")
    with pytest.raises(ValidationError):
        create_app()


def test_wildcard_cors_configuration_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENTERPRISE_RAG_CORS_ORIGINS", '["*"]')
    with pytest.raises(ValidationError, match="CORS requires explicit origins"):
        Settings()
