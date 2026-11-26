"""Provider registry persistence and secret-encryption ports."""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

from pydantic import Field, SecretStr

from app.modules.iam.domain.rbac import RbacRepository
from app.modules.model_gateway.domain.contracts import RegistryStatus, SecretReference, StoredProvider


class ProviderConflict(ValueError):
    """The viewed Provider configuration has changed before a mutation."""


class ProviderNotFound(LookupError):
    """The requested provider does not exist."""


class ProviderUnavailable(RuntimeError):
    """Provider storage or the configured secret cipher is unavailable."""


class RegisteredProvider(StoredProvider):
    """Private registry record; remarks are management metadata, never call credentials."""

    remarks: str = Field(default="", max_length=1000)


@dataclass(frozen=True)
class ProviderPage:
    items: tuple[RegisteredProvider, ...]
    total: int


@dataclass(frozen=True)
class EncryptedSecretValue:
    key_version: str
    ciphertext: bytes = field(repr=False)


class ProviderSecretCipher(Protocol):
    """Encrypt credentials before they enter persistence; callers own secret references."""

    def encrypt(self, reference: SecretReference, value: SecretStr) -> EncryptedSecretValue: ...

    def decrypt(self, reference: SecretReference, value: EncryptedSecretValue) -> SecretStr: ...


class ProviderRepository(RbacRepository, Protocol):
    async def providers(
        self,
        *,
        page: int,
        page_size: int,
        name: str | None,
        provider_type: str | None,
        status: RegistryStatus | None,
    ) -> ProviderPage: ...

    async def provider(self, provider_id: UUID, *, lock: bool = False) -> RegisteredProvider | None: ...

    async def create_provider(
        self,
        provider: RegisteredProvider,
        credential: EncryptedSecretValue | None,
        proxy: tuple[UUID, SecretReference, EncryptedSecretValue] | None,
    ) -> None: ...

    async def update_provider(
        self,
        provider: RegisteredProvider,
        *,
        credential: EncryptedSecretValue | None,
        proxy: tuple[UUID, SecretReference, EncryptedSecretValue] | None,
    ) -> None: ...

    async def archive_provider(self, provider: RegisteredProvider) -> None: ...


type ProviderTransaction = Callable[[], AbstractAsyncContextManager[ProviderRepository]]
