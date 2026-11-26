"""Real broker/database measurements and authenticated Phoenix ingestion in the isolated test stack."""

import asyncio
import json
import logging
import os
import secrets
from datetime import UTC, datetime, timedelta
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import aio_pika
import httpx2
import pytest
from app.adapters.infrastructure import InfrastructureMonitor
from app.adapters.postgres import postgres_conninfo
from app.adapters.telemetry import JsonMetricExporter, OpenTelemetry
from app.core.config import Settings
from app.core.logging import StructuredFormatter
from app.main import create_app
from fastapi.testclient import TestClient
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from psycopg import AsyncConnection

from scripts.infrastructure import compose, up


def export_count(reader: InMemoryMetricReader, name: str) -> int:
    data = reader.get_metrics_data()
    assert data is not None
    return sum(
        int(point["value"])
        for resource in json.loads(data.to_json())["resource_metrics"]
        for scope in resource["scope_metrics"]
        for metric in scope["metrics"]
        if metric["name"] == name
        for point in metric["data"]["data_points"]
    )


async def verify_observability(settings: Settings) -> None:
    assert settings.environment == "test"
    assert settings.phoenix_url.host in {"127.0.0.1", "localhost"} and settings.phoenix_url.port == 26006
    assert (
        settings.telemetry_otlp_endpoint.host in {"127.0.0.1", "localhost"}
        and settings.telemetry_otlp_endpoint.port == 24317
    )
    queue_name, missing_name = "p1-observed-" + uuid4().hex, "p1-missing-" + uuid4().hex
    configured = settings.model_copy(update={"telemetry_queues": [queue_name, missing_name]})
    metrics = InMemoryMetricReader()
    telemetry = OpenTelemetry(configured, metric_reader=metrics)
    monitor = InfrastructureMonitor(configured, telemetry)
    log_output = StringIO()
    handler = logging.StreamHandler(log_output)
    handler.setFormatter(StructuredFormatter())
    logger = logging.getLogger("app")
    old_level = logger.level
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    broker = await aio_pika.connect(
        host=settings.rabbitmq_host,
        port=settings.rabbitmq_port,
        login=settings.rabbitmq_user,
        password=settings.rabbitmq_password.get_secret_value(),
    )
    try:
        async with broker:
            channel = await broker.channel()
            queue = await channel.declare_queue(queue_name, durable=True)
            for _ in range(2):
                await channel.default_exchange.publish(
                    aio_pika.Message(body=b"private-message-body"), routing_key=queue_name
                )
            telemetry.start()
            await monitor.start()
            async with await AsyncConnection.connect(postgres_conninfo(settings)):
                await monitor.sample_metrics()
                assert await monitor.count_postgres_connections() >= 1
            assert await monitor.count_queue_messages(queue_name) == 2
            with pytest.raises(aio_pika.exceptions.ChannelNotFoundEntity):
                await monitor.count_queue_messages(missing_name)
            data = metrics.get_metrics_data()
            assert data is not None
            rendered = json.loads(data.to_json())
            series = {
                metric["name"]: metric["data"]["data_points"]
                for resource in rendered["resource_metrics"]
                for scope in resource["scope_metrics"]
                for metric in scope["metrics"]
            }
            assert all(point["value"] == 1 for point in series["dependency.available"])
            assert series["messaging.queue.ready"][0]["value"] == 2
            availability = {
                point["attributes"]["queue"]: point["value"] for point in series["messaging.observation.available"]
            }
            assert availability == {queue_name: 1, missing_name: 0}
            assert JsonMetricExporter().export(data).name == "SUCCESS"
            assert "private-message-body" not in log_output.getvalue()
            await queue.delete(if_empty=False, if_unused=False)
            await monitor.close()
            await telemetry.close()

        async with httpx2.AsyncClient(
            base_url=str(settings.phoenix_url).rstrip("/"), trust_env=False, timeout=5
        ) as phoenix:
            # This runs only on the disposable test database: rotate the vendor's mandatory initial password.
            login = await phoenix.post("/auth/login", json={"email": "admin@localhost", "password": "admin"})
            assert login.status_code == 403
            reset_token = login.json()["password_reset_token"]
            password = secrets.token_urlsafe(48)
            reset = await phoenix.post("/auth/password-reset", json={"token": reset_token, "password": password})
            assert reset.status_code == 204
            login = await phoenix.post("/auth/login", json={"email": "admin@localhost", "password": password})
            assert login.status_code == 204
            phoenix.headers["Authorization"] = "Bearer " + login.cookies["phoenix-access-token"]
            key_response = await phoenix.post(
                "/v1/system/api_keys",
                json={
                    "data": {
                        "name": "p1-07-isolated-test",
                        "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                    }
                },
            )
            assert key_response.status_code == 201
            key = key_response.json()["data"]["key"]
            key_id = key_response.json()["data"]["id"]
            with TemporaryDirectory() as directory:
                reference = Path(directory) / "collector.json"
                descriptor = os.open(reference, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(descriptor, "w") as output:
                    json.dump({"bearer_token": key}, output)
                exported_settings = settings.model_copy(
                    update={"telemetry_trace_export_enabled": True, "telemetry_credentials_ref": reference}
                )
                active_metrics = InMemoryMetricReader()
                exported = OpenTelemetry(exported_settings, metric_reader=active_metrics)
                with TestClient(create_app(exported_settings, telemetry=exported)) as client:
                    response = client.get("/health/ready", headers={"Authorization": "Bearer private-request-token"})
                    assert response.status_code == 200
                    assert exported.traces is not None
                    assert await asyncio.to_thread(exported.traces.force_flush, timeout_millis=4000)
                    trace_id = response.headers["X-Trace-ID"]
                    received: list[dict[str, object]] = []
                    for _ in range(40):
                        query = await phoenix.get(
                            "/v1/projects/enterprise-rag-api/spans", params={"trace_id": trace_id}
                        )
                        if query.status_code == 200:
                            received = query.json()["data"]
                            if len(received) >= 8:
                                break
                        await asyncio.sleep(0.25)
                    assert len(received) >= 8
                    serialized = json.dumps(received)
                    assert response.headers["X-Request-ID"] in serialized
                    assert "GET /health/ready" in serialized and "postgres.transaction" in serialized
                    assert export_count(active_metrics, "telemetry.spans.exported") >= 8

                    # The same API process must survive a collector outage and resume exporting.
                    await asyncio.to_thread(compose, "test", "stop", "phoenix")
                    try:
                        failures = export_count(active_metrics, "telemetry.export.failures")
                        assert client.get("/health/live").status_code == 200
                        assert await asyncio.to_thread(exported.traces.force_flush, timeout_millis=4000)
                        assert export_count(active_metrics, "telemetry.export.failures") > failures
                    finally:
                        await asyncio.to_thread(up, "test")
                    recovered = client.get("/health/ready")
                    assert recovered.status_code == 200
                    assert await asyncio.to_thread(exported.traces.force_flush, timeout_millis=4000)
                    query = None
                    for _ in range(40):
                        query = await phoenix.get(
                            "/v1/projects/enterprise-rag-api/spans",
                            params={"trace_id": recovered.headers["X-Trace-ID"]},
                        )
                        if query.status_code == 200 and len(query.json()["data"]) >= 8:
                            break
                        await asyncio.sleep(0.25)
                    assert query is not None and query.status_code == 200 and len(query.json()["data"]) >= 8, {
                        "received": len(query.json()["data"])
                        if query is not None and query.status_code == 200
                        else None,
                        "exported": export_count(active_metrics, "telemetry.spans.exported"),
                        "failures": export_count(active_metrics, "telemetry.export.failures"),
                    }

                    # Revoke while the exporter still holds its established gRPC channel.
                    revoked = await phoenix.delete(f"/v1/system/api_keys/{key_id}")
                    assert revoked.status_code == 204
                    failures = export_count(active_metrics, "telemetry.export.failures")
                    rejected = client.get("/health/live")
                    assert rejected.status_code == 200
                    assert await asyncio.to_thread(exported.traces.force_flush, timeout_millis=4000)
                    assert export_count(active_metrics, "telemetry.export.failures") > failures
                    query = await phoenix.get(
                        "/v1/projects/enterprise-rag-api/spans",
                        params={"trace_id": rejected.headers["X-Trace-ID"]},
                    )
                    assert query.status_code == 200 and query.json()["data"] == []
                    serialized += json.dumps(query.json())
                    for secret in (
                        key,
                        password,
                        reset_token,
                        settings.postgres_password.get_secret_value(),
                        "private-request-token",
                    ):
                        assert secret not in serialized + log_output.getvalue()
                failed_metrics = InMemoryMetricReader()
                refused = OpenTelemetry(exported_settings, metric_reader=failed_metrics)
                with TestClient(create_app(exported_settings, telemetry=refused)) as client:
                    response = client.get("/health/live")
                    assert response.status_code == 200
                    assert refused.traces is not None
                    assert await asyncio.to_thread(refused.traces.force_flush, timeout_millis=4000)
                    missing = await phoenix.get(
                        "/v1/projects/enterprise-rag-api/spans", params={"trace_id": response.headers["X-Trace-ID"]}
                    )
                    assert missing.status_code == 200 and missing.json()["data"] == []
                    assert export_count(failed_metrics, "telemetry.export.failures") >= 1
                    assert export_count(failed_metrics, "telemetry.spans.exported") == 0
                    assert "telemetry_export_failed" in log_output.getvalue()
    finally:
        await monitor.close()
        await telemetry.close()
        logger.removeHandler(handler)
        logger.setLevel(old_level)
