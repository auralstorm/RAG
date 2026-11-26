"""Audit HTTP intent is bounded and never accepts client-supplied audit facts."""

from datetime import UTC, datetime
from ipaddress import ip_address
from uuid import uuid4

import pytest
from app.api.audit_context import audit_context
from app.core.config import Settings
from app.core.request_context import create_request_context
from app.main import create_app
from app.modules.audit.api.schemas import AuditQuery
from app.modules.audit.application.recording import security_event
from app.modules.audit.domain.contracts import AuditAction, AuditResult
from app.modules.audit.domain.recording import AuditContext
from app.modules.iam.domain.contracts import Role
from fastapi.testclient import TestClient
from pydantic import ValidationError
from starlette.requests import Request


def test_unconfigured_audit_is_unavailable_and_has_no_public_write_route() -> None:
    with TestClient(create_app(Settings(local_identity_config_ref=None))) as client:
        response = client.get("/api/v1/admin/audit-logs")
        assert response.status_code == 503
        assert response.json()["error"]["request_id"] == response.headers["X-Request-ID"]
        assert client.get("/api/v1/admin/audit-logs", headers={"Origin": "https://foreign.example"}).status_code == 403
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            assert client.request(method, "/api/v1/admin/audit-logs").status_code == 405


def test_audit_selection_rejects_unknown_secrets_and_normalizes_aware_range() -> None:
    query = AuditQuery.model_validate({"occurred_from": "2026-11-25T08:00:00+08:00", "page_size": 100})
    assert query.occurred_from == datetime(2026, 11, 25, tzinfo=UTC)
    for values in (
        {"password": "private"},
        {"occurred_from": "2026-11-25T08:00:00"},
        {"trace_id": "0" * 32},
        {"page_size": 101},
        {"module": "unknown"},
    ):
        with pytest.raises(ValidationError):
            AuditQuery.model_validate(values)


def test_security_event_uses_only_explicit_current_actor_facts() -> None:
    actor = uuid4()
    role = Role(id=uuid4(), code="AUDIT_READONLY", name="auditor", is_system=True, protected=True)
    context = AuditContext(uuid4(), "a" * 32, ip_address("192.0.2.11"))
    success = security_event(context, AuditAction.LOGIN, AuditResult.SUCCEEDED, actor_user_id=actor, roles=(role,))
    assert success.actor_user_id == actor and success.actor_role_ids == (role.id,)
    assert success.ip_address == context.ip_address and success.trace_id == context.trace_id
    anonymous = security_event(context, AuditAction.LOGIN, AuditResult.DENIED)
    assert anonymous.actor_user_id is None and anonymous.actor_role_ids == () and anonymous.after is None


@pytest.mark.parametrize(
    "peer,expected", [("192.0.2.12", "192.0.2.12"), ("2001:db8::42", "2001:db8::42"), ("unix-peer", None), (None, None)]
)
def test_audit_context_uses_direct_peer_and_never_resolves_or_trusts_headers(
    peer: str | None, expected: str | None
) -> None:
    correlated = create_request_context()
    request = Request(
        {
            "type": "http",
            "client": (peer, 1234) if peer else None,
            "state": {"request_context": correlated},
            "headers": [(b"x-forwarded-for", b"203.0.113.11"), (b"x-real-ip", b"203.0.113.12")],
        }
    )
    context = audit_context(request)
    assert (str(context.ip_address) if context.ip_address is not None else None) == expected
    assert context.request_id == correlated.request_id
