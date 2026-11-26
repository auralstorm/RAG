"""Verify first-party platform passwords without blocking the async request loop."""

import asyncio
import secrets
from collections.abc import Awaitable, Callable

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.modules.iam.domain.contracts import IdentityKey
from app.modules.iam.domain.identity_providers import (
    PLATFORM_ISSUER,
    PLATFORM_PROVIDER_KEY,
    PasswordCredentials,
    PlatformPasswordCredential,
)
from app.modules.iam.domain.sessions import AuthenticationDenied, AuthenticationUnavailable

# Argon2id parameters meet current OWASP baseline recommendations. Bound in-flight
# verification per process to limit peak memory during a burst of login requests.
PASSWORD_HASHER = PasswordHasher(time_cost=2, memory_cost=19_456, parallelism=1)
MAX_CONCURRENT_VERIFICATIONS = 4


def hash_platform_password(password: str) -> str:
    """Return a salted Argon2id verifier; callers must never log or expose it."""
    return PASSWORD_HASHER.hash(password)


class PlatformIdentityProvider:
    """Authenticate username/password against a platform credential lookup port."""

    def __init__(
        self,
        lookup: Callable[[str], Awaitable[PlatformPasswordCredential | None]],
    ) -> None:
        self.lookup = lookup
        self._dummy_hash = hash_platform_password(secrets.token_urlsafe(32))
        self._verification_slots = asyncio.Semaphore(MAX_CONCURRENT_VERIFICATIONS)

    async def _verify(self, encoded: str, password: str) -> bool:
        try:
            return await asyncio.to_thread(PASSWORD_HASHER.verify, encoded, password)
        except VerifyMismatchError:
            return False
        except (InvalidHashError, VerificationError) as error:
            raise AuthenticationUnavailable() from error

    async def authenticate(self, credentials: PasswordCredentials) -> IdentityKey:
        credential = await self.lookup(credentials.username)
        encoded = credential.password_hash if credential is not None else self._dummy_hash
        async with self._verification_slots:
            verification = asyncio.create_task(self._verify(encoded, credentials.password))
            try:
                matches = await asyncio.shield(verification)
            except asyncio.CancelledError:
                # The native hash cannot be stopped after it starts. Keep its slot
                # occupied until it finishes, then propagate request cancellation.
                try:
                    await verification
                except AuthenticationUnavailable:
                    pass
                raise
        if credential is None or not matches:
            raise AuthenticationDenied()
        return IdentityKey(
            provider_key=PLATFORM_PROVIDER_KEY,
            issuer=PLATFORM_ISSUER,
            subject=credential.subject,
        )
