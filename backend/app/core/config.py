"""Validated environment configuration."""

import os
from pathlib import Path
from typing import Literal, Self

from pydantic import AliasChoices, AnyHttpUrl, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Load the application configuration without connecting external services."""

    model_config = SettingsConfigDict(
        env_prefix="ENTERPRISE_RAG_",
        env_file=".env",
        extra="ignore",
        hide_input_in_errors=True,
        populate_by_name=True,
    )

    app_name: str = "EnterpriseRag"
    environment: Literal["development", "test", "production"] = "development"
    cors_origins: list[str] = ["http://127.0.0.1:5173", "http://127.0.0.1:5174"]
    infrastructure_enabled: bool = False
    local_identity_config_ref: Path | None = None
    auth_platform_config_ref: Path | None = Field(default=None, repr=False)
    provider_secrets_config_ref: Path | None = Field(default=None, repr=False)
    auth_access_seconds: int = Field(default=900, ge=60, le=900)
    auth_session_seconds: int = Field(default=86400, ge=900, le=604800)
    auth_chat_origins: list[str] = ["http://127.0.0.1:5173", "http://127.0.0.1:4173"]
    auth_admin_origins: list[str] = ["http://127.0.0.1:5174", "http://127.0.0.1:4174"]
    dependency_timeout: float = Field(default=2.0, gt=0, le=10)
    telemetry_enabled: bool = True
    telemetry_trace_export_enabled: bool = False
    telemetry_credentials_ref: Path | None = Field(default=None, repr=False)
    telemetry_otlp_endpoint: AnyHttpUrl = AnyHttpUrl("http://127.0.0.1:14317")
    telemetry_sample_ratio: float = Field(default=1.0, ge=0, le=1)
    telemetry_interval_seconds: float = Field(default=30.0, ge=5, le=300)
    telemetry_queues: list[str] = Field(default_factory=list, max_length=20)
    postgres_host: str = "127.0.0.1"
    postgres_port: int = Field(default=15432, ge=1, le=65535)
    postgres_user: str = "enterprise_rag"
    postgres_database: str = "enterprise_rag"
    postgres_password: SecretStr = SecretStr("")
    redis_host: str = "127.0.0.1"
    redis_port: int = Field(default=16379, ge=1, le=65535)
    redis_password: SecretStr = SecretStr("")
    rabbitmq_host: str = "127.0.0.1"
    rabbitmq_port: int = Field(default=15673, ge=1, le=65535)
    rabbitmq_user: str = "enterprise_rag"
    rabbitmq_password: SecretStr = SecretStr("")
    elasticsearch_url: AnyHttpUrl = AnyHttpUrl("http://127.0.0.1:19200")
    object_storage_endpoint: str = Field(
        default="127.0.0.1:19000",
        validation_alias=AliasChoices("ENTERPRISE_RAG_OBJECT_STORAGE_ENDPOINT", "ENTERPRISE_RAG_MINIO_ENDPOINT"),
    )
    object_storage_access_key: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices("ENTERPRISE_RAG_OBJECT_STORAGE_ACCESS_KEY", "ENTERPRISE_RAG_MINIO_ACCESS_KEY"),
    )
    object_storage_secret_key: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices("ENTERPRISE_RAG_OBJECT_STORAGE_SECRET_KEY", "ENTERPRISE_RAG_MINIO_SECRET_KEY"),
    )
    object_storage_bucket: str = Field(
        default="enterprise-rag",
        validation_alias=AliasChoices("ENTERPRISE_RAG_OBJECT_STORAGE_BUCKET", "ENTERPRISE_RAG_MINIO_BUCKET"),
    )
    phoenix_url: AnyHttpUrl = AnyHttpUrl("http://127.0.0.1:16006")

    @model_validator(mode="after")
    def require_local_credentials(self) -> Self:
        if self.telemetry_trace_export_enabled and not self.telemetry_enabled:
            raise ValueError("Trace export requires telemetry to be enabled")
        if self.telemetry_trace_export_enabled and self.telemetry_credentials_ref is None:
            raise ValueError("Trace export requires a private collector credential reference")
        if self.environment == "production" and self.local_identity_config_ref is not None:
            raise ValueError("Local test identities are not available in production")
        if self.infrastructure_enabled:
            for name in (
                "postgres_password",
                "redis_password",
                "rabbitmq_password",
                "object_storage_access_key",
                "object_storage_secret_key",
            ):
                secret: SecretStr = getattr(self, name)
                if not secret.get_secret_value():
                    raise ValueError(f"Infrastructure credential is missing: {name}")
        return self

    @field_validator("cors_origins", "auth_chat_origins", "auth_admin_origins")
    @classmethod
    def require_explicit_origins(cls, origins: list[str]) -> list[str]:
        if "*" in origins:
            raise ValueError("CORS requires explicit origins")
        return origins

    @field_validator("telemetry_otlp_endpoint")
    @classmethod
    def require_technical_endpoint(cls, endpoint: AnyHttpUrl) -> AnyHttpUrl:
        if (
            endpoint.username
            or endpoint.password
            or endpoint.query
            or endpoint.fragment
            or endpoint.path not in {None, "/"}
        ):
            raise ValueError("OTLP gRPC endpoint requires a host/port without credentials or request parameters")
        return endpoint

    @field_validator("telemetry_queues")
    @classmethod
    def require_bounded_queues(cls, queues: list[str]) -> list[str]:
        if len(set(queues)) != len(queues) or any(not queue or len(queue) > 128 for queue in queues):
            raise ValueError("Observed queues require unique, bounded server configuration names")
        return queues


PROJECT_ROOT = Path(__file__).resolve().parents[3]


class DevelopmentSettings(Settings):
    model_config = SettingsConfigDict(env_file=(PROJECT_ROOT / ".env", PROJECT_ROOT / "infra/compose/.env.development"))


class TestSettings(Settings):
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / "infra/compose/.env.test")
    telemetry_otlp_endpoint: AnyHttpUrl = AnyHttpUrl("http://127.0.0.1:24317")


def load_settings(profile: Literal["development", "test"] | None = None) -> Settings:
    """Load the selected local profile, with process environment taking precedence."""
    selected = profile or os.getenv("ENTERPRISE_RAG_INFRA_PROFILE", "development")
    if selected not in ("development", "test"):
        raise ValueError("Local infrastructure profile must be development or test")
    return TestSettings() if selected == "test" else DevelopmentSettings()
