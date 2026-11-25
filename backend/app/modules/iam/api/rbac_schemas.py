"""Safe RBAC views and explicit, version-bound mutation intents."""

from typing import Literal
from uuid import UUID

from pydantic import Field

from app.api.schemas.common import HttpContract
from app.modules.iam.domain.contracts import PermissionCode, Role
from app.modules.iam.domain.sessions import Application
from app.modules.policy.domain.contracts import KnowledgePermission, PolicyVersion, ResourceGrant


class RoleView(HttpContract):
    role: Role
    permission_codes: tuple[str, ...]


class CapabilityView(HttpContract):
    application: Application
    policy_version: PolicyVersion
    roles: tuple[Role, ...]
    permission_codes: tuple[str, ...]


class KnowledgeScope(HttpContract):
    kb_id: UUID
    can_manage: bool


class GrantView(HttpContract):
    application: Application
    grant: ResourceGrant


class ConfirmedMutation(HttpContract):
    expected_policy_version: PolicyVersion
    confirm: Literal[True]


class CreateRole(ConfirmedMutation):
    code: str = Field(min_length=1, max_length=64, pattern=r"^[A-Z][A-Z0-9_]*$")
    name: str = Field(min_length=1, max_length=128, pattern=r"\S")
    permission_codes: tuple[PermissionCode, ...] = Field(max_length=100)


class UpdateRole(ConfirmedMutation):
    name: str = Field(min_length=1, max_length=128, pattern=r"\S")
    permission_codes: tuple[PermissionCode, ...] = Field(max_length=100)


class AssignRoles(ConfirmedMutation):
    role_ids: tuple[UUID, ...] = Field(max_length=100)


class PutGrant(ConfirmedMutation):
    application: Application
    principal_type: Literal["USER", "ROLE", "ADMIN_USER", "EMPLOYEE"]
    principal_id: UUID
    permission: KnowledgePermission
