"""Explicitly appoint the first active local administrator; no default user is elevated."""

import argparse
import asyncio
import fcntl
import json
import os
import secrets
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from app.adapters.postgres import postgres_transaction
from app.adapters.rbac import PostgresRbacRepository
from app.core.config import Settings, load_settings
from app.modules.audit.domain.contracts import AuditAction, AuditEvent, AuditResult, AuditRisk, AuditSnapshot
from app.modules.iam.domain.rbac import RbacConflict
from app.modules.iam.infrastructure.local_identity import read_private_config


async def appoint_first_admin(settings: Settings, user_id: UUID) -> None:
    """Serialize bootstrap with HTTP role changes and audit the initial appointment."""
    async with postgres_transaction(settings) as connection:
        await connection.execute("SET LOCAL lock_timeout='5s'")
        repository = PostgresRbacRepository(connection)
        await repository.policy_version(write=True)
        if await repository.active_super_admins():
            raise RbacConflict("An active administrator already exists; use authenticated role management")
        user = await repository.user(user_id)
        cursor = await connection.execute(
            "SELECT 1 FROM identities i JOIN identity_applications a ON a.identity_id=i.id WHERE i.user_id=%s AND i.status='ACTIVE' AND i.deleted_at IS NULL AND a.application='admin' LIMIT 1",
            (user_id,),
        )
        if user is None or not user.active or await cursor.fetchone() is None:
            raise RbacConflict("An active platform user with explicit Admin application access is required")
        roles = await repository.roles()
        super_admin = next(item for item in roles if item.role.code == "SUPER_ADMIN")
        before = tuple(item.role.id for item in await repository.roles(user_id))
        selected = tuple(dict.fromkeys((*before, super_admin.role.id)))
        await repository.replace_user_roles(user_id, selected)
        await repository.audit(
            AuditEvent(
                id=uuid4(),
                occurred_at=datetime.now(UTC),
                action=AuditAction.ROLE_CHANGE,
                result=AuditResult.SUCCEEDED,
                risk=AuditRisk.HIGH,
                request_id=uuid4(),
                trace_id=secrets.token_hex(16),
                object_id=user_id,
                before=AuditSnapshot(role_ids=before),
                after=AuditSnapshot(role_ids=selected),
            )
        )


def bootstrap(settings: Settings, path: Path, user_id: UUID) -> None:
    if settings.environment == "production":
        raise ValueError("Local identity bootstrap is not available in production")
    path = path.absolute()
    descriptor = os.open(path.with_name(path.name + ".lock"), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "r+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        configuration = read_private_config(path)
        if configuration.pseudonymization_key is None:
            temporary = path.with_name(path.name + "." + secrets.token_hex(8))
            try:
                descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(descriptor, "w") as output:
                    json.dump(
                        {
                            "signing_key": configuration.signing_key.get_secret_value(),
                            "pseudonymization_key": secrets.token_hex(48),
                            "accounts": [account.model_dump() for account in configuration.accounts],
                        },
                        output,
                    )
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
        asyncio.run(appoint_first_admin(settings, user_id))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", type=UUID, required=True)
    parser.add_argument("--config", type=Path, default=Path(".poc-results/auth/local.json"))
    args = parser.parse_args()
    bootstrap(load_settings(), args.config, args.user_id)
    print("Initial administrator appointed and audited. Restart the API with the private identity reference.")


if __name__ == "__main__":
    main()
