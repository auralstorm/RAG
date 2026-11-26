"""Exercise collector acknowledgements across the actual local gRPC transport."""

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import grpc
import pytest
from app.adapters.telemetry import OpenTelemetry
from app.core.config import Settings
from app.core.request_context import create_request_context
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTracePartialSuccess,
    ExportTraceServiceRequest,
    ExportTraceServiceResponse,
)
from opentelemetry.sdk.metrics.export import InMemoryMetricReader, NumberDataPoint
from pydantic import AnyHttpUrl


@dataclass
class Collector:
    rejected: int = 0
    unavailable: bool = False
    requests: int = 0

    def export(self, request: ExportTraceServiceRequest, context: grpc.ServicerContext) -> ExportTraceServiceResponse:
        assert dict(context.invocation_metadata())["authorization"] == "Bearer private-token"
        assert 0 < context.time_remaining() <= 2.1
        self.requests += 1
        if self.unavailable:
            context.abort(grpc.StatusCode.UNAVAILABLE, "private-collector-error")
        return ExportTraceServiceResponse(
            partial_success=ExportTracePartialSuccess(rejected_spans=self.rejected, error_message="private-error")
        )


@pytest.fixture
def collector() -> Iterator[tuple[Collector, str]]:
    receiver = Collector()
    server = grpc.server(ThreadPoolExecutor(max_workers=1))
    handler = grpc.unary_unary_rpc_method_handler(
        receiver.export,
        request_deserializer=ExportTraceServiceRequest.FromString,
        response_serializer=ExportTraceServiceResponse.SerializeToString,
    )
    server.add_generic_rpc_handlers(
        (
            grpc.method_handlers_generic_handler(
                "opentelemetry.proto.collector.trace.v1.TraceService", {"Export": handler}
            ),
        )
    )
    port = server.add_insecure_port("127.0.0.1:0")
    server.start()
    try:
        yield receiver, f"http://127.0.0.1:{port}"
    finally:
        server.stop(0).wait()


def counts(reader: InMemoryMetricReader) -> dict[str, int]:
    data = reader.get_metrics_data()
    assert data is not None
    result = {
        metric.name: sum(int(point.value) for point in metric.data.data_points if isinstance(point, NumberDataPoint))
        for resource in data.resource_metrics
        for scope in resource.scope_metrics
        for metric in scope.metrics
        if metric.name.startswith("telemetry.")
    }
    result.setdefault("telemetry.spans.exported", 0)
    return result


@pytest.mark.anyio
@pytest.mark.parametrize(("rejected", "accepted"), [(1, 1), (2, 0), (3, 0), (-1, 0)])
async def test_partial_rejection_counts_accepted_spans_and_failed_batches(
    collector: tuple[Collector, str], tmp_path: Path, caplog: pytest.LogCaptureFixture, rejected: int, accepted: int
) -> None:
    receiver, endpoint = collector
    reference = tmp_path / "collector.json"
    reference.write_text('{"bearer_token":"private-token"}')
    reference.chmod(0o600)
    settings = Settings(
        telemetry_trace_export_enabled=True,
        telemetry_credentials_ref=reference,
        telemetry_otlp_endpoint=AnyHttpUrl(endpoint),
    )
    metrics = InMemoryMetricReader()
    telemetry = OpenTelemetry(settings, metric_reader=metrics)
    telemetry.start()
    try:
        receiver.rejected = rejected
        with telemetry.request(create_request_context()):
            with telemetry.operation("child"):
                pass
        assert telemetry.traces is not None
        assert telemetry.traces.force_flush()
        assert counts(metrics) == {"telemetry.spans.exported": accepted, "telemetry.export.failures": 1}
        receiver.unavailable = True
        with telemetry.request(create_request_context()):
            pass
        assert telemetry.traces.force_flush()
        assert counts(metrics) == {"telemetry.spans.exported": accepted, "telemetry.export.failures": 2}
        receiver.unavailable, receiver.rejected = False, 0
        with telemetry.request(create_request_context()):
            pass
        assert telemetry.traces.force_flush()
        assert counts(metrics) == {"telemetry.spans.exported": accepted + 1, "telemetry.export.failures": 2}
        assert receiver.requests == 3
        assert "private-" not in caplog.text
    finally:
        await telemetry.close()
