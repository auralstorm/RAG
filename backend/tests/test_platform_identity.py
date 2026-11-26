"""Unit behavior for the production platform password verifier."""

import asyncio
from pathlib import Path

import pytest
from app.modules.iam.domain.identity_providers import PasswordCredentials, PlatformPasswordCredential
from app.modules.iam.domain.sessions import AuthenticationDenied, AuthenticationUnavailable
from app.modules.iam.infrastructure.platform_config import read_platform_config
from app.modules.iam.infrastructure.platform_identity import (
    PLATFORM_ISSUER,
    PLATFORM_PROVIDER_KEY,
    PlatformIdentityProvider,
    hash_platform_password,
)

from scripts.initialize_platform_auth import initialize

PASSWORD = "synthetic-platform-password-1234"


def test_platform_provider_returns_only_the_exact_identity_key() -> None:
    credential = PlatformPasswordCredential("stable-subject", hash_platform_password(PASSWORD))

    async def scenario() -> None:
        provider = PlatformIdentityProvider(lambda _username: _resolved(credential))
        identity = await provider.authenticate(PasswordCredentials("employee", PASSWORD))
        assert identity.provider_key == PLATFORM_PROVIDER_KEY
        assert identity.issuer == PLATFORM_ISSUER
        assert identity.subject == "stable-subject"

    asyncio.run(scenario())


def test_platform_provider_denies_unknown_and_wrong_credentials() -> None:
    credential = PlatformPasswordCredential("stable-subject", hash_platform_password(PASSWORD))

    async def scenario() -> None:
        provider = PlatformIdentityProvider(lambda username: _resolved(credential if username == "known" else None))
        with pytest.raises(AuthenticationDenied):
            await provider.authenticate(PasswordCredentials("known", "wrong-password"))
        with pytest.raises(AuthenticationDenied):
            await provider.authenticate(PasswordCredentials("unknown", PASSWORD))

    asyncio.run(scenario())


def test_malformed_persisted_hash_fails_closed_and_secrets_are_not_repr() -> None:
    async def scenario() -> None:
        provider = PlatformIdentityProvider(
            lambda _username: _resolved(PlatformPasswordCredential("subject", "not-a-valid-hash"))
        )
        with pytest.raises(AuthenticationUnavailable):
            await provider.authenticate(PasswordCredentials("employee", PASSWORD))

    asyncio.run(scenario())
    assert PASSWORD not in repr(PasswordCredentials("employee", PASSWORD))
    assert "not-a-valid-hash" not in repr(PlatformPasswordCredential("subject", "not-a-valid-hash"))


def test_platform_key_initializer_creates_private_keys_once(tmp_path: Path) -> None:
    path = tmp_path / "auth" / "platform.json"
    initialize(path)
    assert path.stat().st_mode & 0o777 == 0o600
    config = read_platform_config(path)
    assert len(config.signing_key.get_secret_value()) >= 64
    assert config.pseudonymization_key is not None
    original = path.read_bytes()
    with pytest.raises(FileExistsError):
        initialize(path)
    assert path.read_bytes() == original


async def _resolved(value: PlatformPasswordCredential | None) -> PlatformPasswordCredential | None:
    return value
