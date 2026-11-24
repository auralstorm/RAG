"""V1 policy facts distinguish trusted context, operation intent and resource grants."""

from enum import StrEnum
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from app.modules.iam.domain.contracts import (
    ExternalIdentity,
    IamContract,
    PermissionCode,
    SubjectBinding,
    User,
    UtcTimestamp,
)

type PolicyVersion = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")]
type ActorReference = Annotated[str, Field(pattern=r"^actor_[0-9a-f]{64}$")]
type Environment = Literal["development", "test", "production"]


class AccessPurpose(StrEnum):
    ADMIN = "admin"
    CHAT = "chat"


class ResourcePrincipalType(StrEnum):
    USER = "USER"
    ROLE = "ROLE"
    GROUP = "GROUP"
    ADMIN_USER = "ADMIN_USER"
    EMPLOYEE = "EMPLOYEE"


class KnowledgePermission(StrEnum):
    READ = "READ"
    MANAGE = "MANAGE"


class ResourceGrant(IamContract):
    """Explicit KB capability; source profile types require a verified SubjectBinding."""

    id: UUID
    kb_id: UUID
    principal_type: ResourcePrincipalType
    principal_id: UUID
    permission: KnowledgePermission


class AccessContext(IamContract):
    """Internal server-created context, never authenticated by deserializing its fields.

    User-supplied filters, token role claims and model output do not populate this type.
    actor_ref is pseudonymous correlation, not an alternative authorization subject.
    """

    subject_id: UUID
    identity_id: UUID
    actor_ref: ActorReference
    environment: Environment
    purpose: AccessPurpose
    policy_version: PolicyVersion
    issued_at: UtcTimestamp
    expires_at: UtcTimestamp

    @model_validator(mode="after")
    def require_valid_window(self) -> Self:
        if self.expires_at <= self.issued_at:
            raise ValueError("Access context expiration must follow issuance")
        return self


class AuthorizationRequest(IamContract):
    """Server-selected operation and purpose; a KB ID expresses selection, not permission."""

    permission_code: PermissionCode
    purpose: AccessPurpose
    kb_id: UUID | None = None

    @model_validator(mode="after")
    def require_known_resource_scope(self) -> Self:
        kb_action = self.permission_code in ("kb.read", "kb.manage")
        if kb_action != (self.kb_id is not None):
            raise ValueError("KB operations require a KB ID; other operations cannot use a KB as authorization")
        if self.purpose is AccessPurpose.CHAT and self.permission_code != "kb.read":
            raise ValueError("This V1 IAM policy interface permits only KB read operations for Chat")
        return self


class AuthorizationSnapshot(IamContract):
    """Current facts independently loaded by the trusted server, not copied from context.

    Snapshot validity is an input guard, not proof that a cached grant survived revocation.
    Producers reload current identity/roles/groups/ACL for every authorization operation.
    """

    user: User = Field(repr=False)
    identity: ExternalIdentity = Field(repr=False)
    actor_ref: ActorReference
    environment: Environment
    purpose: AccessPurpose
    policy_version: PolicyVersion
    role_ids: frozenset[UUID]
    group_ids: frozenset[UUID]
    permission_codes: frozenset[PermissionCode]
    resource_grants: tuple[ResourceGrant, ...] = Field(repr=False)
    subject_bindings: tuple[SubjectBinding, ...] = Field(repr=False)
    observed_at: UtcTimestamp
    expires_at: UtcTimestamp

    @model_validator(mode="after")
    def require_consistent_snapshot(self) -> Self:
        if self.identity.user_id != self.user.id:
            raise ValueError("Authorization identity belongs to a different user")
        if self.expires_at <= self.observed_at:
            raise ValueError("Authorization snapshot expiration must follow observation")
        source_keys = [(binding.principal_type, binding.principal_id) for binding in self.subject_bindings]
        if len(source_keys) != len(set(source_keys)):
            raise ValueError("Authorization snapshot contains ambiguous subject bindings")
        if len({grant.id for grant in self.resource_grants}) != len(self.resource_grants):
            raise ValueError("Authorization snapshot contains duplicate resource grant IDs")
        grant_keys = [
            (grant.kb_id, grant.principal_type, grant.principal_id, grant.permission) for grant in self.resource_grants
        ]
        if len(grant_keys) != len(set(grant_keys)):
            raise ValueError("Authorization snapshot contains duplicate resource capabilities")
        return self


class DecisionEffect(StrEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"


class DecisionReason(StrEnum):
    ALLOWED = "ALLOWED"
    MISSING_CONTEXT = "MISSING_CONTEXT"
    SUBJECT_MISMATCH = "SUBJECT_MISMATCH"
    INACTIVE_SUBJECT = "INACTIVE_SUBJECT"
    IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
    INACTIVE_IDENTITY = "INACTIVE_IDENTITY"
    CONTEXT_EXPIRED = "CONTEXT_EXPIRED"
    SNAPSHOT_EXPIRED = "SNAPSHOT_EXPIRED"
    ENVIRONMENT_MISMATCH = "ENVIRONMENT_MISMATCH"
    PURPOSE_MISMATCH = "PURPOSE_MISMATCH"
    ACTOR_MISMATCH = "ACTOR_MISMATCH"
    POLICY_VERSION_MISMATCH = "POLICY_VERSION_MISMATCH"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    RESOURCE_DENIED = "RESOURCE_DENIED"


class PolicyDecision(IamContract):
    """Decision binds the operation, subject, KB and current policy version; it is not a token."""

    effect: DecisionEffect
    reason_code: DecisionReason
    subject_id: UUID | None
    permission_code: PermissionCode
    kb_id: UUID | None
    policy_version: PolicyVersion
    decided_at: UtcTimestamp

    @model_validator(mode="after")
    def require_consistent_effect(self) -> Self:
        if self.effect is DecisionEffect.ALLOW:
            if self.subject_id is None or self.reason_code is not DecisionReason.ALLOWED:
                raise ValueError("Allow decisions require a subject and an allowed reason")
        elif self.reason_code is DecisionReason.ALLOWED:
            raise ValueError("Deny decisions require a refusal reason")
        return self

    @property
    def allowed(self) -> bool:
        return self.effect is DecisionEffect.ALLOW
