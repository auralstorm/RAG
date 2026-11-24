"""Exercise public failures, correlation and pagination through the assembled HTTP app."""

from typing import Annotated
from uuid import UUID

import pytest
from app.api.middleware.request_context import RequestContextMiddleware
from app.api.schemas.common import PageResponse, PaginationQuery
from app.core.config import Settings
from app.main import create_app
from fastapi import HTTPException, Query
from fastapi.testclient import TestClient
from pydantic import BaseModel, JsonValue, ValidationError
from starlette.types import Message, Receive, Scope, Send


def test_missing_route_returns_correlated_public_error() -> None:
    with TestClient(create_app(Settings(infrastructure_enabled=False))) as client:
        response = client.get("/api/v1/missing", headers={"X-Request-ID": "untrusted-client-value"})
        assert response.status_code == 404
        error = response.json()["error"]
        assert error["code"] == "RESOURCE_NOT_FOUND"
        assert str(UUID(error["request_id"])) == response.headers["X-Request-ID"]
        assert error["retryable"] is False
        assert len(response.headers["X-Trace-ID"]) == 32
        second = client.get("/api/v1/missing")
        assert second.headers["X-Request-ID"] != response.headers["X-Request-ID"]


@pytest.mark.parametrize(
    "parent",
    ["invalid", "00-" + "0" * 32 + "-" + "1" * 16 + "-00", "00-" + "1" * 32 + "-" + "0" * 16 + "-01"],
)
def test_invalid_trace_context_is_replaced(parent: str) -> None:
    with TestClient(create_app(Settings(infrastructure_enabled=False))) as client:
        response = client.get("/health/live", headers={"traceparent": parent})
        assert response.status_code == 200
        fields = response.headers["traceparent"].split("-")
        assert fields[0] == "00" and int(fields[1], 16) != 0 and int(fields[2], 16) != 0
        assert response.headers["traceparent"] != parent


def test_valid_parent_trace_is_correlated_and_readable_by_allowed_browser() -> None:
    trace_id = "1234567890abcdef" * 2
    parent_span = "1234567890abcdef"
    with TestClient(create_app(Settings(infrastructure_enabled=False))) as client:
        response = client.get(
            "/health/live",
            headers={"traceparent": f"00-{trace_id}-{parent_span}-01", "Origin": "http://127.0.0.1:5173"},
        )
        assert response.headers["X-Trace-ID"] == trace_id
        assert response.headers["traceparent"].split("-")[2] != parent_span
        assert response.headers["traceparent"].endswith("-01")
        assert "X-Request-ID" in response.headers["access-control-expose-headers"]


def test_validation_errors_do_not_echo_rejected_values() -> None:
    application = create_app(Settings(infrastructure_enabled=False))

    class Input(BaseModel):
        count: int

    @application.post("/api/v1/test-input")
    async def receive_input(payload: Input) -> dict[str, int]:
        return {"count": payload.count}

    with TestClient(application) as client:
        response = client.post("/api/v1/test-input", json={"count": "synthetic-private-input"})
        assert response.status_code == 422
        assert response.json()["error"]["details"] == {"error_count": 1}
        assert response.json()["error"]["request_id"] == response.headers["X-Request-ID"]
        assert "synthetic-private-input" not in response.text


def test_http_failure_keeps_protocol_headers_and_hides_internal_detail() -> None:
    application = create_app(Settings(infrastructure_enabled=False))

    @application.get("/api/v1/test-auth")
    async def authentication_failure() -> None:
        raise HTTPException(401, detail="synthetic-private-diagnostic", headers={"WWW-Authenticate": "Bearer"})

    with TestClient(application) as client:
        response = client.get("/api/v1/test-auth")
        assert response.status_code == 401
        assert response.headers["WWW-Authenticate"] == "Bearer"
        assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"
        assert "synthetic-private-diagnostic" not in response.text


def test_unexpected_failure_is_safe_and_keeps_cors_and_correlation(caplog: pytest.LogCaptureFixture) -> None:
    application = create_app(Settings(infrastructure_enabled=False))

    @application.get("/api/v1/test-failure")
    async def unexpected_failure() -> None:
        raise RuntimeError("synthetic-private-exception")

    with TestClient(application) as client:
        response = client.get("/api/v1/test-failure", headers={"Origin": "http://127.0.0.1:5173"})
        assert response.status_code == 500
        assert response.json()["error"]["code"] == "INTERNAL_ERROR"
        assert response.json()["error"]["retryable"] is False
        assert response.json()["error"]["request_id"] == response.headers["X-Request-ID"]
        assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
        assert "synthetic-private-exception" not in response.text + caplog.text


def test_query_pagination_enforces_bounds_and_rejects_unknown_fields() -> None:
    application = create_app(Settings(infrastructure_enabled=False))

    @application.get("/api/v1/test-page")
    async def page(query: Annotated[PaginationQuery, Query()]) -> PaginationQuery:
        return query

    with TestClient(application) as client:
        assert client.get("/api/v1/test-page").json() == {"page": 1, "page_size": 20}
        assert client.get("/api/v1/test-page?page=2&page_size=100").json() == {"page": 2, "page_size": 100}
        for query in ("page=0", "page_size=101", "page_size=0", "page=abc", "unknown=1"):
            assert client.get(f"/api/v1/test-page?{query}").status_code == 422


@pytest.mark.parametrize("items,total,page_size", [([1, 2], 2, 1), ([1], 0, 20)])
def test_inconsistent_page_counts_are_rejected(items: list[JsonValue], total: int, page_size: int) -> None:
    with pytest.raises(ValidationError, match="Page item count"):
        PageResponse[JsonValue](items=items, total=total, page=1, page_size=page_size)
    assert PageResponse[JsonValue](items=[], total=0, page=9, page_size=20).items == []


@pytest.mark.anyio
async def test_stream_failure_does_not_replace_a_response_already_started() -> None:
    sent: list[Message] = []

    async def failing_stream(_scope: Scope, _receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"data: first\n\n", "more_body": True})
        raise RuntimeError("synthetic-stream-failure")

    async def receive() -> Message:
        return {"type": "http.request", "body": b""}

    async def send(message: Message) -> None:
        sent.append(message)

    with pytest.raises(RuntimeError, match="HTTP response stream aborted"):
        await RequestContextMiddleware(failing_stream)({"type": "http", "headers": []}, receive, send)
    assert [message["type"] for message in sent] == ["http.response.start", "http.response.body"]
    assert sent[0]["status"] == 200
