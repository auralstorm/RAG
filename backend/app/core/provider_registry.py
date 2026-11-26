"""Compose Provider registry operations with the current Admin PolicyEnforcer."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from psycopg import Error

from app.adapters.postgres import postgres_transaction
from app.core.config import Settings
from app.modules.iam.application.rbac import RbacService
from app.modules.model_gateway.application.providers import ProviderRegistryService
from app.modules.model_gateway.domain.registry import ProviderRepository, ProviderUnavailable
from app.modules.model_gateway.infrastructure.postgres_registry import PostgresProviderRepository
from app.modules.model_gateway.infrastructure.provider_secrets import (
    AesGcmProviderSecretCipher,
    read_provider_secrets_config,
)


def create_provider_registry(settings: Settings, rbac: RbacService | None) -> ProviderRegistryService | None:
    """Disable registry routes until both current policy and private encryption keys exist."""
    if rbac is None or settings.provider_secrets_config_ref is None:
        return None
    cipher = AesGcmProviderSecretCipher(read_provider_secrets_config(settings.provider_secrets_config_ref))

    @asynccontextmanager
    async def transaction() -> AsyncGenerator[ProviderRepository]:
        try:
            async with postgres_transaction(settings) as connection:
                await connection.execute("SET LOCAL lock_timeout='5s'")
                await connection.execute("SET LOCAL statement_timeout='5s'")
                yield PostgresProviderRepository(connection)
        except Error as error:
            raise ProviderUnavailable() from error

    return ProviderRegistryService(transaction, rbac.enforcer, cipher, settings.environment)
