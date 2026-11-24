"""Check diagnostic integrity and audit data minimization."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from app.modules.audit.domain.contracts import AuditAction, AuditEvent, AuditResult, AuditRisk, StoredAuditEvent
from app.modules.traces.domain.contracts import Trace, TraceError, TraceSpan, TraceStage, TraceStatus
from pydantic import ValidationError

NOW = datetime(2026, 11, 24, tzinfo=UTC)
END = NOW + timedelta(seconds=1)
TRACE_ID = "a" * 32
ROOT_ID, CHILD_ID, OTHER_ID = (digit * 16 for digit in "123")
REQUEST_ID = UUID(int=1)


def span(span_id: str, parent: str | None, stage: TraceStage) -> TraceSpan:
    return TraceSpan(
        span_id=span_id,
        parent_span_id=parent,
        stage=stage,
        status=TraceStatus.SUCCEEDED,
        started_at=NOW,
        finished_at=END,
    )


def trace_with(*spans: TraceSpan) -> Trace:
    return Trace(trace_id=TRACE_ID, request_id=REQUEST_ID, config_version="rag-v1", spans=spans)


def test_trace_accepts_nested_parallel_diagnostics_in_any_input_order() -> None:
    root = span(ROOT_ID, None, TraceStage.ANSWER)
    child = span(CHILD_ID, ROOT_ID, TraceStage.FUSE)
    nested = span(OTHER_ID, CHILD_ID, TraceStage.DENSE)
    diagnostic = trace_with(nested, root, child)
    assert Trace.model_validate_json(diagnostic.model_dump_json()) == diagnostic


def test_trace_rejects_duplicate_dangling_and_cyclic_span_links() -> None:
    root = span(ROOT_ID, None, TraceStage.ANSWER)
    with pytest.raises(ValidationError, match="unique span IDs"):
        trace_with(root, root)
    with pytest.raises(ValidationError, match="parent in the same trace"):
        trace_with(root, span(CHILD_ID, OTHER_ID, TraceStage.DENSE))
    with pytest.raises(ValidationError, match="connect to the answer root"):
        trace_with(root, span(CHILD_ID, OTHER_ID, TraceStage.DENSE), span(OTHER_ID, CHILD_ID, TraceStage.FUSE))


def test_trace_parent_bounds_and_span_failure_fields_are_enforced() -> None:
    root = span(ROOT_ID, None, TraceStage.ANSWER)
    child = span(CHILD_ID, ROOT_ID, TraceStage.FUSE).model_dump()
    with pytest.raises(ValidationError, match="lifetime"):
        trace_with(root, TraceSpan.model_validate(child | {"status": TraceStatus.RUNNING, "finished_at": None}))
    with pytest.raises(ValidationError, match="stable error code"):
        TraceSpan.model_validate(child | {"status": TraceStatus.FAILED})
    assert (
        TraceSpan.model_validate(child | {"status": TraceStatus.FAILED, "error_code": TraceError.TIMEOUT}).error_code
        is TraceError.TIMEOUT
    )
    with pytest.raises(ValidationError, match="must be nonzero"):
        TraceSpan.model_validate(child | {"span_id": "0" * 16})


def reveal_event() -> AuditEvent:
    return AuditEvent(
        id=UUID(int=2),
        occurred_at=NOW,
        action=AuditAction.IDENTITY_REVEAL,
        result=AuditResult.SUCCEEDED,
        risk=AuditRisk.HIGH,
        request_id=REQUEST_ID,
        trace_id="b" * 32,
        target_trace_id=TRACE_ID,
        actor_user_id=UUID(int=3),
    )


def test_successful_identity_reveal_requires_a_high_risk_event_and_protected_reason() -> None:
    event = reveal_event()
    with pytest.raises(ValidationError, match="high-risk"):
        AuditEvent.model_validate(event.model_dump() | {"risk": AuditRisk.LOW})
    with pytest.raises(ValidationError, match="high-risk"):
        AuditEvent.model_validate(event.model_dump() | {"target_trace_id": None})
    with pytest.raises(ValidationError, match="protected reason"):
        StoredAuditEvent(event=event)
    assert StoredAuditEvent(event=event, protected_reason_ref=UUID(int=4)).event.target_trace_id == TRACE_ID


def test_denied_audit_event_cannot_claim_committed_changes() -> None:
    payload = reveal_event().model_dump() | {
        "action": AuditAction.ROLE_CHANGE,
        "result": AuditResult.DENIED,
        "target_trace_id": None,
        "after": {"enabled": True},
    }
    with pytest.raises(ValidationError, match="committed change"):
        AuditEvent.model_validate(payload)
    assert AuditEvent.model_validate(payload | {"after": None}).result is AuditResult.DENIED


@pytest.mark.parametrize("field", ["api_key", "source_id", "prompt", "password"])
def test_diagnostics_and_audit_snapshots_reject_unlisted_fields(field: str) -> None:
    root = span(ROOT_ID, None, TraceStage.ANSWER)
    with pytest.raises(ValidationError, match="Extra inputs"):
        TraceSpan.model_validate(root.model_dump() | {field: "synthetic sensitive value"})
    with pytest.raises(ValidationError, match="Extra inputs"):
        AuditEvent.model_validate(
            reveal_event().model_dump()
            | {
                "action": AuditAction.PROVIDER_CHANGE,
                "target_trace_id": None,
                "after": {field: "synthetic sensitive value"},
            }
        )


def test_frontend_schemas_exclude_private_link_and_reason_references() -> None:
    root = Path(__file__).resolve().parents[2]
    frontend = (root / "frontend/packages/api-client/src/generated/observability.ts").read_text()
    for name in ("Trace", "TraceSpan", "AuditEvent"):
        assert f"readonly {name}:" in frontend
    for name in ("TraceIdentityLink", "StoredAuditEvent", "protected_identity_ref", "protected_reason_ref"):
        assert f"readonly {name}:" not in frontend
    trace_schema = json.loads((root / "docs/api/schemas/observability/trace.json").read_text())
    assert not {"actor_user_id", "conversation_id", "message_id", "ip_address"} & trace_schema["properties"].keys()
