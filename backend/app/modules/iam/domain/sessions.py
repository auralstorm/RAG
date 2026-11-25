"""Server-owned authentication facts and ports, independent of HTTP and persistence."""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

from app.modules.audit.domain.recording import AuditWriter
from app.modules.iam.domain.contracts import ExternalIdentity, IdentityKey, Role, User

type Application = Literal["chat", "admin"]


class AuthenticationDenied(PermissionError):
    """A refusal without account, credential or token diagnostics."""


class AuthenticationThrottled(AuthenticationDenied):
    """A persistent login budget was exceeded."""


class AuthenticationUnavailable(RuntimeError):
    """The source or current authentication facts cannot be loaded safely."""


@dataclass(frozen=True)
class CurrentIdentity:
    user: User
    identity: ExternalIdentity
    applications: frozenset[str]


@dataclass(frozen=True)
class PlatformSession:
    id: UUID
    user_id: UUID
    identity_id: UUID
    application: Application
    expires_at: datetime
    revoked: bool = False


@dataclass(frozen=True)
class AccessClaims:
    session_id: UUID
    user_id: UUID
    identity_id: UUID
    application: Application
    expires_at: datetime


@dataclass(frozen=True)
class SessionIssue:
    session: PlatformSession
    user: User
    access_token: str = field(repr=False)
    refresh_token: str = field(repr=False)
    csrf_token: str = field(repr=False)
    access_expires_at: datetime


class IdentityProvider(Protocol):
    async def authenticate(self, username: str, password: str) -> IdentityKey: ...


class SessionTokens(Protocol):
    def issue(self, session: PlatformSession, now: datetime, expires_at: datetime) -> str: ...
    def verify(self, token: str, application: Application) -> AccessClaims: ...
    def csrf(self, session_id: UUID) -> str: ...


class AuthRepository(AuditWriter, Protocol):
    async def find_identity(self, key: IdentityKey) -> CurrentIdentity | None: ...
    async def current_identity(self, identity_id: UUID) -> CurrentIdentity | None: ...
    async def insert_session(self, session: PlatformSession, refresh_hash: str) -> None: ...
    async def session(self, session_id: UUID) -> PlatformSession | None: ...
    async def refresh_session(self, token_hash: str) -> tuple[PlatformSession, bool] | None: ...
    async def rotate_refresh(self, token_hash: str, replacement_hash: str, session: PlatformSession) -> None: ...
    async def revoke(self, session_id: UUID) -> None: ...
    async def login_budget(self, bucket: str, now: datetime, limit: int) -> bool: ...
    async def audit_roles(self, user_id: UUID) -> tuple[Role, ...]: ...


type AuthTransaction = Callable[[], AbstractAsyncContextManager[AuthRepository]]
