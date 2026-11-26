"""Authorized Provider CRUD with encrypted secrets and atomic append-only audit."""

import hmac
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from ipaddress import IPv4Address, IPv6Address
from uuid import UUID, uuid4

from pydantic import HttpUrl, SecretStr

from app.modules.audit.application.recording import security_event
from app.modules.audit.domain.contracts import AuditAction, AuditEvent, AuditResult, AuditSnapshot
from app.modules.audit.domain.recording import AuditContext
from app.modules.iam.domain.rbac import AuthorizationDenied, RbacConflict
from app.modules.iam.domain.sessions import AuthenticationDenied
from app.modules.model_gateway.domain.contracts import RegistryStatus, SecretReference, StoredProvider
from app.modules.model_gateway.domain.registry import (
    EncryptedSecretValue,
    ProviderConflict,
    ProviderNotFound,
    ProviderPage,
    ProviderRepository,
    ProviderSecretCipher,
    ProviderTransaction,
    RegisteredProvider,
)
from app.modules.policy.application.enforcement import Authority, PolicyEnforcer
from app.modules.policy.domain.contracts import Environment


@dataclass(frozen=True)
class ProviderMutationContext:
    expected_version: str
    request_id: UUID
    trace_id: str
    csrf_token: str = field(repr=False)
    ip_address: IPv4Address | IPv6Address | None = field(default=None, repr=False)


