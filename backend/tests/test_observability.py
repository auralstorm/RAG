"""Observe real ASGI paths without collecting request bodies, identities or high-cardinality IDs."""

import asyncio
import json
import logging
import os
from collections.abc import Iterator
from io import StringIO
from pathlib import Path
from uuid import uuid4

import httpx2
import pytest
from app.adapters.telemetry import JsonMetricExporter, OpenTelemetry
from app.adapters.telemetry_credentials import read_collector_credentials
from app.api.middleware.request_context import RequestContextMiddleware
from app.core.config import Settings
from app.core.logging import StructuredFormatter
from app.core.observability import current_request, current_telemetry, observe_operation
from app.main import create_app
from fastapi import HTTPException
from fastapi.testclient import TestClient
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic import SecretStr, ValidationError
from starlette.types import Message, Receive, Scope, Send

from scripts import collector_credentials


@pytest.fixture
def logs() -> Iterator[StringIO]:
    output = StringIO()
    handler = logging.StreamHandler(output)
    handler.setFormatter(StructuredFormatter())
    logger = logging.getLogger("app")
    level = logger.level
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    try:
        yield output
    finally:
        logger.removeHandler(handler)
        logger.setLevel(level)


def observer() -> tuple[OpenTelemetry, InMemorySpanExporter, InMemoryMetricReader]:
    spans, metrics = InMemorySpanExporter(), InMemoryMetricReader()
    return (
        OpenTelemetry(Settings(infrastructure_enabled=False), span_exporter=spans, metric_reader=metrics),
        spans,
        metrics,
    )


