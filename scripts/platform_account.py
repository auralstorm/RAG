"""Provision one database-backed platform account with Chat access by default."""

import argparse
import asyncio
import getpass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.adapters.audit_writer import PostgresAuditWriter
from app.adapters.postgres import postgres_transaction
from app.core.config import Settings, load_settings
from app.modules.audit.domain.contracts import AuditAction, AuditEvent, AuditResult, AuditRisk, AuditSnapshot
from app.modules.iam.domain.contracts import UserStatus
from app.modules.iam.domain.identity_providers import PLATFORM_ISSUER, PLATFORM_PROVIDER_KEY
from app.modules.iam.infrastructure.platform_config import read_platform_config
from app.modules.iam.infrastructure.platform_identity import hash_platform_password
from psycopg.errors import UniqueViolation


def validate_account(username: str, display_name: str, password: str) -> None:
    if not username or len(username) > 128 or username.strip() != username or not username.strip():
        raise ValueError("Username must contain 1 to 128 non-padding characters")
    if not display_name.strip() or len(display_name) > 128:
        raise ValueError("Display name must contain 1 to 128 non-whitespace characters")
    if not 12 <= len(password) <= 1024:
        raise ValueError("Use a password between 12 and 1024 characters")


async def provision(
    settings: Settings,
    username: str,
    display_name: str,
    password: str,
    *,
    admin_access: bool = False,
) -> UUID:
    """Create a user, platform identity, password verifier, app grants and audit atomically."""
    validate_account(username, display_name, password)
    if settings.auth_platform_config_ref is None:
        raise ValueError("Configure ENTERPRISE_RAG_AUTH_PLATFORM_CONFIG_REF before provisioning accounts")
    if settings.local_identity_config_ref is not None:
        raise ValueError("Disable the development-only local identity source before provisioning platform accounts")
    read_platform_config(settings.auth_platform_config_ref)

    user_id, identity_id, subject = uuid4(), uuid4(), str(uuid4())
    password_hash = await asyncio.to_thread(hash_platform_password, password)
    applications = ("chat", "admin") if admin_access else ("chat",)
    try:
        async with postgres_transaction(settings) as connection:
            await connection.execute("SET LOCAL lock_timeout = '5s'")
            await connection.execute("SET LOCAL statement_timeout = '5s'")
            await connection.execute(
                "INSERT INTO users(id,display_name,status) VALUES (%s,%s,'ACTIVE')", (user_id, display_name)
            )
            await connection.execute(
                "INSERT INTO identities(id,user_id,provider_key,issuer,subject,status) "
                "VALUES (%s,%s,%s,%s,%s,'ACTIVE')",
                (identity_id, user_id, PLATFORM_PROVIDER_KEY, PLATFORM_ISSUER, subject),
            )
            await connection.execute(
                "INSERT INTO platform_password_credentials(identity_id,username,password_hash) VALUES (%s,%s,%s)",
                (identity_id, username, password_hash),
            )
            for application in applications:
                await connection.execute(
                    "INSERT INTO identity_applications(identity_id,application) VALUES (%s,%s)",
                    (identity_id, application),
                )
            await PostgresAuditWriter(connection).audit(
                AuditEvent(
                    id=uuid4(),
                    occurred_at=datetime.now(UTC),
                    action=AuditAction.LIFECYCLE_CHANGE,
                    result=AuditResult.SUCCEEDED,
                    risk=AuditRisk.HIGH if admin_access else AuditRisk.MEDIUM,
                    request_id=uuid4(),
                    trace_id=uuid4().hex,
                    object_id=user_id,
                    after=AuditSnapshot(user_status=UserStatus.ACTIVE, application_access=applications),
                )
            )
    except UniqueViolation as error:
        raise ValueError("An account with this username already exists; no account was changed") from error
    return user_id


async def _run(args: argparse.Namespace, password: str) -> UUID:
    return await provision(
        load_settings(),
        args.username,
        args.display_name,
        password,
        admin_access=args.admin_access,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", required=True)
    parser.add_argument("--display-name", required=True)
    parser.add_argument(
        "--admin-access",
        action="store_true",
        help="Explicitly grant the Admin application in addition to the default Chat access",
    )
    args = parser.parse_args()
    password = getpass.getpass("平台账号初始密码（不回显）：")
    confirmation = getpass.getpass("再次输入初始密码：")
    if password != confirmation:
        parser.error("The entered passwords do not match")
    user_id = asyncio.run(_run(args, password))
    print(f"Platform account provisioned. User ID: {user_id}")
    if args.admin_access:
        print("Admin application access was granted; assign the required role before use.")


if __name__ == "__main__":
    main()
