"""Technical observation ports and task-local correlation, never authorization facts."""

from collections.abc import Generator, Mapping
from contextlib import AbstractContextManager, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Literal, Protocol

from app.core.request_context import RequestContext

type HttpOutcome = Literal["completed", "error", "aborted", "cancelled"]


@dataclass(frozen=True)
class MetricSample:
    name: str
    attributes: Mapping[str, str | int]
    unit: str = ""
    started_at_ns: int = 0
    observed_at_ns: int = 0
    value: int | float | None = None
    count: int | None = None
    total: int | float | None = None
    boundaries: tuple[float, ...] = ()
    buckets: tuple[int, ...] = ()


@dataclass(frozen=True)
class MetricBatch:
    samples: tuple[MetricSample, ...]


class MetricSink(Protocol):
    def dependency(self, name: str, available: bool, duration: float) -> None: ...
    def postgres_connections(self, count: int | None) -> None: ...
    def queue_messages(self, queue: str, count: int | None) -> None: ...


class Telemetry(MetricSink, Protocol):
    def request(self, context: RequestContext) -> AbstractContextManager[RequestContext]: ...
    def operation(self, name: str) -> AbstractContextManager[None]: ...
    def http_completed(self, method: str, route: str, status: int, duration: float, outcome: HttpOutcome) -> None: ...


current_request: ContextVar[RequestContext | None] = ContextVar("observed_request", default=None)
current_telemetry: ContextVar[Telemetry | None] = ContextVar("request_telemetry", default=None)


@contextmanager
def observe_operation(name: str) -> Generator[None]:
    """Observe a technical operation within the current request without changing its transaction."""
    telemetry = current_telemetry.get()
    if telemetry is None:
        yield
    else:
        with telemetry.operation(name):
            yield
