"""Development-only identity source, configured through a private local file reference."""

import asyncio
import hashlib
import hmac
import os
import secrets
import stat
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.modules.iam.domain.contracts import IdentityKey
from app.modules.iam.domain.sessions import AuthenticationDenied

LOCAL_ISSUER = "urn:enterprise-rag:local"
PASSWORD_ITERATIONS = 600_000


class LocalAccount(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    username: str = Field(min_length=1, max_length=128, repr=False)
    subject: str = Field(min_length=1, max_length=256, repr=False)
    salt: str = Field(pattern=r"^[0-9a-f]{32}$", repr=False)
    password_hash: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)


class LocalIdentityConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    signing_key: SecretStr = Field(min_length=64)
    accounts: tuple[LocalAccount, ...] = Field(min_length=1, max_length=100)


def read_private_config(path: Path) -> LocalIdentityConfig:
    """Refuse symlinks, shared permissions, foreign owners and oversized source files."""
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as source:
        info = os.fstat(source.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_mode & 0o077
            or info.st_size > 100_000
        ):
            raise ValueError("Local identity configuration requires a private regular file")
        configuration = LocalIdentityConfig.model_validate_json(source.read(100_001))
    names = [account.username for account in configuration.accounts]
    subjects = [account.subject for account in configuration.accounts]
    if len(set(names)) != len(names) or len(set(subjects)) != len(subjects):
        raise ValueError("Local identity configuration contains duplicate account mappings")
    return configuration


def password_hash(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), PASSWORD_ITERATIONS).hex()


class LocalIdentityProvider:
    def __init__(self, configuration: LocalIdentityConfig) -> None:
        self.configuration = configuration
        self.dummy_salt = secrets.token_hex(16)
        self.dummy_hash = password_hash(secrets.token_urlsafe(32), self.dummy_salt)

    async def authenticate(self, username: str, password: str) -> IdentityKey:
        account = next((item for item in self.configuration.accounts if item.username == username), None)
        actual = await asyncio.to_thread(password_hash, password, account.salt if account else self.dummy_salt)
        matches = hmac.compare_digest(actual, account.password_hash if account else self.dummy_hash)
        if not matches or account is None:
            raise AuthenticationDenied()
        return IdentityKey(provider_key="local", issuer=LOCAL_ISSUER, subject=account.subject)
