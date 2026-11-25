"""Owned OpenTelemetry providers with bounded, anonymous technical observations."""

import asyncio
import logging
import os
from collections.abc import Generator, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import replace
from threading import Lock

from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.metrics import CallbackOptions, Counter, Histogram, Observation, UpDownCounter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    HistogramDataPoint,
    MetricExporter,
    MetricExportResult,
    MetricReader,
    MetricsData,
    NumberDataPoint,
    PeriodicExportingMetricReader,
)
from opentelemetry.sdk.metrics.view import ExplicitBucketHistogramAggregation, View
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor, SpanExporter, SpanExportResult
from opentelemetry.sdk.trace.sampling import TraceIdRatioBased
from opentelemetry.trace import NonRecordingSpan, SpanContext, SpanKind, Status, StatusCode, TraceFlags

from app.adapters.telemetry_credentials import read_collector_credentials
from app.core.config import Settings
from app.core.observability import HttpOutcome, MetricBatch, MetricSample
from app.core.request_context import RequestContext

logger = logging.getLogger(__name__)
LABELS = frozenset({"method", "route", "status", "outcome", "dependency", "queue"})


class ObservedSpanExporter(SpanExporter):
    """Count collector acknowledgements, not just flushes; exporter failures stay observational."""

    def __init__(self, exporter: SpanExporter, successes: Counter, failures: Counter) -> None:
        self.exporter = exporter
        self.successes = successes
        self.failures = failures

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        try:
            result = self.exporter.export(spans)
        except Exception:
            result = SpanExportResult.FAILURE
        if result is SpanExportResult.SUCCESS:
            self.successes.add(len(spans))
        else:
            self.failures.add(1)
            logger.warning("telemetry_export_failed")
        return result

    def shutdown(self) -> None:
        self.exporter.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self.exporter.force_flush(timeout_millis)


class JsonMetricExporter(MetricExporter):
    """Emit numeric SDK aggregates through the same technical JSON logging configuration."""

    def export(self, metrics_data: MetricsData, timeout_millis: float = 10000, **kwargs: object) -> MetricExportResult:
        samples: list[MetricSample] = []
        for resource in metrics_data.resource_metrics:
            for scope in resource.scope_metrics:
                for metric in scope.metrics:
                    for point in metric.data.data_points:
                        attributes = {
                            key: value
                            for key, value in (point.attributes or {}).items()
                            if key in LABELS and isinstance(value, (str, int))
                        }
                        if isinstance(point, HistogramDataPoint):
                            samples.append(
                                MetricSample(
                                    metric.name,
                                    attributes,
                                    unit=metric.unit or "",
                                    started_at_ns=point.start_time_unix_nano,
                                    observed_at_ns=point.time_unix_nano,
                                    count=point.count,
                                    total=point.sum,
                                    boundaries=tuple(point.explicit_bounds),
                                    buckets=tuple(point.bucket_counts),
                                )
                            )
                        elif isinstance(point, NumberDataPoint):
                            samples.append(
                                MetricSample(
                                    metric.name,
                                    attributes,
                                    unit=metric.unit or "",
                                    started_at_ns=point.start_time_unix_nano,
                                    observed_at_ns=point.time_unix_nano,
                                    value=point.value,
                                )
                            )
        logger.info("metrics_snapshot", extra={"metrics": MetricBatch(tuple(samples))})
        return MetricExportResult.SUCCESS

    def force_flush(self, timeout_millis: float = 10000) -> bool:
        return True

    def shutdown(self, timeout_millis: float = 30000, **kwargs: object) -> None:
        return None


