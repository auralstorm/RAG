"""Bounded OTLP transport retaining acknowledgements discarded by the stock exporter."""

import logging
from collections.abc import Sequence
from threading import Lock
from urllib.parse import urlsplit

import grpc
from opentelemetry.exporter.otlp.proto.common.trace_encoder import encode_spans
from opentelemetry.metrics import Counter
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
    ExportTraceServiceResponse,
)
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

logger = logging.getLogger(__name__)


class AcknowledgedOtlpExporter(SpanExporter):
    """Count accepted spans and failed batches, never retain collector error text or retry partial batches."""

    def __init__(self, endpoint: str, token: str, successes: Counter, failures: Counter) -> None:
        address = urlsplit(endpoint)
        self.channel = (
            grpc.secure_channel(address.netloc, grpc.ssl_channel_credentials())
            if address.scheme == "https"
            else grpc.insecure_channel(address.netloc)
        )
        # Public generic gRPC calls avoid depending on the generated stub's untyped constructor.
        self.send: grpc.UnaryUnaryMultiCallable[ExportTraceServiceRequest, ExportTraceServiceResponse] = (
            self.channel.unary_unary(
                "/opentelemetry.proto.collector.trace.v1.TraceService/Export",
                request_serializer=ExportTraceServiceRequest.SerializeToString,
                response_deserializer=ExportTraceServiceResponse.FromString,
            )
        )
        self.metadata = (("authorization", "Bearer " + token),)
        self.successes, self.failures = successes, failures
        self.lock = Lock()
        self.closed = False

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        with self.lock:
            if self.closed:
                return SpanExportResult.FAILURE
            try:
                response = self.send(encode_spans(spans), metadata=self.metadata, timeout=2, wait_for_ready=True)
                rejected = response.partial_success.rejected_spans
                # Invalid acknowledgements cannot establish that any spans were accepted.
                if rejected < 0 or rejected > len(spans):
                    accepted, failed = 0, True
                else:
                    accepted, failed = len(spans) - rejected, rejected > 0
            except Exception:
                accepted, failed = 0, True
            if accepted:
                self.successes.add(accepted)
            if failed:
                self.failures.add(1)
                logger.warning("telemetry_export_failed")
                return SpanExportResult.FAILURE
            return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        with self.lock:
            if not self.closed:
                self.closed = True
                self.channel.close()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True
