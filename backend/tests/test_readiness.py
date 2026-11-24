import asyncio

import pytest
from app.core.config import Settings
from app.core.readiness import check_dependencies
from app.main import create_app
from fastapi.testclient import TestClient


async def available() -> None:
    return None


async def unavailable() -> None:
    raise RuntimeError("private-password-and-connection-details")


@pytest.mark.anyio
async def test_reports_unavailable_dependency_without_exposing_diagnostics() -> None:
    report = await check_dependencies({"postgres": available, "redis": unavailable}, timeout=0.1)
    assert report.status == "not_ready"
    assert report.dependencies == {"postgres": True, "redis": False}
    assert "private-password" not in report.model_dump_json()


@pytest.mark.anyio
async def test_readiness_probes_have_bounded_timeouts() -> None:
    async def slow() -> None:
        await asyncio.sleep(10)

    report = await check_dependencies({"postgres": available, "redis": slow}, timeout=0.01)
    assert report.dependencies == {"postgres": True, "redis": False}


@pytest.mark.anyio
async def test_caller_cancellation_is_not_hidden_as_a_dependency_failure() -> None:
    async def cancelled() -> None:
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await check_dependencies({"redis": cancelled}, timeout=0.1)


def test_unconfigured_api_is_live_but_not_ready() -> None:
    with TestClient(create_app(Settings(infrastructure_enabled=False))) as client:
        assert client.get("/health/live").status_code == 200
        response = client.get("/health/ready")
        assert response.status_code == 503
        assert response.json() == {"status": "not_ready", "dependencies": {"configuration": False}}