class OpenTelemetry:
    """Each application owns providers; no global SDK setup or default HTTP/SQL body capture."""

    def __init__(
        self,
        settings: Settings,
        *,
        span_exporter: SpanExporter | None = None,
        metric_reader: MetricReader | None = None,
    ) -> None:
        self.settings = settings
        self.span_exporter = span_exporter
        self.metric_reader = metric_reader
        self.traces: TracerProvider | None = None
        self.metrics: MeterProvider | None = None
        self.tracer: trace.Tracer | None = None
        self.requests: Counter | None = None
        self.duration: Histogram | None = None
        self.active: UpDownCounter | None = None
        self.probe_duration: Histogram | None = None
        self.lock = Lock()
        self.health: dict[str, bool] = {}
        self.connections: int | None = None
        self.queues: dict[str, int | None] = {name: None for name in settings.telemetry_queues}

    def start(self) -> None:
        if not self.settings.telemetry_enabled:
            return
        # Do not run Resource.create(): environment detectors can add arbitrary sensitive attributes.
        resource = Resource(
            {
                "service.name": "enterprise-rag-api",
                "service.version": "0.1.0",
                "service.instance.id": f"api-{os.getpid()}",
                "deployment.environment.name": self.settings.environment,
                "openinference.project.name": "enterprise-rag-api",
            }
        )
        reader = self.metric_reader or PeriodicExportingMetricReader(
            JsonMetricExporter(),
            export_interval_millis=self.settings.telemetry_interval_seconds * 1000,
            export_timeout_millis=2000,
        )
        self.metrics = MeterProvider(
            resource=resource,
            metric_readers=[reader],
            shutdown_on_exit=False,
            views=[
                View(
                    instrument_type=Histogram,
                    aggregation=ExplicitBucketHistogramAggregation(
                        (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60)
                    ),
                )
            ],
        )
        meter = self.metrics.get_meter("enterprise-rag.observability", "1.0")
        exported_spans = meter.create_counter("telemetry.spans.exported", unit="{span}")
        export_failures = meter.create_counter("telemetry.export.failures", unit="{failure}")
        self.requests = meter.create_counter("http.server.requests", unit="{request}")
        self.duration = meter.create_histogram("http.server.duration", unit="s")
        self.active = meter.create_up_down_counter("http.server.active_requests", unit="{request}")
        self.probe_duration = meter.create_histogram("dependency.probe.duration", unit="s")
        meter.create_observable_gauge("dependency.available", callbacks=[self._health], unit="1")
        meter.create_observable_gauge("db.server.connections", callbacks=[self._connections], unit="{connection}")
        meter.create_observable_gauge("db.observation.available", callbacks=[self._connections_available], unit="1")
        meter.create_observable_gauge("messaging.queue.ready", callbacks=[self._queues], unit="{message}")
        meter.create_observable_gauge("messaging.observation.available", callbacks=[self._queues_available], unit="1")
        self.traces = TracerProvider(
            resource=resource, sampler=TraceIdRatioBased(self.settings.telemetry_sample_ratio), shutdown_on_exit=False
        )
        if self.span_exporter is not None:
            self.traces.add_span_processor(
                SimpleSpanProcessor(ObservedSpanExporter(self.span_exporter, exported_spans, export_failures))
            )
        elif self.settings.telemetry_trace_export_enabled:
            if self.settings.telemetry_credentials_ref is None:
                raise ValueError("Collector credential reference is missing")
            credentials = read_collector_credentials(self.settings.telemetry_credentials_ref)
            endpoint = str(self.settings.telemetry_otlp_endpoint).rstrip("/")
            exporter = OTLPSpanExporter(
                endpoint=endpoint,
                insecure=endpoint.startswith("http://"),
                timeout=2,
                headers={"authorization": "Bearer " + credentials.bearer_token.get_secret_value()},
            )
            self.traces.add_span_processor(
                BatchSpanProcessor(
                    ObservedSpanExporter(exporter, exported_spans, export_failures),
                    max_queue_size=2048,
                    max_export_batch_size=256,
                    export_timeout_millis=2000,
                )
            )
        self.tracer = self.traces.get_tracer("enterprise-rag.observability", "1.0")

    async def close(self) -> None:
        metrics, traces = self.metrics, self.traces
        self.metrics, self.traces, self.tracer = None, None, None
        self.requests, self.duration, self.active, self.probe_duration = None, None, None, None
        try:
            if traces is not None:
                await asyncio.to_thread(traces.shutdown)
        finally:
            if metrics is not None:
                await asyncio.to_thread(metrics.shutdown, timeout_millis=3000)

    @contextmanager
    def request(self, context: RequestContext) -> Generator[RequestContext]:
        if self.tracer is None:
            yield context
            return
        parent = Context()
        if context.parent_span_id is not None:
            remote = SpanContext(
                int(context.trace_id, 16),
                int(context.parent_span_id, 16),
                True,
                TraceFlags(int(context.trace_flags, 16)),
            )
            parent = trace.set_span_in_context(NonRecordingSpan(remote), parent)
        span = self.tracer.start_span(
            "http.request", context=parent, kind=SpanKind.SERVER, attributes={"request.id": str(context.request_id)}
        )
        active = span.get_span_context()
        observed = replace(
            context,
            trace_id=f"{active.trace_id:032x}",
            span_id=f"{active.span_id:016x}",
            trace_flags=f"{int(active.trace_flags):02x}",
        )
        if self.active is not None:
            self.active.add(1)
        try:
            with trace.use_span(span, end_on_exit=True, record_exception=False, set_status_on_exception=False):
                yield observed
        finally:
            if self.active is not None:
                self.active.add(-1)

    @contextmanager
    def operation(self, name: str) -> Generator[None]:
        if self.tracer is None:
            yield
            return
        span = self.tracer.start_span(name)
        with trace.use_span(span, end_on_exit=True, record_exception=False, set_status_on_exception=False):
            try:
                yield
            except BaseException:
                span.set_status(Status(StatusCode.ERROR))
                span.set_attribute("error.type", "operation_error")
                raise

    def http_completed(self, method: str, route: str, status: int, duration: float, outcome: HttpOutcome) -> None:
        if self.tracer is None:
            return
        attributes = {"method": method, "route": route, "status": status, "outcome": outcome}
        if self.requests is not None and self.duration is not None:
            self.requests.add(1, attributes)
            self.duration.record(duration, attributes)
        span = trace.get_current_span()
        span.update_name(f"{method} {route}")
        for key, value in attributes.items():
            span.set_attribute(key, value)
        if status >= 500 or outcome != "completed":
            span.set_status(Status(StatusCode.ERROR))
            span.set_attribute("error.type", "http_error" if outcome == "completed" else outcome)

    def dependency(self, name: str, available: bool, duration: float) -> None:
        with self.lock:
            previous = self.health.get(name)
            self.health[name] = available
        if previous is not available:
            logger.info("dependency_status", extra={"dependency": name, "available": available})
        if self.probe_duration is not None:
            self.probe_duration.record(duration, {"dependency": name})

    def postgres_connections(self, count: int | None) -> None:
        with self.lock:
            self.connections = count

    def queue_messages(self, queue: str, count: int | None) -> None:
        with self.lock:
            self.queues[queue] = count

    def _health(self, _options: CallbackOptions) -> Iterator[Observation]:
        with self.lock:
            health = dict(self.health)
        for name, available in health.items():
            yield Observation(int(available), {"dependency": name})

    def _connections(self, _options: CallbackOptions) -> Iterator[Observation]:
        with self.lock:
            count = self.connections
        if count is not None:
            yield Observation(count)

    def _connections_available(self, _options: CallbackOptions) -> Iterator[Observation]:
        with self.lock:
            available = self.connections is not None
        yield Observation(int(available))

    def _queues(self, _options: CallbackOptions) -> Iterator[Observation]:
        with self.lock:
            queues = dict(self.queues)
        for queue, count in queues.items():
            if count is not None:
                yield Observation(count, {"queue": queue})

    def _queues_available(self, _options: CallbackOptions) -> Iterator[Observation]:
        with self.lock:
            queues = dict(self.queues)
        if not queues:
            yield Observation(0)
        for queue, count in queues.items():
            yield Observation(int(count is not None), {"queue": queue})
