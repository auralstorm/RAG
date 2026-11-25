"""Compose the IAM use cases without leaking database or provider adapters into API code."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from psycopg import Error

from app.adapters.postgres import postgres_transaction
from app.adapters.rbac import PostgresRbacRepository
from app.core.config import Settings
from app.modules.iam.application.rbac import RbacService
from app.modules.iam.application.sessions import SessionService
from app.modules.iam.domain.rbac import RbacRepository
from app.modules.iam.domain.sessions import AuthenticationUnavailable, AuthRepository
from app.modules.iam.infrastructure.local_identity import LocalIdentityProvider, read_private_config
from app.modules.iam.infrastructure.repositories import PostgresAuthRepository
from app.modules.iam.infrastructure.tokens import JwtSessionTokens
from app.modules.policy.application.enforcement import PolicyEnforcer


def create_iam_services(settings: Settings) -> tuple[SessionService | None, RbacService | None]:
    if settings.local_identity_config_ref is None:
        return None, None
    configuration = read_private_config(settings.local_identity_config_ref)

    @asynccontextmanager
    async def transaction() -> AsyncGenerator[AuthRepository]:
        try:
            async with postgres_transaction(settings) as connection:
                await connection.execute("SET LOCAL lock_timeout = '5s'")
                await connection.execute("SET LOCAL statement_timeout = '5s'")
                yield PostgresAuthRepository(connection)
        except Error as error:
            raise AuthenticationUnavailable() from error

    sessions = SessionService(
        transaction,
        LocalIdentityProvider(configuration),
        JwtSessionTokens(configuration.signing_key.get_secret_value()),
        access_seconds=settings.auth_access_seconds,
        session_seconds=settings.auth_session_seconds,
    )
    if configuration.pseudonymization_key is None:
        return sessions, None

    @asynccontextmanager
    async def policy_transaction() -> AsyncGenerator[RbacRepository]:
        try:
            async with postgres_transaction(settings) as connection:
                await connection.execute("SET LOCAL lock_timeout = '5s'")
                await connection.execute("SET LOCAL statement_timeout = '5s'")
                yield PostgresRbacRepository(connection)
        except Error as error:
            raise AuthenticationUnavailable() from error

    return sessions, RbacService(
        policy_transaction,
        PolicyEnforcer(
            sessions,
            settings.environment,
            configuration.pseudonymization_key.get_secret_value().encode(),
        ),
    )
