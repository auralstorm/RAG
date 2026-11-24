"""Validated environment configuration."""

from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Load the application configuration without connecting external services."""

    model_config = SettingsConfigDict(env_prefix="ENTERPRISE_RAG_", env_file=".env", extra="ignore")

    app_name: str = "EnterpriseRag"
    environment: Literal["development", "test", "production"] = "development"
    cors_origins: list[str] = ["http://127.0.0.1:5173", "http://127.0.0.1:5174"]

    @field_validator("cors_origins")
    @classmethod
    def require_explicit_origins(cls, origins: list[str]) -> list[str]:
        if "*" in origins:
            raise ValueError("CORS requires explicit origins")
        return origins