class ProviderRegistryService:
    def __init__(
        self,
        transactions: ProviderTransaction,
        enforcer: PolicyEnforcer,
        cipher: ProviderSecretCipher,
        environment: Environment,
    ) -> None:
        self.transactions = transactions
        self.enforcer = enforcer
        self.cipher = cipher
        self.environment: Environment = environment

    async def denied_mutation(self, context: AuditContext, provider_id: UUID | None = None) -> None:
        """Append a pre-authentication denial without inventing an actor."""
        async with self.transactions() as repository:
            await repository.audit(
                security_event(
                    context,
                    AuditAction.PROVIDER_CHANGE,
                    AuditResult.DENIED,
                    object_id=provider_id,
                )
            )

    @staticmethod
    def _snapshot(provider: StoredProvider) -> AuditSnapshot:
        # Config versions are generated UUIDs so audit snapshots identify the exact edit without values.
        return AuditSnapshot(
            enabled=provider.status is RegistryStatus.ACTIVE,
            proxy_configured=provider.proxy_ref is not None,
            configuration_id=UUID(provider.config_version),
            credential_present=provider.has_credential,
        )

    @asynccontextmanager
    async def _write(
        self,
        token: str,
        context: ProviderMutationContext,
        provider_id: UUID | None,
    ) -> AsyncGenerator[tuple[ProviderRepository, Authority], None]:
        failure: (
            AuthenticationDenied | AuthorizationDenied | RbacConflict | ProviderConflict | ProviderNotFound | None
        ) = None
        authority: Authority | None = None
        async with self.transactions() as repository:
            current_version = await repository.policy_version(write=True)
            try:
                authority = await self.enforcer.load(repository, "admin", token, current_version)
                async with repository.savepoint():
                    self.enforcer.require(authority, "provider.manage")
                    if not hmac.compare_digest(context.csrf_token, authority.session.csrf_token):
                        raise AuthorizationDenied()
                    if context.expected_version != current_version:
                        raise RbacConflict()
                    yield repository, authority
                    self.enforcer.require(authority, "provider.manage")
            except (
                AuthenticationDenied,
                AuthorizationDenied,
                RbacConflict,
                ProviderConflict,
                ProviderNotFound,
            ) as error:
                failure = error
                result = (
                    AuditResult.FAILED
                    if isinstance(error, (RbacConflict, ProviderConflict, ProviderNotFound))
                    else AuditResult.DENIED
                )
                await repository.audit(
                    security_event(
                        AuditContext(context.request_id, context.trace_id, context.ip_address),
                        AuditAction.PROVIDER_CHANGE,
                        result,
                        actor_user_id=authority.session.user.id if authority is not None else None,
                        roles=tuple(item.role for item in authority.roles) if authority is not None else (),
                        object_id=provider_id,
                    )
                )
        if failure is not None:
            raise failure

    async def list_providers(
        self,
        token: str,
        *,
        page: int,
        page_size: int,
        name: str | None = None,
        provider_type: str | None = None,
        status: RegistryStatus | None = None,
    ) -> ProviderPage:
        if page < 1 or not 1 <= page_size <= 100:
            raise ValueError("Provider listing requires bounded pagination")
        async with self.transactions() as repository:
            authority = await self.enforcer.load(
                repository, "admin", token, await repository.policy_version(write=False)
            )
            self.enforcer.require(authority, "provider.read")
            result = await repository.providers(
                page=page,
                page_size=page_size,
                name=name,
                provider_type=provider_type,
                status=status,
            )
            self.enforcer.require(authority, "provider.read")
            return result

    async def get_provider(self, token: str, provider_id: UUID) -> RegisteredProvider:
        async with self.transactions() as repository:
            authority = await self.enforcer.load(
                repository, "admin", token, await repository.policy_version(write=False)
            )
            self.enforcer.require(authority, "provider.read")
            provider = await repository.provider(provider_id)
            self.enforcer.require(authority, "provider.read")
            if provider is None:
                raise ProviderNotFound()
            return provider

    def _encrypt(self, reference: SecretReference | None, value: SecretStr | None) -> EncryptedSecretValue | None:
        if reference is None or value is None:
            return None
        return self.cipher.encrypt(reference, value)

    def _secret_reference(self, secret_id: UUID | None = None, version: int = 1) -> SecretReference:
        return SecretReference(
            secret_id=secret_id or uuid4(),
            version=version,
            environment=self.environment,
        )

    async def create_provider(
        self,
        token: str,
        context: ProviderMutationContext,
        *,
        name: str,
        provider_type: str,
        base_url: HttpUrl,
        timeout_seconds: int,
        credential: SecretStr | None,
        proxy_url: SecretStr | None,
        remarks: str,
    ) -> RegisteredProvider:
        async with self._write(token, context, None) as (repository, _authority):
            provider_id = uuid4()
            credential_ref = self._secret_reference() if credential is not None else None
            proxy_id = uuid4() if proxy_url is not None else None
            proxy_secret_ref = self._secret_reference() if proxy_url is not None else None
            credential_value = self._encrypt(credential_ref, credential)
            proxy_value = self._encrypt(proxy_secret_ref, proxy_url)
            now = datetime.now(UTC)
            now_provider = RegisteredProvider.model_validate(
                {
                    "id": provider_id,
                    "name": name,
                    "remarks": remarks,
                    "provider_type": provider_type,
                    "config_version": str(uuid4()),
                    "status": RegistryStatus.ACTIVE,
                    "has_credential": credential_ref is not None,
                    "created_at": now,
                    "updated_at": now,
                    "base_url": base_url,
                    "credential_ref": credential_ref,
                    "proxy_ref": proxy_id,
                    "timeout_seconds": timeout_seconds,
                }
            )
            proxy = (
                (proxy_id, proxy_secret_ref, proxy_value)
                if proxy_id is not None and proxy_secret_ref is not None and proxy_value is not None
                else None
            )
            await repository.create_provider(now_provider, credential_value, proxy)
            await repository.audit(self._success_event(context, _authority, None, now_provider))
        return now_provider

    async def update_provider(
        self,
        token: str,
        context: ProviderMutationContext,
        provider_id: UUID,
        *,
        name: str | None,
        provider_type: str | None,
        base_url: HttpUrl | None,
        timeout_seconds: int | None,
        status: RegistryStatus | None,
        credential: SecretStr | None,
        proxy_url: SecretStr | None,
        clear_proxy: bool,
        remarks: str | None,
        expected_config_version: UUID,
    ) -> RegisteredProvider:
        async with self._write(token, context, provider_id) as (repository, authority):
            current = await repository.provider(provider_id, lock=True)
            if current is None:
                raise ProviderNotFound()
            if current.config_version != str(expected_config_version):
                raise ProviderConflict()
            credential_ref = current.credential_ref
            credential_value = None
            if credential is not None:
                credential_ref = self._secret_reference(
                    credential_ref.secret_id if credential_ref is not None else None,
                    credential_ref.version + 1 if credential_ref is not None else 1,
                )
                credential_value = self._encrypt(credential_ref, credential)
            proxy: tuple[UUID, SecretReference, EncryptedSecretValue] | None = None
            proxy_ref = current.proxy_ref
            if clear_proxy:
                proxy_ref = None
            elif proxy_url is not None:
                proxy_ref = uuid4()
                proxy_secret_ref = self._secret_reference()
                proxy_value = self._encrypt(proxy_secret_ref, proxy_url)
                if proxy_value is not None:
                    proxy = (proxy_ref, proxy_secret_ref, proxy_value)
            updated = RegisteredProvider.model_validate(
                current.model_dump(mode="python")
                | {
                    "name": name if name is not None else current.name,
                    "remarks": remarks if remarks is not None else current.remarks,
                    "provider_type": provider_type if provider_type is not None else current.provider_type,
                    "base_url": base_url if base_url is not None else current.base_url,
                    "timeout_seconds": timeout_seconds if timeout_seconds is not None else current.timeout_seconds,
                    "status": status if status is not None else current.status,
                    "config_version": str(uuid4()),
                    "updated_at": datetime.now(UTC),
                    "credential_ref": credential_ref,
                    "has_credential": credential_ref is not None,
                    "proxy_ref": proxy_ref,
                }
            )
            await repository.update_provider(
                updated,
                credential=credential_value,
                proxy=proxy,
            )
            await repository.audit(self._success_event(context, authority, current, updated))
        return updated

    async def delete_provider(
        self, token: str, context: ProviderMutationContext, provider_id: UUID, expected_config_version: UUID
    ) -> None:
        async with self._write(token, context, provider_id) as (repository, authority):
            current = await repository.provider(provider_id, lock=True)
            if current is None:
                raise ProviderNotFound()
            if current.config_version != str(expected_config_version):
                raise ProviderConflict()
            archived = RegisteredProvider.model_validate(
                current.model_dump(mode="python")
                | {
                    "status": RegistryStatus.DISABLED,
                    "config_version": str(uuid4()),
                    "updated_at": datetime.now(UTC),
                }
            )
            await repository.archive_provider(archived)
            await repository.audit(self._success_event(context, authority, current, None))

    def _success_event(
        self,
        context: ProviderMutationContext,
        authority: Authority,
        before: StoredProvider | None,
        after: StoredProvider | None,
    ) -> AuditEvent:
        target = after if after is not None else before
        return security_event(
            AuditContext(context.request_id, context.trace_id, context.ip_address),
            AuditAction.PROVIDER_CHANGE,
            AuditResult.SUCCEEDED,
            actor_user_id=authority.session.user.id,
            roles=tuple(item.role for item in authority.roles),
            object_id=target.id if target is not None else None,
            before=self._snapshot(before) if before is not None else None,
            after=self._snapshot(after) if after is not None else None,
        )
