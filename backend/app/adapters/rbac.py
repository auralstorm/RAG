"""Transactional IAM/Policy database bridge; no HTTP layer accesses these tables."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from uuid import UUID

from psycopg.errors import CheckViolation, ForeignKeyViolation, UniqueViolation

from app.adapters.iam_repository import PostgresAuthRepository
from app.modules.iam.domain.contracts import Permission, Role, SubjectBinding, User
from app.modules.iam.domain.rbac import RbacConflict, RoleDetails
from app.modules.iam.domain.sessions import Application
from app.modules.policy.domain.contracts import ResourceGrant


class PostgresRbacRepository(PostgresAuthRepository):
    @asynccontextmanager
    async def savepoint(self) -> AsyncGenerator[None]:
        try:
            async with self.connection.transaction():
                yield
        except (CheckViolation, ForeignKeyViolation, UniqueViolation) as error:
            raise RbacConflict() from error

    async def policy_version(self, *, write: bool) -> str:
        cursor = await self.connection.execute(
            "SELECT version FROM policy_state WHERE singleton FOR UPDATE"
            if write
            else "SELECT version FROM policy_state WHERE singleton FOR SHARE"
        )
        row = await cursor.fetchone()
        if row is None:
            raise RuntimeError("Current policy state is unavailable")
        return f"rbac-v1:{row[0]}"

    async def roles(self, user_id: UUID | None = None) -> tuple[RoleDetails, ...]:
        cursor = await self.connection.execute(
            "SELECT to_jsonb(r)-'created_at'-'updated_at'-'deleted_at', "
            "COALESCE(array_agg(DISTINCT p.code) FILTER (WHERE p.code IS NOT NULL),'{}') "
            "FROM roles r LEFT JOIN role_permissions rp ON rp.role_id=r.id LEFT JOIN permissions p ON p.id=rp.permission_id "
            "WHERE r.deleted_at IS NULL AND (%s::uuid IS NULL OR EXISTS(SELECT 1 FROM user_roles ur WHERE ur.role_id=r.id AND ur.user_id=%s)) "
            "GROUP BY r.id ORDER BY r.code",
            (user_id, user_id),
        )
        return tuple(
            RoleDetails(Role.model_validate(row[0]), frozenset(str(code) for code in row[1]))
            for row in await cursor.fetchall()
        )

    async def permissions(self) -> tuple[Permission, ...]:
        cursor = await self.connection.execute(
            "SELECT to_jsonb(p)-'created_at'-'updated_at' FROM permissions p ORDER BY code"
        )
        return tuple(Permission.model_validate(row[0]) for row in await cursor.fetchall())

    async def bindings(self, user_id: UUID) -> tuple[SubjectBinding, ...]:
        cursor = await self.connection.execute(
            "SELECT to_jsonb(b)-'created_at' FROM subject_bindings b WHERE user_id=%s", (user_id,)
        )
        return tuple(SubjectBinding.model_validate(row[0]) for row in await cursor.fetchall())

    async def grants(
        self,
        application: Application,
        user_id: UUID,
        roles: tuple[RoleDetails, ...],
        bindings: tuple[SubjectBinding, ...],
    ) -> tuple[ResourceGrant, ...]:
        cursor = await self.connection.execute(
            "SELECT jsonb_build_object('id',g.id,'kb_id',g.kb_id,'principal_type',g.principal_type,'principal_id',g.principal_id,'permission',g.permission) "
            "FROM kb_resource_grants g WHERE purpose=%s AND ((principal_type='USER' AND principal_id=%s) "
            "OR (principal_type='ROLE' AND principal_id=ANY(%s::uuid[])) OR EXISTS(SELECT 1 FROM subject_bindings b "
            "WHERE b.principal_type=g.principal_type AND b.principal_id=g.principal_id AND b.user_id=%s)) ORDER BY g.id",
            (application, user_id, [item.role.id for item in roles], user_id),
        )
        return tuple(ResourceGrant.model_validate(row[0]) for row in await cursor.fetchall())

    async def all_grants(self, kb_id: UUID) -> tuple[tuple[Application, ResourceGrant], ...]:
        cursor = await self.connection.execute(
            "SELECT jsonb_build_object('id',g.id,'kb_id',g.kb_id,'principal_type',g.principal_type,'principal_id',g.principal_id,'permission',g.permission),purpose "
            "FROM kb_resource_grants g WHERE kb_id=%s ORDER BY id",
            (kb_id,),
        )
        # The database restricts purposes to the same closed application vocabulary.
        return tuple(
            ("chat" if row[1] == "chat" else "admin", ResourceGrant.model_validate(row[0]))
            for row in await cursor.fetchall()
        )

    async def create_role(self, role: Role, permissions: frozenset[str]) -> None:
        await self.connection.execute(
            "INSERT INTO roles(id,code,name,is_system,protected) VALUES(%s,%s,%s,false,false)",
            (role.id, role.code, role.name),
        )
        await self._insert_permissions(role.id, permissions)

    async def _insert_permissions(self, role_id: UUID, permissions: frozenset[str]) -> None:
        await self.connection.execute(
            "INSERT INTO role_permissions(role_id,permission_id) SELECT %s,id FROM permissions WHERE code=ANY(%s::text[])",
            (role_id, list(permissions)),
        )

    async def update_role(self, role_id: UUID, name: str, permissions: frozenset[str]) -> None:
        await self.connection.execute(
            "UPDATE roles SET name=%s WHERE id=%s AND NOT protected AND deleted_at IS NULL", (name, role_id)
        )
        await self.connection.execute("DELETE FROM role_permissions WHERE role_id=%s", (role_id,))
        await self._insert_permissions(role_id, permissions)

    async def delete_role(self, role_id: UUID) -> None:
        await self.connection.execute(
            "UPDATE roles SET deleted_at=CURRENT_TIMESTAMP WHERE id=%s AND NOT protected", (role_id,)
        )

    async def user(self, user_id: UUID) -> User | None:
        cursor = await self.connection.execute(
            "SELECT to_jsonb(u)-'deleted_at' FROM users u WHERE id=%s AND deleted_at IS NULL", (user_id,)
        )
        row = await cursor.fetchone()
        return User.model_validate(row[0]) if row else None

    async def replace_user_roles(self, user_id: UUID, role_ids: tuple[UUID, ...]) -> None:
        await self.connection.execute("DELETE FROM user_roles WHERE user_id=%s", (user_id,))
        await self.connection.execute(
            "INSERT INTO user_roles(user_id,role_id) SELECT %s,id FROM roles WHERE id=ANY(%s::uuid[])",
            (user_id, list(role_ids)),
        )

    async def active_super_admins(self) -> frozenset[UUID]:
        cursor = await self.connection.execute(
            "SELECT DISTINCT u.id FROM users u JOIN user_roles ur ON ur.user_id=u.id JOIN roles r ON r.id=ur.role_id "
            "WHERE u.status='ACTIVE' AND u.deleted_at IS NULL AND r.code='SUPER_ADMIN' AND r.deleted_at IS NULL "
            "AND EXISTS(SELECT 1 FROM identities i JOIN identity_applications a ON a.identity_id=i.id "
            "WHERE i.user_id=u.id AND i.status='ACTIVE' AND i.deleted_at IS NULL AND a.application='admin')"
        )
        return frozenset(UUID(str(row[0])) for row in await cursor.fetchall())

    async def put_grant(self, application: Application, grant: ResourceGrant) -> None:
        await self.connection.execute(
            "INSERT INTO kb_resource_grants(id,kb_id,purpose,principal_type,principal_id,permission) VALUES(%s,%s,%s,%s,%s,%s) "
            "ON CONFLICT(kb_id,purpose,principal_type,principal_id) DO UPDATE SET permission=EXCLUDED.permission",
            (
                grant.id,
                grant.kb_id,
                application,
                grant.principal_type.value,
                grant.principal_id,
                grant.permission.value,
            ),
        )

    async def delete_grant(self, kb_id: UUID, grant_id: UUID) -> bool:
        cursor = await self.connection.execute(
            "DELETE FROM kb_resource_grants WHERE id=%s AND kb_id=%s RETURNING id", (grant_id, kb_id)
        )
        return await cursor.fetchone() is not None
