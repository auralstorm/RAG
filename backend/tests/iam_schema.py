"""Real PostgreSQL assertions for the P1-03 identity, relationship and audit boundary."""

import asyncio
from uuid import UUID, uuid4

import pytest
from app.adapters.postgres import postgres_transaction
from app.core.config import Settings
from psycopg import AsyncConnection, IntegrityError, sql
from psycopg.abc import QueryNoTemplate
from psycopg.errors import CheckViolation, ForeignKeyViolation, UniqueViolation
from psycopg.rows import TupleRow


async def rejected(
    connection: AsyncConnection[TupleRow],
    statement: QueryNoTemplate,
    parameters: tuple[object, ...] = (),
    error: type[IntegrityError] = CheckViolation,
) -> None:
    """A savepoint keeps each deliberate constraint failure out of the surrounding transaction."""
    with pytest.raises(error):
        async with connection.transaction():
            await connection.execute(statement, parameters)


async def verify_iam_schema(settings: Settings) -> None:
    """Run on a disposable migrated database; do not invoke against business data."""
    user_id, other_user_id, identity_id, role_id, permission_id = (uuid4() for _ in range(5))
    source_id = uuid4()
    async with postgres_transaction(settings) as connection:
        await connection.execute(
            "INSERT INTO users (id, display_name, status) VALUES (%s, '员工', 'ACTIVE'), (%s, '员工', 'ACTIVE')",
            (user_id, other_user_id),
        )
        for status in ("ACTIVE", "DISABLED", "LOCKED", "PENDING_DEPARTURE", "DEPARTED"):
            await connection.execute("UPDATE users SET status = %s WHERE id = %s", (status, user_id))
        await rejected(connection, "UPDATE users SET status = 'UNKNOWN' WHERE id = %s", (user_id,))
        await rejected(connection, "UPDATE users SET display_name = '   ' WHERE id = %s", (user_id,))
        await rejected(
            connection, "UPDATE users SET status = 'ACTIVE', deleted_at = CURRENT_TIMESTAMP WHERE id = %s", (user_id,)
        )
        await connection.execute("UPDATE users SET status = 'ACTIVE' WHERE id = %s", (user_id,))

        insert_identity = (
            "INSERT INTO identities (id, user_id, provider_key, issuer, subject, status) "
            "VALUES (%s, %s, %s, %s, %s, 'ACTIVE')"
        )
        await connection.execute(insert_identity, (identity_id, user_id, "local", "https://issuer", "Subject"))
        await rejected(
            connection,
            insert_identity,
            (uuid4(), other_user_id, "local", "https://issuer", "Subject"),
            UniqueViolation,
        )
        # Equality is exact, including issuer case, trailing slash, subject case and provider.
        for provider, issuer, subject in (
            ("other", "https://issuer", "Subject"),
            ("local", "https://Issuer", "Subject"),
            ("local", "https://issuer/", "Subject"),
            ("local", "https://issuer", "subject"),
        ):
            await connection.execute(insert_identity, (uuid4(), user_id, provider, issuer, subject))
        long_key = ("源" * 2048, "人" * 256)
        await connection.execute(insert_identity, (uuid4(), user_id, "unicode", *long_key))
        await rejected(connection, insert_identity, (uuid4(), other_user_id, "unicode", *long_key), UniqueViolation)
        await rejected(
            connection,
            insert_identity,
            (uuid4(), uuid4(), "local", "https://issuer", "missing"),
            ForeignKeyViolation,
        )
        await rejected(connection, "UPDATE identities SET deleted_at = CURRENT_TIMESTAMP WHERE id = %s", (identity_id,))
        await connection.execute(
            "UPDATE identities SET status = 'DISABLED', deleted_at = CURRENT_TIMESTAMP WHERE id = %s", (identity_id,)
        )
        # A disabled or deleted mapping cannot be claimed by a second platform subject.
        await rejected(
            connection,
            insert_identity,
            (uuid4(), other_user_id, "local", "https://issuer", "Subject"),
            UniqueViolation,
        )

        insert_binding = "INSERT INTO subject_bindings (principal_type, principal_id, user_id) VALUES (%s, %s, %s)"
        await connection.execute(insert_binding, ("ADMIN_USER", source_id, user_id))
        await connection.execute(insert_binding, ("EMPLOYEE", source_id, other_user_id))
        await rejected(connection, insert_binding, ("ADMIN_USER", source_id, other_user_id), UniqueViolation)
        await rejected(connection, insert_binding, ("USER", source_id, user_id))
        await rejected(connection, insert_binding, ("EMPLOYEE", uuid4(), uuid4()), ForeignKeyViolation)

        cursor = await connection.execute("SELECT code, is_system, protected FROM roles ORDER BY code")
        assert await cursor.fetchall() == [
            ("AUDIT_READONLY", True, True),
            ("KB_ADMIN", True, True),
            ("SUPER_ADMIN", True, True),
        ]
        await connection.execute("INSERT INTO roles (id, code, name) VALUES (%s, 'CUSTOM', '自定义角色')", (role_id,))
        await rejected(
            connection,
            "INSERT INTO roles (id, code, name) VALUES (%s, 'CUSTOM', '重复')",
            (uuid4(),),
            UniqueViolation,
        )
        await rejected(connection, "DELETE FROM roles WHERE code = 'SUPER_ADMIN'")
        await rejected(connection, "UPDATE roles SET code = 'RENAMED' WHERE code = 'KB_ADMIN'")
        await rejected(connection, "UPDATE roles SET protected = false WHERE code = 'AUDIT_READONLY'")
        await rejected(connection, "UPDATE roles SET deleted_at = CURRENT_TIMESTAMP WHERE code = 'SUPER_ADMIN'")
        await rejected(connection, "TRUNCATE roles CASCADE")
        await rejected(connection, "UPDATE roles SET is_system = true WHERE code = 'CUSTOM'")
        await rejected(
            connection, "INSERT INTO roles (id, code, name) VALUES (%s, 'SUPER_ADMIN', '伪造系统角色')", (uuid4(),)
        )

        await connection.execute(
            "INSERT INTO permissions (id, code, resource, action) VALUES (%s, 'foundation_probe.read', 'foundation_probe', 'read')",
            (permission_id,),
        )
        await rejected(
            connection,
            "INSERT INTO permissions (id, code, resource, action) VALUES (%s, 'foundation_probe.read', 'foundation_probe', 'read')",
            (uuid4(),),
            UniqueViolation,
        )
        await rejected(
            connection,
            "INSERT INTO permissions (id, code, resource, action) VALUES (%s, 'foundation_probe.manage', 'foundation_probe', 'read')",
            (uuid4(),),
        )
        for table, columns, values in (
            ("user_roles", ("user_id", "role_id"), (user_id, role_id)),
            ("role_permissions", ("role_id", "permission_id"), (role_id, permission_id)),
        ):
            statement = sql.SQL("INSERT INTO {} ({}, {}) VALUES (%s, %s)").format(
                sql.Identifier(table), *(sql.Identifier(column) for column in columns)
            )
            await connection.execute(statement, values)
            await rejected(connection, statement, values, UniqueViolation)
            await rejected(connection, statement, (uuid4(), values[1]), ForeignKeyViolation)
            await rejected(connection, statement, (values[0], uuid4()), ForeignKeyViolation)
        await rejected(connection, "DELETE FROM users WHERE id = %s", (user_id,), ForeignKeyViolation)
        await rejected(connection, "DELETE FROM roles WHERE id = %s", (role_id,), ForeignKeyViolation)
        await rejected(connection, "DELETE FROM permissions WHERE id = %s", (permission_id,), ForeignKeyViolation)

        # Historical actor roles and object IDs intentionally do not FK to mutable resources.
        await connection.execute(
            "INSERT INTO audit_events (id, occurred_at, action, result, risk, request_id, actor_user_id, actor_role_ids) "
            "VALUES (%s, CURRENT_TIMESTAMP, 'iam.login', 'SUCCEEDED', 'LOW', %s, %s, %s)",
            (uuid4(), uuid4(), user_id, [role_id]),
        )
        await connection.execute(
            "INSERT INTO audit_events (id, occurred_at, action, result, risk, request_id) "
            "VALUES (%s, CURRENT_TIMESTAMP, 'iam.login', 'DENIED', 'MEDIUM', %s)",
            (uuid4(), uuid4()),
        )
        for statement in (
            "UPDATE audit_events SET risk = 'HIGH'",
            "DELETE FROM audit_events",
            "TRUNCATE audit_events",
        ):
            await rejected(connection, statement)
        await rejected(
            connection,
            "INSERT INTO audit_events (id, occurred_at, action, result, risk, request_id, actor_user_id) "
            "VALUES (%s, CURRENT_TIMESTAMP, 'iam.login', 'SUCCEEDED', 'LOW', %s, %s)",
            (uuid4(), uuid4(), uuid4()),
            ForeignKeyViolation,
        )
        await rejected(
            connection,
            "INSERT INTO audit_events (id, occurred_at, action, result, risk, request_id) "
            "VALUES (%s, CURRENT_TIMESTAMP, 'trace.reveal_identity', 'SUCCEEDED', 'HIGH', %s)",
            (uuid4(), uuid4()),
        )
        await rejected(
            connection,
            "INSERT INTO audit_events (id, occurred_at, action, result, risk, request_id, after_snapshot) "
            "VALUES (%s, CURRENT_TIMESTAMP, 'iam.login', 'FAILED', 'LOW', %s, '{}'::jsonb)",
            (uuid4(), uuid4()),
        )
        # A subject can be retired without destroying audit or mapping facts.
        await connection.execute(
            "UPDATE users SET status = 'DEPARTED', deleted_at = CURRENT_TIMESTAMP WHERE id = %s", (user_id,)
        )
        cursor = await connection.execute("SELECT count(*) FROM audit_events WHERE actor_user_id = %s", (user_id,))
        assert await cursor.fetchone() == (1,)

    async with postgres_transaction(settings) as connection:
        cursor = await connection.execute("SELECT created_at, updated_at FROM users WHERE id = %s", (other_user_id,))
        before = await cursor.fetchone()
        assert before is not None
        await connection.execute("UPDATE users SET display_name = '新名称' WHERE id = %s", (other_user_id,))
        cursor = await connection.execute("SELECT created_at, updated_at FROM users WHERE id = %s", (other_user_id,))
        after = await cursor.fetchone()
        assert after is not None and after[0] == before[0] and after[1] > before[1]

    # Two independent transactions race to claim one verified identity. PostgreSQL,
    # rather than a process lock or a check-before-insert, determines the sole winner.
    async def claim_identity(subject_user_id: UUID) -> bool:
        try:
            async with postgres_transaction(settings) as connection:
                await connection.execute("SET LOCAL lock_timeout = '5s'")
                await connection.execute(
                    insert_identity, (uuid4(), subject_user_id, "concurrent", "https://issuer", "same-subject")
                )
            return True
        except UniqueViolation:
            return False

    assert sorted(await asyncio.gather(claim_identity(user_id), claim_identity(other_user_id))) == [False, True]
