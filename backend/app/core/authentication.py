"""Compose the IAM use cases without leaking database or provider adapters into API code."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Literal

from psycopg import Error

from app.adapters.iam_repository import PostgresAuthRepository, PostgresPlatformCredentialLookup
from app.adapters.postgres import postgres_transaction
from app.adapters.rbac import PostgresRbacRepository
from app.core.config import Settings
from app.modules.iam.application.login import LoginService
from app.modules.iam.application.rbac import RbacService
from app.modules.iam.application.sessions import SessionService
from app.modules.iam.domain.identity_providers import PasswordCredentials
from app.modules.iam.domain.rbac import RbacRepository
from app.modules.iam.domain.sessions import AuthenticationUnavailable, AuthRepository
from app.modules.iam.infrastructure.local_identity import LocalIdentityProvider, read_private_config
from app.modules.iam.infrastructure.platform_config import PlatformAuthConfig, read_platform_config
from app.modules.iam.infrastructure.platform_identity import PlatformIdentityProvider
from app.modules.iam.infrastructure.tokens import JwtSessionTokens
from app.modules.policy.application.enforcement import PolicyEnforcer


@dataclass(frozen=True)
class IamServices:
    sessions: SessionService | None = None
    rbac: RbacService | None = None
    password_login: LoginService[PasswordCredentials] | None = None
    password_login_mode: Literal["local", "platform"] | None = None


def create_iam_services(settings: Settings) -> IamServices:
    local = read_private_config(settings.local_identity_config_ref) if settings.local_identity_config_ref else None
    if settings.auth_platform_config_ref is not None:
        configuration = read_platform_config(settings.auth_platform_config_ref)
    elif local is not None and local.signing_key is not None:
        configuration = PlatformAuthConfig(
            signing_key=local.signing_key, pseudonymization_key=local.pseudonymization_key
        )
    elif local is not None:
        raise ValueError("Configured identities require a private platform authentication configuration")
    else:
        return IamServices()

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
        JwtSessionTokens(configuration.signing_key.get_secret_value()),
        access_seconds=settings.auth_access_seconds,
        session_seconds=settings.auth_session_seconds,
    )
    if local is not None:
        password_login = LoginService(
            sessions,
            LocalIdentityProvider(local),
            account_key=lambda credentials: credentials.username,
        )
        password_login_mode: Literal["local", "platform"] = "local"
    else:
        password_login = LoginService(
            sessions,
            PlatformIdentityProvider(PostgresPlatformCredentialLookup(settings)),
            account_key=lambda credentials: credentials.username.casefold(),
        )
        password_login_mode = "platform"
    if configuration.pseudonymization_key is None:
        return IamServices(
            sessions=sessions,
            password_login=password_login,
            password_login_mode=password_login_mode,
        )

    @asynccontextmanager
    async def policy_transaction() -> AsyncGenerator[RbacRepository]:
        try:
            async with postgres_transaction(settings) as connection:
                await connection.execute("SET LOCAL lock_timeout = '5s'")
                await connection.execute("SET LOCAL statement_timeout = '5s'")
                yield PostgresRbacRepository(connection)
        except Error as error:
            raise AuthenticationUnavailable() from error

    rbac = RbacService(
        policy_transaction,
        PolicyEnforcer(
            sessions,
            settings.environment,
            configuration.pseudonymization_key.get_secret_value().encode(),
        ),
    )
    return IamServices(
        sessions=sessions,
        rbac=rbac,
        password_login=password_login,
        password_login_mode=password_login_mode,
    )
