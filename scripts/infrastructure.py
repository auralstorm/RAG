"""Manage only this repository's isolated development and test Compose projects."""

import argparse
import os
import secrets
import subprocess
from pathlib import Path
from typing import Literal

from app.adapters.object_storage import open_s3_client
from app.core.config import Settings, load_settings
from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "infra/compose/compose.yaml"
type Profile = Literal["development", "test"]


def profile_file(profile: Profile) -> Path:
    return ROOT / "infra/compose" / f".env.{profile}"


def migrate_storage_config(path: Path) -> None:
    """Append canonical S3 names, preserving legacy credentials and a private backup.

    This migrates configuration only. Source data volumes are never mounted or deleted.
    Existing canonical values take precedence, including explicit empty values.
    """
    values = dotenv_values(path)
    names = {
        **{
            f"ENTERPRISE_RAG_OBJECT_STORAGE_{name}": f"ENTERPRISE_RAG_MINIO_{name}"
            for name in ("ENDPOINT", "ACCESS_KEY", "SECRET_KEY", "BUCKET")
        },
        "OBJECT_STORAGE_PORT": "MINIO_PORT",
        "OBJECT_STORAGE_CONSOLE_PORT": "MINIO_CONSOLE_PORT",
    }
    additions: dict[str, str] = {}
    for target, source in names.items():
        if target not in values and source in values:
            value = values[source]
            if not value:
                raise ValueError(f"Legacy storage configuration is missing: {source}")
            additions[target] = value
    if not additions:
        return
    backup = path.with_name(f"{path.name}.pre-rustfs")
    original = path.read_text()
    if not backup.exists():
        descriptor = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as output:
            output.write(original)

    # dotenv single quotes keep spaces, dollar signs and comment characters literal.
    def quote(value: str) -> str:
        return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"

    temporary = path.with_name(f"{path.name}.rustfs-tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as output:
        output.write(
            original.rstrip("\n") + "\n\n# S3 configuration migrated for RustFS; legacy values retained for rollback.\n"
        )
        output.write("\n".join(f"{key}={quote(value)}" for key, value in additions.items()) + "\n")
    os.replace(temporary, path)


def initialize_config(profile: Profile) -> Path:
    path = profile_file(profile)
    if path.exists():
        migrate_storage_config(path)
        load_settings(profile)
        return path
    offset = 0 if profile == "development" else 10000
    values: dict[str, str] = {
        "ENTERPRISE_RAG_ENVIRONMENT": profile,
        "ENTERPRISE_RAG_INFRASTRUCTURE_ENABLED": "true",
        "ENTERPRISE_RAG_POSTGRES_HOST": "127.0.0.1",
        "ENTERPRISE_RAG_POSTGRES_PORT": str(15432 + offset),
        "ENTERPRISE_RAG_POSTGRES_USER": "enterprise_rag",
        "ENTERPRISE_RAG_POSTGRES_DATABASE": "enterprise_rag",
        "ENTERPRISE_RAG_POSTGRES_PASSWORD": secrets.token_urlsafe(32),
        "ENTERPRISE_RAG_REDIS_HOST": "127.0.0.1",
        "ENTERPRISE_RAG_REDIS_PORT": str(16379 + offset),
        "ENTERPRISE_RAG_REDIS_PASSWORD": secrets.token_urlsafe(32),
        "ENTERPRISE_RAG_RABBITMQ_HOST": "127.0.0.1",
        "ENTERPRISE_RAG_RABBITMQ_PORT": str(15673 + offset),
        "ENTERPRISE_RAG_RABBITMQ_USER": "enterprise_rag",
        "ENTERPRISE_RAG_RABBITMQ_PASSWORD": secrets.token_urlsafe(32),
        "ENTERPRISE_RAG_ELASTICSEARCH_URL": f"http://127.0.0.1:{19200 + offset}",
        "ENTERPRISE_RAG_OBJECT_STORAGE_ENDPOINT": f"127.0.0.1:{19000 + offset}",
        "ENTERPRISE_RAG_OBJECT_STORAGE_ACCESS_KEY": "enterprise_rag",
        "ENTERPRISE_RAG_OBJECT_STORAGE_SECRET_KEY": secrets.token_urlsafe(32),
        "ENTERPRISE_RAG_OBJECT_STORAGE_BUCKET": "enterprise-rag",
        "ENTERPRISE_RAG_PHOENIX_URL": f"http://127.0.0.1:{16006 + offset}",
        "RABBITMQ_MANAGEMENT_PORT": str(15672 + offset),
        "ELASTICSEARCH_PORT": str(19200 + offset),
        "OBJECT_STORAGE_PORT": str(19000 + offset),
        "OBJECT_STORAGE_CONSOLE_PORT": str(19001 + offset),
        "PHOENIX_PORT": str(16006 + offset),
        "PHOENIX_GRPC_PORT": str(14317 + offset),
    }
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as output:
        output.write("\n".join(f"{key}={value}" for key, value in values.items()) + "\n")
    return path


def compose_command(profile: Profile, *arguments: str) -> list[str]:
    project = "enterprise-rag-dev" if profile == "development" else "enterprise-rag-test"
    return [
        "docker",
        "compose",
        "--project-name",
        project,
        "--file",
        str(COMPOSE),
        "--env-file",
        str(ROOT / "infra/compose/images.env"),
        "--env-file",
        str(profile_file(profile)),
        *arguments,
    ]


def compose(profile: Profile, *arguments: str) -> None:
    subprocess.run(compose_command(profile, *arguments), cwd=ROOT, check=True)


class StoragePort(BaseModel):
    target: int
    host_ip: str
    published: int


class StorageService(BaseModel):
    environment: dict[str, str]
    ports: list[StoragePort]


class StorageServices(BaseModel):
    rustfs: StorageService


class StorageComposeConfig(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True)

    services: StorageServices


def validate_storage_alignment(settings: Settings, service: StorageService) -> None:
    endpoints = {f"{port.host_ip}:{port.published}" for port in service.ports if port.target == 9000}
    if settings.object_storage_endpoint not in endpoints or (
        service.environment.get("RUSTFS_ACCESS_KEY") != settings.object_storage_access_key.get_secret_value()
        or service.environment.get("RUSTFS_SECRET_KEY") != settings.object_storage_secret_key.get_secret_value()
    ):
        raise ValueError(
            "Object storage settings disagree with local Compose. Use matching canonical "
            "OBJECT_STORAGE_* settings and remove conflicting MINIO_* overrides."
        )


def initialize_storage(settings: Settings) -> None:
    with open_s3_client(settings) as client:
        if not client.bucket_exists(settings.object_storage_bucket):
            client.make_bucket(settings.object_storage_bucket, location="us-east-1")


def prepare_local_storage(profile: Profile) -> Settings:
    initialize_config(profile)
    settings = load_settings(profile)
    rendered = subprocess.check_output(compose_command(profile, "config", "--format", "json", "rustfs"), cwd=ROOT)
    configuration = StorageComposeConfig.model_validate_json(rendered)
    validate_storage_alignment(settings, configuration.services.rustfs)
    return settings


def start_dependencies(profile: Profile, settings: Settings) -> None:
    compose(profile, "up", "--detach", "--wait", "--wait-timeout", "240")
    initialize_storage(settings)
    print(f"{profile} dependencies are healthy; object storage initialization is complete.")


def up(profile: Profile) -> None:
    start_dependencies(profile, prepare_local_storage(profile))


def reset(profile: Profile, *, confirmed: bool) -> None:
    if not confirmed:
        raise ValueError("Reset deletes only this profile's data volumes; pass --confirm-reset to request it")
    settings = prepare_local_storage(profile)
    compose(profile, "down", "--volumes")
    start_dependencies(profile, settings)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("up", "down", "status", "init", "reset"))
    parser.add_argument("--profile", choices=("development", "test"), default="development")
    parser.add_argument("--confirm-reset", action="store_true")
    arguments = parser.parse_args()
    profile: Profile = "test" if arguments.profile == "test" else "development"
    if arguments.action == "up":
        up(profile)
    elif arguments.action == "reset":
        reset(profile, confirmed=bool(arguments.confirm_reset))
    elif arguments.action == "init":
        initialize_config(profile)
    else:
        initialize_config(profile)
        compose(profile, "down" if arguments.action == "down" else "ps")


if __name__ == "__main__":
    main()
