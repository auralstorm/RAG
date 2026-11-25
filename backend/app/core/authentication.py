"""Compose the IAM use cases without leaking database or provider adapters into API code."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from psycopg import Error

from app.adapters.postgres import postgres_transaction
from app.core.config import Settings
from app.modules.iam.application.sessions import SessionService
from app.modules.iam.domain.sessions import AuthenticationUnavailable, AuthRepository
from app.modules.iam.infrastructure.local_identity import LocalIdentityProvider, read_private_config
from app.modules.iam.infrastructure.repositories import PostgresAuthRepository
from app.modules.iam.infrastructure.tokens import JwtSessionTokens


def create_session_service(settings: Settings) -> SessionService | None:
    if settings.local_identity_config_ref is None:
        return None
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

    return SessionService(
        transaction,
        LocalIdentityProvider(configuration),
        JwtSessionTokens(configuration.signing_key.get_secret_value()),
        access_seconds=settings.auth_access_seconds,
        session_seconds=settings.auth_session_seconds,
    )
