"""Request correlation identifiers, separate from identity and resource authorization."""

import re
import secrets
from dataclasses import dataclass
from uuid import UUID, uuid4

TRACEPARENT = re.compile(r"00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})")


@dataclass(frozen=True)
class RequestContext:
    """A fresh server request ID and a validated or newly generated W3C trace context."""

    request_id: UUID
    trace_id: str
    span_id: str
    trace_flags: str

    def response_headers(self) -> dict[str, str]:
        return {
            "X-Request-ID": str(self.request_id),
            "X-Trace-ID": self.trace_id,
            "traceparent": f"00-{self.trace_id}-{self.span_id}-{self.trace_flags}",
        }


def create_request_context(traceparent: str | None = None) -> RequestContext:
    """Accept only version-00 nonzero trace IDs; supplied context never grants authority."""
    parent = TRACEPARENT.fullmatch(traceparent) if traceparent is not None else None
    valid_parent = parent is not None and int(parent[1], 16) != 0 and int(parent[2], 16) != 0
    return RequestContext(
        request_id=uuid4(),
        trace_id=parent[1] if valid_parent and parent is not None else secrets.token_hex(16),
        span_id=secrets.token_hex(8),
        trace_flags=f"{int(parent[3], 16) & 1:02x}" if valid_parent and parent is not None else "00",
    )
