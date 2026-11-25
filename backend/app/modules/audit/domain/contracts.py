"""Audit facts and allowlisted, typed change summaries."""

from enum import StrEnum
from ipaddress import IPv4Address, IPv6Address
from typing import Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from app.core.contracts import TraceId, UtcTimestamp, VersionedContract
from app.modules.iam.domain.contracts import SystemRoleCode, UserStatus
from app.modules.policy.domain.contracts import AccessPurpose, ResourceGrant


class AuditAction(StrEnum):
    LOGIN = "iam.login"
    ROLE_CHANGE = "iam.role_change"
    PERMISSION_CHANGE = "iam.permission_change"
    PROVIDER_CHANGE = "provider.change"
    MODEL_CHANGE = "model.change"
    KB_CHANGE = "kb.change"
    CONFIG_PUBLISH = "rag.config_publish"
    IDENTITY_REVEAL = "trace.reveal_identity"
    LIFECYCLE_CHANGE = "lifecycle.change"


class AuditResult(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    DENIED = "DENIED"
    FAILED = "FAILED"


class AuditRisk(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class AuditSnapshot(VersionedContract):
    enabled: bool | None = Field(default=None, strict=True)
    user_status: UserStatus | None = None
    application_access: tuple[Literal["chat", "admin"], ...] | None = Field(default=None, max_length=2)
    role_ids: tuple[UUID, ...] | None = Field(default=None, max_length=100)
    permission_ids: tuple[UUID, ...] | None = Field(default=None, max_length=100)
    configuration_id: UUID | None = None
    credential_present: bool | None = Field(default=None, strict=True)
    resource_grant: ResourceGrant | None = None
    resource_purpose: AccessPurpose | None = None

    @model_validator(mode="after")
    def require_grant_purpose(self) -> Self:
        if (self.resource_grant is None) != (self.resource_purpose is None):
            raise ValueError("An audited resource grant requires its application purpose")
        if self.application_access is not None and len(set(self.application_access)) != len(self.application_access):
            raise ValueError("Application access snapshots cannot contain duplicates")
        return self


class AuditEvent(VersionedContract):
    id: UUID
    occurred_at: UtcTimestamp
    action: AuditAction
    result: AuditResult
    risk: AuditRisk
    request_id: UUID
    trace_id: TraceId | None = None
    actor_user_id: UUID | None = Field(default=None, repr=False)
    actor_system_roles: tuple[SystemRoleCode, ...] = ()
    actor_role_ids: tuple[UUID, ...] = Field(default=(), max_length=100)
    ip_address: IPv4Address | IPv6Address | None = Field(default=None, repr=False)
    object_id: UUID | None = None
    target_trace_id: TraceId | None = None
    before: AuditSnapshot | None = Field(default=None, repr=False)
    after: AuditSnapshot | None = Field(default=None, repr=False)

    @model_validator(mode="after")
    def require_auditable_result(self) -> Self:
        if self.actor_user_id is None and (self.actor_system_roles or self.actor_role_ids):
            raise ValueError("Actor roles require a recorded actor")
        if self.result is not AuditResult.SUCCEEDED and self.after is not None:
            raise ValueError("An unsuccessful operation cannot report a committed change")
        if self.action is AuditAction.IDENTITY_REVEAL:
            if (
                self.risk is not AuditRisk.HIGH
                or self.object_id is not None
                or self.before is not None
                or self.after is not None
                or (
                    self.result is AuditResult.SUCCEEDED
                    and (self.actor_user_id is None or self.target_trace_id is None)
                )
            ):
                raise ValueError("Identity reveal requires a high-risk audit event with a trace target on success")
        elif self.target_trace_id is not None:
            raise ValueError("Only identity reveal uses a target trace ID")
        return self


class StoredAuditEvent(VersionedContract):
    event: AuditEvent = Field(repr=False)
    protected_reason_ref: UUID | None = Field(default=None, repr=False)

    @model_validator(mode="after")
    def require_reveal_reason(self) -> Self:
        if (
            self.event.action is AuditAction.IDENTITY_REVEAL
            and self.event.result is AuditResult.SUCCEEDED
            and self.protected_reason_ref is None
        ):
            raise ValueError("Successful identity reveal requires a protected reason record")
        return self
