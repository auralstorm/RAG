"""RBAC use cases enforce policy and commit mutations together with protected audit facts."""

import hmac
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.modules.audit.domain.contracts import AuditAction, AuditEvent, AuditResult, AuditRisk, AuditSnapshot
from app.modules.iam.domain.contracts import Permission, Role, SystemRoleCode
from app.modules.iam.domain.rbac import (
    DELEGABLE_PERMISSIONS,
    PERMISSION_CODES,
    SYSTEM_ROLE_PERMISSIONS,
    AuthorizationDenied,
    RbacConflict,
    RbacRepository,
    RbacTransaction,
    RoleDetails,
)
from app.modules.iam.domain.sessions import Application
from app.modules.policy.application.enforcement import Authority, PolicyEnforcer
from app.modules.policy.domain.contracts import AccessPurpose, KnowledgePermission, ResourceGrant, ResourcePrincipalType


@dataclass(frozen=True)
class MutationContext:
    expected_version: str
    request_id: UUID
    trace_id: str
    csrf_token: str = field(repr=False)


class RbacService:
    def __init__(self, transactions: RbacTransaction, enforcer: PolicyEnforcer) -> None:
        self.transactions = transactions
        self.enforcer = enforcer

    def _event(
        self,
        authority: Authority,
        context: MutationContext,
        action: AuditAction,
        result: AuditResult,
        object_id: UUID | None = None,
        before: AuditSnapshot | None = None,
        after: AuditSnapshot | None = None,
    ) -> AuditEvent:
        return AuditEvent(
            id=uuid4(),
            occurred_at=datetime.now(UTC),
            action=action,
            result=result,
            risk=AuditRisk.HIGH,
            request_id=context.request_id,
            trace_id=context.trace_id,
            actor_user_id=authority.session.user.id,
            actor_role_ids=tuple(item.role.id for item in authority.roles),
            actor_system_roles=tuple(SystemRoleCode(item.role.code) for item in authority.roles if item.role.is_system),
            object_id=object_id,
            before=before,
            after=after,
        )

    @asynccontextmanager
    async def _write(
        self, token: str, context: MutationContext, permission: str, action: AuditAction
    ) -> AsyncGenerator[tuple[RbacRepository, Authority]]:
        failure: AuthorizationDenied | RbacConflict | None = None
        async with self.transactions() as repository:
            version = await repository.policy_version(write=True)
            authority = await self.enforcer.load(repository, "admin", token, version)
            try:
                async with repository.savepoint():
                    self.enforcer.require(authority, permission)
                    if not hmac.compare_digest(context.csrf_token, authority.session.csrf_token):
                        raise AuthorizationDenied()
                    if context.expected_version != version:
                        raise RbacConflict()
                    yield repository, authority
                    # Expiration while waiting for a target/audit write must roll back
                    # both the mutation and its success event before reporting denial.
                    self.enforcer.require(authority, permission)
            except (AuthorizationDenied, RbacConflict) as error:
                failure = error
                await repository.audit(
                    self._event(
                        authority,
                        context,
                        action,
                        AuditResult.DENIED if isinstance(error, AuthorizationDenied) else AuditResult.FAILED,
                    )
                )
        if failure is not None:
            raise failure

    async def capabilities(self, application: Application, token: str) -> Authority:
        async with self.transactions() as repository:
            version = await repository.policy_version(write=False)
            return await self.enforcer.load(repository, application, token, version)

    async def list_roles(self, token: str) -> tuple[RoleDetails, ...]:
        async with self.transactions() as repository:
            authority = await self.enforcer.load(
                repository, "admin", token, await repository.policy_version(write=False)
            )
            self.enforcer.require(authority, "role.read")
            return await repository.roles()

    async def list_permissions(self, token: str) -> tuple[Permission, ...]:
        async with self.transactions() as repository:
            authority = await self.enforcer.load(
                repository, "admin", token, await repository.policy_version(write=False)
            )
            self.enforcer.require(authority, "permission.read")
            return tuple(item for item in await repository.permissions() if item.code in PERMISSION_CODES)

    def _delegable(self, codes: tuple[str, ...]) -> frozenset[str]:
        selected = frozenset(codes)
        if len(selected) != len(codes) or not selected.issubset(DELEGABLE_PERMISSIONS):
            raise AuthorizationDenied()
        return selected

    async def _role_snapshot(
        self, repository: RbacRepository, codes: frozenset[str], *, enabled: bool
    ) -> AuditSnapshot:
        permissions = await repository.permissions()
        return AuditSnapshot(
            enabled=enabled,
            permission_ids=tuple(sorted(item.id for item in permissions if item.code in codes)),
        )

    async def create_role(
        self, token: str, context: MutationContext, code: str, name: str, codes: tuple[str, ...]
    ) -> RoleDetails:
        async with self._write(token, context, "role.manage", AuditAction.ROLE_CHANGE) as (repository, authority):
            permissions = self._delegable(codes)
            if code in SYSTEM_ROLE_PERMISSIONS:
                raise RbacConflict()
            role = Role(id=uuid4(), code=code, name=name, is_system=False, protected=False)
            await repository.create_role(role, permissions)
            await repository.audit(
                self._event(
                    authority,
                    context,
                    AuditAction.ROLE_CHANGE,
                    AuditResult.SUCCEEDED,
                    role.id,
                    AuditSnapshot(enabled=False),
                    await self._role_snapshot(repository, permissions, enabled=True),
                )
            )
            result = RoleDetails(role, permissions)
        return result

    async def update_role(
        self, token: str, context: MutationContext, role_id: UUID, name: str, codes: tuple[str, ...]
    ) -> RoleDetails:
        async with self._write(token, context, "role.manage", AuditAction.PERMISSION_CHANGE) as (repository, authority):
            target = next((item for item in await repository.roles() if item.role.id == role_id), None)
            if target is None or target.role.protected:
                raise RbacConflict()
            permissions = self._delegable(codes)
            await repository.update_role(role_id, name, permissions)
            await repository.audit(
                self._event(
                    authority,
                    context,
                    AuditAction.PERMISSION_CHANGE,
                    AuditResult.SUCCEEDED,
                    role_id,
                    await self._role_snapshot(repository, target.permission_codes, enabled=True),
                    await self._role_snapshot(repository, permissions, enabled=True),
                )
            )
            result = RoleDetails(target.role.model_copy(update={"name": name}), permissions)
        return result

    async def delete_role(self, token: str, context: MutationContext, role_id: UUID) -> None:
        async with self._write(token, context, "role.manage", AuditAction.ROLE_CHANGE) as (repository, authority):
            target = next((item for item in await repository.roles() if item.role.id == role_id), None)
            if target is None or target.role.protected:
                raise RbacConflict()
            await repository.delete_role(role_id)
            await repository.audit(
                self._event(
                    authority,
                    context,
                    AuditAction.ROLE_CHANGE,
                    AuditResult.SUCCEEDED,
                    role_id,
                    await self._role_snapshot(repository, target.permission_codes, enabled=True),
                    AuditSnapshot(enabled=False, permission_ids=()),
                )
            )

    async def assign_roles(
        self, token: str, context: MutationContext, user_id: UUID, role_ids: tuple[UUID, ...]
    ) -> None:
        async with self._write(token, context, "role.manage", AuditAction.ROLE_CHANGE) as (repository, authority):
            roles = await repository.roles()
            selected = [item for item in roles if item.role.id in role_ids]
            target = await repository.user(user_id)
            if target is None or not target.active or len(selected) != len(role_ids):
                raise RbacConflict()
            admins = await repository.active_super_admins()
            if user_id in admins and len(admins) == 1 and not any(item.role.code == "SUPER_ADMIN" for item in selected):
                raise RbacConflict()
            before = tuple(item.role.id for item in await repository.roles(user_id))
            await repository.replace_user_roles(user_id, role_ids)
            await repository.audit(
                self._event(
                    authority,
                    context,
                    AuditAction.ROLE_CHANGE,
                    AuditResult.SUCCEEDED,
                    user_id,
                    AuditSnapshot(role_ids=before),
                    AuditSnapshot(role_ids=role_ids),
                )
            )

    async def put_grant(
        self, token: str, context: MutationContext, application: Application, grant: ResourceGrant
    ) -> None:
        async with self._write(token, context, "acl.manage", AuditAction.PERMISSION_CHANGE) as (repository, authority):
            if application == "chat" and grant.permission is not KnowledgePermission.READ:
                raise AuthorizationDenied()
            if grant.principal_type is ResourcePrincipalType.USER and await repository.user(grant.principal_id) is None:
                raise RbacConflict()
            if grant.principal_type is ResourcePrincipalType.ROLE and not any(
                item.role.id == grant.principal_id for item in await repository.roles()
            ):
                raise RbacConflict()
            before = next(
                (
                    item
                    for purpose, item in await repository.all_grants(grant.kb_id)
                    if purpose == application
                    and item.principal_type == grant.principal_type
                    and item.principal_id == grant.principal_id
                ),
                None,
            )
            await repository.put_grant(application, grant)
            # Upserts preserve the existing grant ID, including in the audit summary.
            after = grant.model_copy(update={"id": before.id}) if before else grant
            await repository.audit(
                self._event(
                    authority,
                    context,
                    AuditAction.PERMISSION_CHANGE,
                    AuditResult.SUCCEEDED,
                    grant.kb_id,
                    AuditSnapshot(enabled=True, resource_grant=before, resource_purpose=AccessPurpose(application))
                    if before
                    else AuditSnapshot(enabled=False),
                    AuditSnapshot(enabled=True, resource_grant=after, resource_purpose=AccessPurpose(application)),
                )
            )

    async def list_grants(self, token: str, kb_id: UUID) -> tuple[tuple[Application, ResourceGrant], ...]:
        async with self.transactions() as repository:
            authority = await self.enforcer.load(
                repository, "admin", token, await repository.policy_version(write=False)
            )
            self.enforcer.require(authority, "acl.read")
            self.enforcer.require(authority, "kb.read", kb_id=kb_id)
            return await repository.all_grants(kb_id)

    async def delete_grant(self, token: str, context: MutationContext, kb_id: UUID, grant_id: UUID) -> None:
        async with self._write(token, context, "acl.manage", AuditAction.PERMISSION_CHANGE) as (repository, authority):
            target = next(
                ((app, grant) for app, grant in await repository.all_grants(kb_id) if grant.id == grant_id), None
            )
            if target is None or not await repository.delete_grant(kb_id, grant_id):
                raise RbacConflict()
            await repository.audit(
                self._event(
                    authority,
                    context,
                    AuditAction.PERMISSION_CHANGE,
                    AuditResult.SUCCEEDED,
                    kb_id,
                    AuditSnapshot(enabled=True, resource_grant=target[1], resource_purpose=AccessPurpose(target[0])),
                    AuditSnapshot(enabled=False),
                )
            )

    async def knowledge_scope(self, application: Application, token: str) -> tuple[tuple[UUID, bool], ...]:
        authority = await self.capabilities(application, token)
        result: list[tuple[UUID, bool]] = []
        for kb_id in sorted({grant.kb_id for grant in authority.snapshot.resource_grants}):
            try:
                self.enforcer.require(authority, "kb.read", kb_id=kb_id)
            except AuthorizationDenied:
                continue
            can_manage = False
            if application == "admin":
                try:
                    self.enforcer.require(authority, "kb.manage", kb_id=kb_id)
                    can_manage = True
                except AuthorizationDenied:
                    pass
            result.append((kb_id, can_manage))
        return tuple(result)

    async def require(self, application: Application, token: str, permission: str, kb_id: UUID | None = None) -> None:
        """Read-only enforcement seam for subsequent modules; decisions are never bearer credentials."""
        async with self.transactions() as repository:
            authority = await self.enforcer.load(
                repository, application, token, await repository.policy_version(write=False)
            )
            self.enforcer.require(authority, permission, kb_id=kb_id)

    async def knowledge_access(self, application: Application, token: str, kb_id: UUID) -> bool:
        async with self.transactions() as repository:
            authority = await self.enforcer.load(
                repository, application, token, await repository.policy_version(write=False)
            )
            self.enforcer.require(authority, "kb.read", kb_id=kb_id)
            if application == "admin":
                try:
                    self.enforcer.require(authority, "kb.manage", kb_id=kb_id)
                    return True
                except AuthorizationDenied:
                    pass
            return False
