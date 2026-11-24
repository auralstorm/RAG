"""V1 IAM contracts; legacy profile identifiers remain explicit mapping sources."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field, model_validator


def utc_timestamp(value: datetime) -> datetime:
    return value.astimezone(UTC)


type UtcTimestamp = Annotated[AwareDatetime, AfterValidator(utc_timestamp)]
type PermissionCode = Annotated[str, Field(max_length=128, pattern=r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")]


class IamContract(BaseModel):
    """Versioned immutable contract; unknown fields and unsupported versions are rejected."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    schema_version: Literal["1.0"] = "1.0"


class UserStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    LOCKED = "LOCKED"
    PENDING_DEPARTURE = "PENDING_DEPARTURE"
    DEPARTED = "DEPARTED"


class IdentityStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class LegacyPrincipalType(StrEnum):
    ADMIN_USER = "ADMIN_USER"
    EMPLOYEE = "EMPLOYEE"


class SystemRoleCode(StrEnum):
    SUPER_ADMIN = "SUPER_ADMIN"
    KB_ADMIN = "KB_ADMIN"
    AUDIT_READONLY = "AUDIT_READONLY"


class User(IamContract):
    """Canonical platform subject; status is current server state, not a token claim."""

    id: UUID
    display_name: str = Field(min_length=1, max_length=128, pattern=r"\S", repr=False)
    status: UserStatus
    created_at: UtcTimestamp
    updated_at: UtcTimestamp

    @model_validator(mode="after")
    def require_time_order(self) -> Self:
        if self.updated_at < self.created_at:
            raise ValueError("User update precedes creation")
        return self

    @property
    def active(self) -> bool:
        return self.status is UserStatus.ACTIVE


class IdentityKey(IamContract):
    """Exact verified-provider lookup key; this type does not verify authentication."""

    provider_key: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_.-]*$", repr=False)
    issuer: str = Field(min_length=1, max_length=2048, pattern=r"\S", repr=False)
    subject: str = Field(min_length=1, max_length=256, pattern=r"\S", repr=False)


class ExternalIdentity(IdentityKey):
    """Restricted mapping facts; raw issuer/subject never belong in public User or Trace DTOs."""

    id: UUID
    user_id: UUID
    status: IdentityStatus

    @property
    def key(self) -> IdentityKey:
        return IdentityKey(provider_key=self.provider_key, issuer=self.issuer, subject=self.subject)


class LegacyPrincipalKey(IamContract):
    """Equal UUID values in different source profile types remain different identities."""

    principal_type: LegacyPrincipalType
    principal_id: UUID


class SubjectBinding(LegacyPrincipalKey):
    """Explicit source-profile to canonical-User association, loaded by the trusted server."""

    user_id: UUID


class Role(IamContract):
    """Role metadata does not grant permissions; assignments and grants are separate facts."""

    id: UUID
    code: str = Field(min_length=1, max_length=64, pattern=r"^[A-Z][A-Z0-9_]*$")
    name: str = Field(min_length=1, max_length=128, pattern=r"\S")
    is_system: bool
    protected: bool

    @model_validator(mode="after")
    def require_system_role_flags(self) -> Self:
        reserved = self.code in {role.value for role in SystemRoleCode}
        if reserved != self.is_system or (reserved and not self.protected):
            raise ValueError("Reserved system roles require matching protected system flags")
        return self


class Permission(IamContract):
    """One operation capability; code is the exact resource.action identifier."""

    id: UUID
    code: PermissionCode
    resource: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    action: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    description: str = Field(default="", max_length=512)

    @model_validator(mode="after")
    def require_consistent_code(self) -> Self:
        if self.code != f"{self.resource}.{self.action}":
            raise ValueError("Permission code must match resource.action")
        return self


class UserRole(IamContract):
    user_id: UUID
    role_id: UUID


class RolePermission(IamContract):
    role_id: UUID
    permission_id: UUID
