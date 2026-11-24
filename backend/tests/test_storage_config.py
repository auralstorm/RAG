"""Check legacy profile migration without rotating credentials or losing rollback data."""

from pathlib import Path

import pytest
from app.core.config import Settings
from dotenv import dotenv_values
from pydantic import SecretStr, ValidationError
from pydantic_settings import SettingsConfigDict

from scripts.infrastructure import migrate_storage_config


def test_legacy_profile_migration_preserves_credentials_and_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / ".env.test"
    original = (
        "# preserve comments and other passwords\n"
        "ENTERPRISE_RAG_POSTGRES_PASSWORD=unchanged\n"
        "ENTERPRISE_RAG_MINIO_ENDPOINT=127.0.0.1:29000\n"
        "ENTERPRISE_RAG_MINIO_ACCESS_KEY=legacy-app\n"
        "ENTERPRISE_RAG_MINIO_SECRET_KEY='secret $ with # space'\n"
        "ENTERPRISE_RAG_MINIO_BUCKET=legacy-bucket\n"
        "MINIO_PORT=29000\nMINIO_CONSOLE_PORT=29001\n"
    )
    path.write_text(original)
    migrate_storage_config(path)
    values = dotenv_values(path)
    assert values["ENTERPRISE_RAG_OBJECT_STORAGE_SECRET_KEY"] == "secret $ with # space"
    assert values["ENTERPRISE_RAG_OBJECT_STORAGE_BUCKET"] == "legacy-bucket"
    assert values["OBJECT_STORAGE_PORT"] == "29000"
    assert values["ENTERPRISE_RAG_POSTGRES_PASSWORD"] == "unchanged"
    assert path.read_text().startswith(original)
    backup = tmp_path / ".env.test.pre-rustfs"
    assert backup.read_text() == original
    assert path.stat().st_mode & 0o777 == 0o600
    assert backup.stat().st_mode & 0o777 == 0o600
    migrated = path.read_bytes()
    migrate_storage_config(path)
    assert path.read_bytes() == migrated
    assert backup.read_text() == original


def test_canonical_storage_names_take_precedence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / ".env.test"
    path.write_text("ENTERPRISE_RAG_MINIO_BUCKET=legacy\nENTERPRISE_RAG_OBJECT_STORAGE_BUCKET=chosen\n")
    migrate_storage_config(path)
    assert dotenv_values(path)["ENTERPRISE_RAG_OBJECT_STORAGE_BUCKET"] == "chosen"

    class ProfileSettings(Settings):
        model_config = SettingsConfigDict(env_file=path)

    assert ProfileSettings().object_storage_bucket == "chosen"
    monkeypatch.setenv("ENTERPRISE_RAG_MINIO_BUCKET", "legacy")
    assert ProfileSettings().object_storage_bucket == "legacy"
    monkeypatch.setenv("ENTERPRISE_RAG_OBJECT_STORAGE_BUCKET", "chosen")
    assert ProfileSettings().object_storage_bucket == "chosen"


def test_empty_legacy_credential_does_not_rewrite_profile(tmp_path: Path) -> None:
    path = tmp_path / ".env.test"
    original = "ENTERPRISE_RAG_MINIO_SECRET_KEY=\n"
    path.write_text(original)
    with pytest.raises(ValueError, match="ENTERPRISE_RAG_MINIO_SECRET_KEY"):
        migrate_storage_config(path)
    assert path.read_text() == original


def test_missing_storage_secret_fails_closed_without_exposing_other_secrets() -> None:
    with pytest.raises(ValidationError) as failure:
        Settings(
            infrastructure_enabled=True,
            postgres_password=SecretStr("private-pg-secret"),
            redis_password=SecretStr("private-cache-secret"),
            rabbitmq_password=SecretStr("private-mq-secret"),
            object_storage_access_key=SecretStr("private-access-key"),
            object_storage_secret_key=SecretStr(""),
        )
    assert "object_storage_secret_key" in str(failure.value)
    assert "private-pg-secret" not in str(failure.value)
