"""JSON lines from explicit technical fields; raw messages and exception text are discarded."""

import json
import logging
import os
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

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
APP_ROOT = Path(__file__).absolute().parents[1]


@dataclass(frozen=True)
class ExceptionDiagnostic:
    causes: list[dict[str, object]]


def exception_chain(error: BaseException) -> ExceptionDiagnostic:
    """Keep bounded code locations and types, never messages, source lines or locals."""
    causes: list[dict[str, object]] = []
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen and len(causes) < 5:
        seen.add(id(current))
        error_type = type(current).__name__
        frames: list[dict[str, object]] = []
        traceback = current.__traceback__
        while traceback is not None:
            code = traceback.tb_frame.f_code
            try:
                relative = Path(code.co_filename).relative_to(APP_ROOT)
            except ValueError:
                relative = None
            if relative is not None and all(re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", part) for part in relative.parts):
                frames.append(
                    {
                        "source": "app/" + relative.as_posix(),
                        "function": code.co_name if re.fullmatch(r"[A-Za-z0-9_]{1,128}", code.co_name) else "<code>",
                        "line": traceback.tb_lineno,
                    }
                )
                frames = frames[-8:]
            traceback = traceback.tb_next
        causes.append(
            {"type": error_type if re.fullmatch(r"[A-Za-z0-9_]{1,128}", error_type) else "Exception", "frames": frames}
        )
        current = current.__cause__ or (None if current.__suppress_context__ else current.__context__)
    return ExceptionDiagnostic(causes)


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
        diagnostic: object = getattr(record, "diagnostic", None)
        if event == "unhandled_http_error" and isinstance(diagnostic, ExceptionDiagnostic):
            result["exception_chain"] = diagnostic.causes
        if event == "dependency_status":
            for name in ("dependency", "available"):
                value: object = getattr(record, name, None)
                if isinstance(value, (str, bool)):
                    result[name] = value
        batch: object = getattr(record, "metrics", None)
        if event == "metrics_snapshot" and isinstance(batch, MetricBatch):
            result["metrics"] = [asdict(sample) for sample in batch.samples]
        return json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
