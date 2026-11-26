"""V1 operation matrix and the application-facing persistence port for RBAC."""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.modules.audit.domain.contracts import AuditEvent
from app.modules.iam.domain.contracts import Permission, Role, SubjectBinding, User
from app.modules.iam.domain.sessions import Application, AuthRepository
from app.modules.policy.domain.contracts import ResourceGrant

PERMISSION_CODES = (
    "dashboard.read",
    "provider.read",
    "provider.manage",
    "model.read",
    "model.manage",
    "kb.read",
    "kb.manage",
    "document.read",
    "document.manage",
    "trace.read",
    "trace.reveal_identity",
    "user.read",
    "user.manage",
    "role.read",
    "role.manage",
    "permission.read",
    "employee.read",
    "employee.manage",
    "audit.read",
    "config.read",
    "config.manage",
    "acl.read",
    "acl.manage",
)
DELEGABLE_PERMISSIONS = frozenset(code for code in PERMISSION_CODES if code.endswith(".read"))
SYSTEM_ROLE_PERMISSIONS = {
    "SUPER_ADMIN": frozenset(PERMISSION_CODES),
    "KB_ADMIN": frozenset({"dashboard.read", "kb.read", "document.read"}),
    "AUDIT_READONLY": DELEGABLE_PERMISSIONS,
}


class AuthorizationDenied(PermissionError):
    """The current principal lacks the requested operation or resource capability."""


class RbacConflict(ValueError):
    """A stale policy version, protected role or last-administrator invariant prevents a write."""


@dataclass(frozen=True)
class RoleDetails:
    role: Role
    permission_codes: frozenset[str]


class RbacRepository(AuthRepository, Protocol):
    def savepoint(self) -> AbstractAsyncContextManager[None]: ...
    async def policy_version(self, *, write: bool) -> str: ...
    async def roles(self, user_id: UUID | None = None) -> tuple[RoleDetails, ...]: ...
    async def permissions(self) -> tuple[Permission, ...]: ...
    async def bindings(self, user_id: UUID) -> tuple[SubjectBinding, ...]: ...
    async def grants(
        self,
        application: Application,
        user_id: UUID,
        roles: tuple[RoleDetails, ...],
        bindings: tuple[SubjectBinding, ...],
    ) -> tuple[ResourceGrant, ...]: ...
    async def all_grants(self, kb_id: UUID) -> tuple[tuple[Application, ResourceGrant], ...]: ...
    async def create_role(self, role: Role, permissions: frozenset[str]) -> None: ...
    async def update_role(self, role_id: UUID, name: str, permissions: frozenset[str]) -> None: ...
    async def delete_role(self, role_id: UUID) -> None: ...
    async def user(self, user_id: UUID) -> User | None: ...
    async def replace_user_roles(self, user_id: UUID, role_ids: tuple[UUID, ...]) -> None: ...
    async def active_super_admins(self) -> frozenset[UUID]: ...
    async def put_grant(self, application: Application, grant: ResourceGrant) -> None: ...
    async def delete_grant(self, kb_id: UUID, grant_id: UUID) -> bool: ...
    async def audit(self, event: AuditEvent) -> None: ...


type RbacTransaction = Callable[[], AbstractAsyncContextManager[RbacRepository]]
