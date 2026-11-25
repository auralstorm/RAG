"""Typed identity verification ports; provider credentials never become platform tokens."""

from dataclasses import dataclass, field
from typing import Protocol

from app.modules.iam.domain.contracts import IdentityKey

PLATFORM_PROVIDER_KEY = "platform"
PLATFORM_ISSUER = "urn:enterprise-rag:platform"


@dataclass(frozen=True)
class PasswordCredentials:
    username: str = field(repr=False)
    password: str = field(repr=False)


@dataclass(frozen=True)
class PlatformPasswordCredential:
    """Stored password verifier and exact platform identity returned by persistence."""

    subject: str = field(repr=False)
    password_hash: str = field(repr=False)


class IdentityProvider[CredentialsT](Protocol):
    """Verify source credentials before returning an exact, trusted identity key.

    Implementations own provider protocol/credential validation and translate known
    refusals or outages into AuthenticationDenied or AuthenticationUnavailable.
    They never create platform users, sessions or grants.
    """

    async def authenticate(self, credentials: CredentialsT) -> IdentityKey: ...


@dataclass(frozen=True)
class AuthorizationRequest:
    """Server-owned values bound to a pending, expiring browser login transaction."""

    redirect_uri: str
    state: str = field(repr=False)
    nonce: str | None = field(default=None, repr=False)
    code_challenge: str | None = field(default=None, repr=False)


@dataclass(frozen=True)
class AuthorizationCodeCredentials:
    """Construct only after consuming and verifying the browser's login transaction.

    The coordinator must check state, expiry, browser, application and provider,
    and consume the transaction atomically before invoking the Adapter. The Adapter
    verifies the authorization code and applicable provider claims using these
    original server-owned values. This type alone proves none of those checks.
    """

    code: str = field(repr=False)
    redirect_uri: str
    nonce: str | None = field(default=None, repr=False)
    code_verifier: str | None = field(default=None, repr=False)


class AuthorizationCodeProvider(IdentityProvider[AuthorizationCodeCredentials], Protocol):
    """Protocol-specific redirects and verification; no browser state store inside.

    Nonce/PKCE are optional across protocols, not optional when the configured
    provider flow requires them. The Adapter must reject missing required values.
    """

    def authorization_url(self, request: AuthorizationRequest) -> str: ...
