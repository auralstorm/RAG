"""Construct allowlisted audit facts without copying request payloads or credentials."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.modules.audit.domain.contracts import AuditAction, AuditEvent, AuditResult, AuditRisk, AuditSnapshot
from app.modules.audit.domain.recording import AuditContext
from app.modules.iam.domain.contracts import Role, SystemRoleCode


def security_event(
    context: AuditContext,
    action: AuditAction,
    result: AuditResult,
    *,
    actor_user_id: UUID | None = None,
    roles: tuple[Role, ...] = (),
    object_id: UUID | None = None,
    before: AuditSnapshot | None = None,
    after: AuditSnapshot | None = None,
) -> AuditEvent:
    """Record server-loaded actor facts; unknown login actors remain anonymous."""
    return AuditEvent(
        id=uuid4(),
        occurred_at=datetime.now(UTC),
        action=action,
        result=result,
        risk=AuditRisk.MEDIUM if action is AuditAction.LOGIN else AuditRisk.HIGH,
        request_id=context.request_id,
        trace_id=context.trace_id,
        ip_address=context.ip_address,
        actor_user_id=actor_user_id,
        actor_role_ids=tuple(role.id for role in roles),
        actor_system_roles=tuple(SystemRoleCode(role.code) for role in roles if role.is_system),
        object_id=object_id,
        before=before,
        after=after,
    )
