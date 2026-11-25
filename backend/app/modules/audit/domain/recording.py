"""Append-only audit port and trusted request metadata; callers own the transaction."""

from dataclasses import dataclass, field
from ipaddress import IPv4Address, IPv6Address
from typing import Protocol
from uuid import UUID

from app.modules.audit.domain.contracts import AuditEvent


@dataclass(frozen=True)
class AuditContext:
    request_id: UUID
    trace_id: str
    ip_address: IPv4Address | IPv6Address | None = field(default=None, repr=False)


class AuditWriter(Protocol):
    async def audit(self, event: AuditEvent) -> None:
        """Append a validated fact in the caller's transaction; never commit or discard failures."""
        ...
