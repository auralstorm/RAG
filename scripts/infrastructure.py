"""Manage only this repository's isolated development and test Compose projects."""

import argparse
import os
import secrets
import subprocess
from pathlib import Path
from typing import Literal

from app.core.config import load_settings
from dotenv import dotenv_values
from minio import Minio

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "infra/compose/compose.yaml"
type Profile = Literal["development", "test"]


def profile_file(profile: Profile) -> Path:
    return ROOT / "infra/compose" / f".env.{profile}"


def initialize_config(profile: Profile) -> Path:
    path = profile_file(profile)
    if path.exists():
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
        "ENTERPRISE_RAG_MINIO_ENDPOINT": f"127.0.0.1:{19000 + offset}",
        "ENTERPRISE_RAG_MINIO_ACCESS_KEY": "enterprise_rag",
        "ENTERPRISE_RAG_MINIO_SECRET_KEY": secrets.token_urlsafe(32),
        "ENTERPRISE_RAG_MINIO_BUCKET": "enterprise-rag",
        "ENTERPRISE_RAG_PHOENIX_URL": f"http://127.0.0.1:{16006 + offset}",
        "RABBITMQ_MANAGEMENT_PORT": str(15672 + offset),
        "ELASTICSEARCH_PORT": str(19200 + offset),
        "MINIO_PORT": str(19000 + offset),
        "MINIO_CONSOLE_PORT": str(19001 + offset),
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


def initialize_storage(profile: Profile) -> None:
    settings = load_settings(profile)
    client = Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key.get_secret_value(),
        secret_key=settings.minio_secret_key.get_secret_value(),
        secure=False,
        region="us-east-1",
    )
    if not client.bucket_exists(settings.minio_bucket):
        client.make_bucket(settings.minio_bucket, location="us-east-1")


def up(profile: Profile) -> None:
    initialize_config(profile)
    compose(profile, "config", "--quiet")
    image = dotenv_values(ROOT / "infra/compose/images.env").get("MINIO_IMAGE")
    if not image:
        raise ValueError("MinIO image is not configured")
    found = subprocess.run(["docker", "image", "inspect", image], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if found.returncode:
        compose(profile, "build", "minio")
    compose(profile, "up", "--detach", "--wait", "--wait-timeout", "240")
    initialize_storage(profile)
    print(f"{profile} dependencies are healthy; object storage initialization is complete.")


def reset(profile: Profile, *, confirmed: bool) -> None:
    if not confirmed:
        raise ValueError("Reset deletes only this profile's data volumes; pass --confirm-reset to request it")
    initialize_config(profile)
    compose(profile, "down", "--volumes")
    up(profile)


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