def test_trace_logs_headers_and_metrics_share_only_technical_facts(
    logs: StringIO, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OTEL_RESOURCE_ATTRIBUTES", "private.subject=private-environment-identity")
    telemetry, spans, metrics = observer()
    application = create_app(Settings(infrastructure_enabled=False), telemetry=telemetry)

    @application.post("/api/v1/observe/{object_id}")
    async def observed(object_id: str, payload: dict[str, str]) -> dict[str, bool]:
        with observe_operation("test.operation"):
            logging.getLogger("app.test").warning("raw-private-password %s", payload["password"])
        return {"ok": bool(object_id)}

    object_id = str(uuid4())
    parent = "00-" + "a" * 32 + "-" + "b" * 16 + "-01"
    with TestClient(application) as client:
        response = client.post(
            f"/api/v1/observe/{object_id}?query=private-query",
            headers={"traceparent": parent, "Authorization": "Bearer private-token", "Cookie": "private-cookie"},
            json={"password": "private-password-value"},
        )
        assert response.status_code == 200
        data = metrics.get_metrics_data()
        assert data is not None
        exported = data.to_json()
        assert "http.server.requests" in exported and "http.server.duration" in exported
        assert "http.server.active_requests" in exported
        assert object_id not in exported and "request.id" not in exported
        assert '"value": 0' in exported
        assert JsonMetricExporter().export(data).name == "SUCCESS"
    recorded = [json.loads(line) for line in logs.getvalue().splitlines()]
    completion = next(record for record in recorded if record["event"] == "http_request_completed")
    assert completion["request_id"] == response.headers["X-Request-ID"]
    assert completion["trace_id"] == response.headers["X-Trace-ID"] == "a" * 32
    assert completion["span_id"] == response.headers["traceparent"].split("-")[2]
    assert completion["route"] == "/api/v1/observe/{object_id}" and completion["status"] == 200
    assert completion["duration_seconds"] >= 0
    exported_spans = spans.get_finished_spans()
    server = next(span for span in exported_spans if span.name.startswith("POST "))
    child = next(span for span in exported_spans if span.name == "test.operation")
    assert server.parent is not None and server.parent.span_id == int("b" * 16, 16)
    assert server.context is not None and child.context is not None and child.parent is not None
    assert child.context.trace_id == server.context.trace_id == int("a" * 32, 16)
    assert child.parent.span_id == server.context.span_id
    assert "private.subject" not in server.resource.attributes
    rendered = logs.getvalue() + str(exported_spans) + exported
    for private in (
        object_id,
        "private-password-value",
        "private-token",
        "private-cookie",
        "private-query",
        "raw-private-password",
    ):
        assert private not in rendered


def test_cors_denials_unknown_paths_and_http_errors_are_observed(logs: StringIO) -> None:
    telemetry, spans, metrics = observer()
    application = create_app(Settings(infrastructure_enabled=False), telemetry=telemetry)

    @application.get("/api/v1/observed-denial")
    async def denied() -> None:
        raise HTTPException(403, "private-denial-reason")

    @application.get("/api/v1/observed-error")
    async def failed() -> None:
        raise RuntimeError("private-error-stack")

    with TestClient(application) as client:
        for response, status in (
            (
                client.options(
                    "/health/live",
                    headers={"Origin": "https://foreign.example", "Access-Control-Request-Method": "GET"},
                ),
                400,
            ),
            (client.get("/api/v1/private-missing-id"), 404),
            (client.get("/api/v1/observed-denial"), 403),
            (client.get("/api/v1/observed-error", headers={"Origin": "http://127.0.0.1:5173"}), 500),
        ):
            assert response.status_code == status
            assert response.headers["X-Request-ID"] and response.headers["X-Trace-ID"]
        assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
        data = metrics.get_metrics_data()
        assert data is not None
    completions = [
        json.loads(line)
        for line in logs.getvalue().splitlines()
        if json.loads(line)["event"] == "http_request_completed"
    ]
    assert sorted(record["status"] for record in completions) == [400, 403, 404, 500]
    assert len({record["request_id"] for record in completions}) == 4
    assert all(not span.events for span in spans.get_finished_spans())
    assert "private-" not in logs.getvalue() + data.to_json() + str(spans.get_finished_spans())


@pytest.mark.anyio
async def test_parallel_requests_and_child_logs_never_share_request_identity(logs: StringIO) -> None:
    telemetry, spans, _metrics = observer()
    telemetry.start()
    application = create_app(Settings(infrastructure_enabled=False), telemetry=telemetry)

    @application.get("/api/v1/parallel")
    async def parallel() -> dict[str, bool]:
        await asyncio.sleep(0.01)
        with observe_operation("test.parallel_child"):
            logging.getLogger("app.test").info("private-log-message")
        return {"ok": True}

    try:
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(application), base_url="http://testserver", trust_env=False
        ) as client:
            responses = await asyncio.gather(
                *(
                    client.get("/api/v1/parallel", headers={"traceparent": f"00-{number:032x}-{'b' * 16}-01"})
                    for number in range(1, 9)
                )
            )
        records = [json.loads(line) for line in logs.getvalue().splitlines()]
        assert len({response.headers["X-Request-ID"] for response in responses}) == 8
        for response in responses:
            request_records = [
                record for record in records if record.get("request_id") == response.headers["X-Request-ID"]
            ]
            assert len(request_records) == 2
            assert {record["trace_id"] for record in request_records} == {response.headers["X-Trace-ID"]}
        assert len(spans.get_finished_spans()) == 16
        assert current_request.get() is None and current_telemetry.get() is None
    finally:
        await telemetry.close()


@pytest.mark.anyio
@pytest.mark.parametrize("cancelled", [False, True])
async def test_aborted_or_cancelled_stream_keeps_wire_status_and_is_counted(logs: StringIO, cancelled: bool) -> None:
    telemetry, spans, metrics = observer()
    telemetry.start()
    sent: list[Message] = []

    async def stream(_scope: Scope, _receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"data: first\n\n", "more_body": True})
        if cancelled:
            raise asyncio.CancelledError
        raise RuntimeError("private-stream-failure")

    async def receive() -> Message:
        return {"type": "http.request", "body": b""}

    async def send(message: Message) -> None:
        sent.append(message)

    try:
        with pytest.raises(asyncio.CancelledError if cancelled else RuntimeError):
            await RequestContextMiddleware(stream, telemetry)(
                {"type": "http", "headers": [], "method": "GET"}, receive, send
            )
        data = metrics.get_metrics_data()
        assert data is not None
        assert len(sent) == 2 and sent[0]["status"] == 200
        rendered = data.to_json() + logs.getvalue() + str(spans.get_finished_spans())
        assert ('"cancelled"' if cancelled else '"aborted"') in rendered
        assert "private-stream-failure" not in rendered
        assert len(spans.get_finished_spans()) == 1
        assert current_request.get() is None
    finally:
        await telemetry.close()


