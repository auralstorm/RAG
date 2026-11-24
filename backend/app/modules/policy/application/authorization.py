"""Fail closed using current operation permissions and explicit resource membership."""

import hashlib
import hmac
from datetime import UTC, datetime
from uuid import UUID

from app.modules.iam.domain.contracts import IdentityStatus
from app.modules.policy.domain.contracts import (
    AccessContext,
    AccessPurpose,
    AuthorizationRequest,
    AuthorizationSnapshot,
    DecisionEffect,
    DecisionReason,
    KnowledgePermission,
    PolicyDecision,
    ResourceGrant,
    ResourcePrincipalType,
)


def actor_reference(subject_id: UUID, pseudonymization_key: bytes) -> str:
    """Create a pseudonymous reference using a server-resolved key, never a default key."""
    if len(pseudonymization_key) < 32:
        raise ValueError("Actor pseudonymization requires a server key of at least 32 bytes")
    return "actor_" + hmac.new(pseudonymization_key, subject_id.bytes, hashlib.sha256).hexdigest()


def _principal_matches(grant: ResourceGrant, snapshot: AuthorizationSnapshot) -> bool:
    if grant.principal_type is ResourcePrincipalType.USER:
        return grant.principal_id == snapshot.user.id
    if grant.principal_type is ResourcePrincipalType.ROLE:
        return grant.principal_id in snapshot.role_ids
    if grant.principal_type is ResourcePrincipalType.GROUP:
        return grant.principal_id in snapshot.group_ids
    return any(
        binding.principal_type.value == grant.principal_type.value
        and binding.principal_id == grant.principal_id
        and binding.user_id == snapshot.user.id
        for binding in snapshot.subject_bindings
    )


def validate_access_context(
    context: AccessContext | None,
    snapshot: AuthorizationSnapshot,
    *,
    now: datetime,
    purpose: AccessPurpose | None = None,
) -> DecisionReason | None:
    """Check current identity/context binding without granting any operation or resource access."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Authorization requires a timezone-aware server clock")
    if context is None:
        return DecisionReason.MISSING_CONTEXT
    if context.subject_id != snapshot.user.id:
        return DecisionReason.SUBJECT_MISMATCH
    if not snapshot.user.active:
        return DecisionReason.INACTIVE_SUBJECT
    if context.identity_id != snapshot.identity.id:
        return DecisionReason.IDENTITY_MISMATCH
    if snapshot.identity.status is not IdentityStatus.ACTIVE:
        return DecisionReason.INACTIVE_IDENTITY
    if not context.issued_at <= now < context.expires_at:
        return DecisionReason.CONTEXT_EXPIRED
    if not snapshot.observed_at <= now < snapshot.expires_at:
        return DecisionReason.SNAPSHOT_EXPIRED
    if context.environment != snapshot.environment:
        return DecisionReason.ENVIRONMENT_MISMATCH
    if context.purpose != snapshot.purpose or (purpose is not None and purpose != snapshot.purpose):
        return DecisionReason.PURPOSE_MISMATCH
    if context.actor_ref != snapshot.actor_ref:
        return DecisionReason.ACTOR_MISMATCH
    if context.policy_version != snapshot.policy_version:
        return DecisionReason.POLICY_VERSION_MISMATCH
    return None


def _refusal(
    request: AuthorizationRequest, context: AccessContext | None, snapshot: AuthorizationSnapshot, now: datetime
) -> DecisionReason | None:
    reason = validate_access_context(context, snapshot, now=now, purpose=request.purpose)
    if reason is not None:
        return reason
    if request.permission_code not in snapshot.permission_codes:
        return DecisionReason.PERMISSION_DENIED
    if request.kb_id is not None:
        required = KnowledgePermission.MANAGE if request.permission_code == "kb.manage" else KnowledgePermission.READ
        if not any(
            grant.kb_id == request.kb_id
            and (grant.permission is KnowledgePermission.MANAGE or grant.permission is required)
            and _principal_matches(grant, snapshot)
            for grant in snapshot.resource_grants
        ):
            return DecisionReason.RESOURCE_DENIED
    return None


def authorize(
    request: AuthorizationRequest,
    context: AccessContext | None,
    snapshot: AuthorizationSnapshot,
    *,
    now: datetime,
) -> PolicyDecision:
    """Evaluate current facts; caller owns authentication, current reads and operation intent.

    This pure rule creates no session or bearer credential. A decision cannot authorize
    another operation or replace a fresh check after resource/role/lifecycle changes.
    """
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Authorization requires a timezone-aware server clock")
    checked_at = now.astimezone(UTC)
    reason = _refusal(request, context, snapshot, checked_at)
    return PolicyDecision(
        effect=DecisionEffect.DENY if reason is not None else DecisionEffect.ALLOW,
        reason_code=reason or DecisionReason.ALLOWED,
        subject_id=context.subject_id if context is not None else None,
        permission_code=request.permission_code,
        kb_id=request.kb_id,
        policy_version=snapshot.policy_version,
        decided_at=checked_at,
    )
