"""Collect correlation and the direct ASGI peer; forwarded headers never identify actors."""

from ipaddress import ip_address

from fastapi import Request

from app.api.errors import request_context
from app.modules.audit.domain.recording import AuditContext


def audit_context(request: Request) -> AuditContext:
    correlated = request_context(request)
    address = None
    if request.client is not None:
        try:
            address = ip_address(request.client.host)
        except ValueError:
            # A non-IP ASGI test/Unix peer has no IP; do not resolve hostnames or trust headers.
            pass
    return AuditContext(correlated.request_id, correlated.trace_id, address)