@pytest.mark.anyio
async def test_missing_sources_are_unavailable_gauges_and_not_zero_counts() -> None:
    telemetry, _spans, metrics = observer()
    telemetry.start()
    try:
        telemetry.postgres_connections(3)
        telemetry.queue_messages("configured-queue", 5)
        present = metrics.get_metrics_data()
        assert present is not None and "db.server.connections" in present.to_json()
        telemetry.postgres_connections(None)
        telemetry.queue_messages("configured-queue", None)
        missing = metrics.get_metrics_data()
        assert missing is not None
        exported = missing.to_json()
        assert "db.server.connections" not in exported and "messaging.queue.ready" not in exported
        assert "db.observation.available" in exported and "messaging.observation.available" in exported
    finally:
        await telemetry.close()


@pytest.mark.parametrize(
    "endpoint",
    ["http://user:private@localhost:4317", "http://localhost:4317?token=private", "http://localhost:4317/path"],
)
def test_otlp_endpoint_does_not_embed_credentials_or_request_data(endpoint: str) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({"telemetry_otlp_endpoint": endpoint})


def test_formatter_never_formats_raw_messages_arguments_or_exception_stacks() -> None:
    record = logging.LogRecord(
        "uvicorn.error", logging.ERROR, "server.py", 1, "private-url %s", ("private-token",), None
    )
    record.exc_text = "private-error-stack"
    record.request_id = "client-spoofed-id"
    record.password = "private-password"
    assert "private" not in StructuredFormatter().format(record)
    assert "client-spoofed" not in StructuredFormatter().format(record)


def test_private_collector_reference_rejects_shared_symlink_and_malformed_files(tmp_path: Path) -> None:
    reference = tmp_path / "collector.json"
    reference.write_text(json.dumps({"bearer_token": "private-test-token"}))
    os.chmod(reference, 0o600)
    assert read_collector_credentials(reference).bearer_token.get_secret_value() == "private-test-token"
    os.chmod(reference, 0o644)
    with pytest.raises(ValueError, match="unavailable"):
        read_collector_credentials(reference)
    os.chmod(reference, 0o600)
    link = tmp_path / "linked.json"
    link.symlink_to(reference)
    with pytest.raises(ValueError, match="unavailable"):
        read_collector_credentials(link)
    for content in (
        '{"bearer_token":"private-test-token","password":"private"}',
        '{"bearer_token":"private\\nvalue"}',
        "private-invalid-json",
        "x" * 16385,
    ):
        reference.write_text(content)
        with pytest.raises(ValueError) as failed:
            read_collector_credentials(reference)
        assert "private" not in str(failed.value)
    pipe = tmp_path / "pipe"
    os.mkfifo(pipe, 0o600)
    with pytest.raises(ValueError, match="unavailable"):
        read_collector_credentials(pipe)


def test_collector_provisioning_never_overwrites_or_writes_tracked_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(collector_credentials, "ROOT", tmp_path)
    reference = tmp_path / ".poc-results/observability/collector.json"
    collector_credentials.write_credentials(reference, SecretStr("private-service-token"))
    assert reference.stat().st_mode & 0o077 == 0
    with pytest.raises(FileExistsError):
        collector_credentials.write_credentials(reference, SecretStr("another-token"))
    assert read_collector_credentials(reference).bearer_token.get_secret_value() == "private-service-token"
    with pytest.raises(ValueError):
        collector_credentials.write_credentials(tmp_path / "tracked.json", SecretStr("private-service-token"))


def test_export_cannot_be_enabled_without_a_credential_reference() -> None:
    with pytest.raises(ValidationError):
        Settings(telemetry_trace_export_enabled=True)
