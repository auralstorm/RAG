"""Compose read-only audit use cases with current IAM/Policy and database error translation."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from psycopg import Error

from app.adapters.audit_query import PostgresAuditRepository
from app.adapters.postgres import postgres_transaction
from app.core.config import Settings
from app.modules.audit.application.queries import AuditService
from app.modules.audit.domain.queries import AuditRepository, AuditUnavailable
from app.modules.iam.application.rbac import RbacService


def create_audit_service(settings: Settings, rbac: RbacService | None) -> AuditService | None:
    if rbac is None:
        return None

    @asynccontextmanager
    async def transaction() -> AsyncGenerator[AuditRepository]:
        try:
            async with postgres_transaction(settings) as connection:
                await connection.execute("SET LOCAL lock_timeout='5s'")
                await connection.execute("SET LOCAL statement_timeout='5s'")
                yield PostgresAuditRepository(connection)
        except Error as error:
            raise AuditUnavailable() from error

    return AuditService(transaction, rbac.enforcer)
