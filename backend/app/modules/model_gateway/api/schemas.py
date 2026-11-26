"""Admin Provider DTOs: editable routing settings never include private secret references."""

from typing import Literal, Self
from uuid import UUID

from app.api.schemas.common import HttpContract, PaginationQuery
from app.modules.model_gateway.domain.contracts import Provider, RegistryStatus
from app.modules.policy.domain.contracts import PolicyVersion
from pydantic import AnyHttpUrl, Field, HttpUrl, SecretStr, field_validator, model_validator


def validate_provider_url(url: HttpUrl) -> HttpUrl:
    if url.username is not None or url.password is not None or url.query is not None or url.fragment is not None:
        raise ValueError("Provider endpoints cannot contain credentials, query parameters or fragments")
    return url


def validate_proxy_url(value: SecretStr | None) -> SecretStr | None:
    if value is None:
        return None
    url = AnyHttpUrl(value.get_secret_value())
    if url.query is not None or url.fragment is not None:
        raise ValueError("Proxy URLs cannot contain query parameters or fragments")
    return value


class ProviderQuery(PaginationQuery):
    name: str | None = Field(default=None, max_length=128)
    provider_type: str | None = Field(default=None, max_length=64)
    status: RegistryStatus | None = None


class ProviderAdminView(Provider):
    """Permission-bound management projection; secrets and opaque references stay private."""

    base_url: HttpUrl
    timeout_seconds: int = Field(gt=0, le=300, strict=True)
    proxy_configured: bool = Field(strict=True)
    remarks: str = Field(max_length=1000)

    @field_validator("base_url")
    @classmethod
    def require_safe_endpoint(cls, url: HttpUrl) -> HttpUrl:
        return validate_provider_url(url)


class ProviderMutation(HttpContract):
    expected_policy_version: PolicyVersion
    confirm: Literal[True]

    @field_validator("name", check_fields=False)
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Provider name is empty")
        return value.strip() if value is not None else None

    @field_validator("credential", check_fields=False)
    @classmethod
    def require_header_safe_credential(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and not all(33 <= ord(char) <= 126 for char in value.get_secret_value()):
            raise ValueError("Provider credential must contain visible ASCII characters only")
        return value


class ProviderVersionMutation(ProviderMutation):
    expected_config_version: UUID


class CreateProvider(ProviderMutation):
    name: str = Field(min_length=1, max_length=128, pattern=r"\S")
    provider_type: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    base_url: HttpUrl
    timeout_seconds: int = Field(gt=0, le=300, strict=True)
    remarks: str = Field(default="", max_length=1000)
    credential: SecretStr | None = Field(default=None, min_length=1, max_length=4096, repr=False)
    proxy_url: SecretStr | None = Field(default=None, min_length=1, max_length=2048, repr=False)

    @field_validator("base_url")
    @classmethod
    def require_safe_endpoint(cls, url: HttpUrl) -> HttpUrl:
        return validate_provider_url(url)

    @field_validator("proxy_url")
    @classmethod
    def require_safe_proxy(cls, value: SecretStr | None) -> SecretStr | None:
        return validate_proxy_url(value)


class UpdateProvider(ProviderVersionMutation):
    name: str | None = Field(default=None, min_length=1, max_length=128, pattern=r"\S")
    provider_type: str | None = Field(default=None, min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    base_url: HttpUrl | None = None
    timeout_seconds: int | None = Field(default=None, gt=0, le=300, strict=True)
    status: RegistryStatus | None = None
    credential: SecretStr | None = Field(default=None, min_length=1, max_length=4096, repr=False)
    proxy_url: SecretStr | None = Field(default=None, min_length=1, max_length=2048, repr=False)
    remarks: str | None = Field(default=None, max_length=1000)
    clear_proxy: bool = Field(default=False, strict=True)

    @field_validator("base_url")
    @classmethod
    def require_safe_endpoint(cls, url: HttpUrl | None) -> HttpUrl | None:
        return validate_provider_url(url) if url is not None else None

    @field_validator("proxy_url")
    @classmethod
    def require_safe_proxy(cls, value: SecretStr | None) -> SecretStr | None:
        return validate_proxy_url(value)

    @model_validator(mode="after")
    def require_update(self) -> Self:
        changed = self.model_fields_set - {
            "expected_policy_version",
            "expected_config_version",
            "confirm",
            "clear_proxy",
        }
        if any(getattr(self, field) is None for field in changed):
            raise ValueError("Omit unchanged fields instead of submitting null")
        if not changed and not self.clear_proxy:
            raise ValueError("Provider update must include a changed field")
        if self.clear_proxy and self.proxy_url is not None:
            raise ValueError("A proxy cannot be replaced and cleared in the same request")
        return self


class ProviderPageResponse(HttpContract):
    items: list[ProviderAdminView]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)

    @model_validator(mode="after")
    def require_page_bounds(self) -> Self:
        if len(self.items) > self.page_size or len(self.items) > self.total:
            raise ValueError("Provider page exceeds its declared bounds")
        return self
