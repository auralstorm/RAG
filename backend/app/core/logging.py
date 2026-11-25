"""JSON lines from explicit technical fields; raw messages and exception text are discarded."""

import json
import logging
import os
from dataclasses import asdict
from datetime import UTC, datetime

from app.core.observability import MetricBatch, current_request

EVENTS = frozenset(
    {
        "http_request_completed",
        "unhandled_http_error",
        "metrics_snapshot",
        "dependency_status",
        "telemetry_sampler_failed",
        "telemetry_export_failed",
    }
)


class StructuredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        event = record.msg if isinstance(record.msg, str) and record.msg in EVENTS else "component_log"
        component = (
            "app" if record.name.startswith("app.") else "server" if record.name.startswith("uvicorn") else "dependency"
        )
        result: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "event": event,
            "component": component,
            "process_id": os.getpid(),
        }
        context = current_request.get()
        if context is not None:
            result.update(request_id=str(context.request_id), trace_id=context.trace_id, span_id=context.span_id)
        # These extras are supplied by controlled middleware, never copied from a request.
        if event in {"http_request_completed", "unhandled_http_error"}:
            for name in ("method", "route", "status", "duration_seconds", "outcome", "response_started"):
                value: object = getattr(record, name, None)
                if isinstance(value, (str, int, float, bool)):
                    result[name] = value
        if event == "dependency_status":
            for name in ("dependency", "available"):
                value: object = getattr(record, name, None)
                if isinstance(value, (str, bool)):
                    result[name] = value
        batch: object = getattr(record, "metrics", None)
        if event == "metrics_snapshot" and isinstance(batch, MetricBatch):
            result["metrics"] = [asdict(sample) for sample in batch.samples]
        return json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
