"""Provision an explicit local test identity; never enable local identities in production."""

import argparse
import fcntl
import getpass
import json
import os
import secrets
from pathlib import Path
from uuid import uuid4

from app.adapters.postgres import postgres_conninfo
from app.core.config import load_settings
from app.modules.iam.infrastructure.local_identity import (
    LOCAL_ISSUER,
    LocalAccount,
    LocalIdentityConfig,
    password_hash,
    read_private_config,
)
from psycopg import Connection
from pydantic import SecretStr


def provision(username: str, password: str, applications: list[str], path: Path, display_name: str) -> None:
    """Create one new source mapping and account; conflicting usernames are never relinked."""
    path = path.absolute()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(path.with_name(path.name + ".lock"), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "r+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        _provision_locked(username, password, applications, path, display_name)


def _provision_locked(username: str, password: str, applications: list[str], path: Path, display_name: str) -> None:
    settings = load_settings()
    if settings.environment == "production":
        raise ValueError("Local test identities are not available in production")
    if not 12 <= len(password) <= 1024:
        raise ValueError("Use a local password between 12 and 1024 characters")
    if (
        not applications
        or not set(applications).issubset({"chat", "admin"})
        or not display_name.strip()
        or len(display_name) > 128
    ):
        raise ValueError("Explicit application permissions and a valid display name are required")
    existing = read_private_config(path) if path.exists() else None
    if existing and any(account.username == username for account in existing.accounts):
        raise ValueError("The local account already exists; no identity was changed")
    account = LocalAccount(username=username, subject=str(uuid4()), salt=secrets.token_hex(16), password_hash="0" * 64)
    account = account.model_copy(update={"password_hash": password_hash(password, account.salt)})
    configuration = LocalIdentityConfig(
        signing_key=existing.signing_key if existing else SecretStr(secrets.token_hex(48)),
        pseudonymization_key=existing.pseudonymization_key if existing else None,
        accounts=(*(existing.accounts if existing else ()), account),
    )
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + secrets.token_hex(8))
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w") as output:
            output.write(
                json.dumps(
                    {
                        "signing_key": configuration.signing_key.get_secret_value(),
                        **(
                            {"pseudonymization_key": configuration.pseudonymization_key.get_secret_value()}
                            if configuration.pseudonymization_key
                            else {}
                        ),
                        "accounts": [item.model_dump() for item in configuration.accounts],
                    }
                )
            )
        user_id, identity_id = uuid4(), uuid4()
        with Connection.connect(postgres_conninfo(settings)) as connection:
            connection.execute(
                "INSERT INTO users(id,display_name,status) VALUES (%s,%s,'ACTIVE')", (user_id, display_name)
            )
            connection.execute(
                "INSERT INTO identities(id,user_id,provider_key,issuer,subject,status) "
                "VALUES (%s,%s,'local',%s,%s,'ACTIVE')",
                (identity_id, user_id, LOCAL_ISSUER, account.subject),
            )
            for application in set(applications):
                connection.execute(
                    "INSERT INTO identity_applications VALUES (%s,%s,CURRENT_TIMESTAMP)", (identity_id, application)
                )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", required=True)
    parser.add_argument("--display-name", required=True)
    parser.add_argument("--application", choices=("chat", "admin"), nargs="+", required=True)
    parser.add_argument("--config", type=Path, default=Path(".poc-results/auth/local.json"))
    args = parser.parse_args()
    password = getpass.getpass("本地测试账号密码（不回显）：")
    provision(args.username, password, args.application, args.config, args.display_name)
    print(
        "Local identity provisioned. Set ENTERPRISE_RAG_LOCAL_IDENTITY_CONFIG_REF to the private configuration path and restart the API."
    )


if __name__ == "__main__":
    main()
