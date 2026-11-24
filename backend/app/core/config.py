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
    dependency_timeout: float = Field(default=2.0, gt=0, le=10)
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

    @field_validator("cors_origins")
    @classmethod
    def require_explicit_origins(cls, origins: list[str]) -> list[str]:
        if "*" in origins:
            raise ValueError("CORS requires explicit origins")
        return origins


PROJECT_ROOT = Path(__file__).resolve().parents[3]


class DevelopmentSettings(Settings):
    model_config = SettingsConfigDict(env_file=(PROJECT_ROOT / ".env", PROJECT_ROOT / "infra/compose/.env.development"))


class TestSettings(Settings):
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / "infra/compose/.env.test")


def load_settings(profile: Literal["development", "test"] | None = None) -> Settings:
    """Load the selected local profile, with process environment taking precedence."""
    selected = profile or os.getenv("ENTERPRISE_RAG_INFRA_PROFILE", "development")
    if selected not in ("development", "test"):
        raise ValueError("Local infrastructure profile must be development or test")
    return TestSettings() if selected == "test" else DevelopmentSettings()
