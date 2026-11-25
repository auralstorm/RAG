"""Platform login and session lifecycle; transactions belong to these use cases."""

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.modules.audit.application.recording import security_event
from app.modules.audit.domain.contracts import AuditAction, AuditResult
from app.modules.audit.domain.recording import AuditContext
from app.modules.iam.domain.contracts import IdentityKey, IdentityStatus
from app.modules.iam.domain.sessions import (
    Application,
    AuthenticationDenied,
    AuthRepository,
    AuthTransaction,
    CurrentIdentity,
    PlatformSession,
    SessionIssue,
    SessionTokens,
)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def require_identity(facts: CurrentIdentity | None, application: Application) -> CurrentIdentity:
    if facts is None or not facts.user.active or facts.identity.status is not IdentityStatus.ACTIVE:
        raise AuthenticationDenied()
    if facts.identity.user_id != facts.user.id or application not in facts.applications:
        raise AuthenticationDenied()
    return facts


class SessionService:
    """Issue short-lived access JWTs and rotate opaque, hashed refresh credentials."""

    def __init__(
        self,
        transactions: AuthTransaction,
        tokens: SessionTokens,
        *,
        access_seconds: int = 900,
        session_seconds: int = 86400,
    ) -> None:
        self.transactions = transactions
        self.tokens = tokens
        self.access_seconds = access_seconds
        self.session_seconds = session_seconds

    def _issue(self, session: PlatformSession, facts: CurrentIdentity, refresh: str, now: datetime) -> SessionIssue:
        expires = min(now + timedelta(seconds=self.access_seconds), session.expires_at)
        return SessionIssue(
            session,
            facts.user,
            self.tokens.issue(session, now, expires),
            refresh,
            self.tokens.csrf(session.id),
            expires,
        )

    async def denied_login(self, context: AuditContext) -> None:
        """Record an Origin refusal without attributing the supplied account or cookies."""
        async with self.transactions() as repository:
            await repository.audit(security_event(context, AuditAction.LOGIN, AuditResult.DENIED))

    async def establish(
        self,
        application: Application,
        key: IdentityKey,
        context: AuditContext,
    ) -> SessionIssue:
        """Resolve an Adapter-verified key; never expose this input as a browser DTO."""
        denied = False
        issue: SessionIssue | None = None
        async with self.transactions() as repository:
            try:
                facts = require_identity(await repository.find_identity(key), application)
            except AuthenticationDenied:
                denied = True
                await repository.audit(security_event(context, AuditAction.LOGIN, AuditResult.DENIED))
            else:
                now = datetime.now(UTC)
                session = PlatformSession(
                    uuid4(),
                    facts.user.id,
                    facts.identity.id,
                    application,
                    now + timedelta(seconds=self.session_seconds),
                )
                refresh = secrets.token_urlsafe(48)
                await repository.insert_session(session, token_digest(refresh))
                await repository.audit(
                    security_event(
                        context,
                        AuditAction.LOGIN,
                        AuditResult.SUCCEEDED,
                        actor_user_id=facts.user.id,
                        roles=await repository.audit_roles(facts.user.id),
                    )
                )
                issue = self._issue(session, facts, refresh, now)
        if denied or issue is None:
            raise AuthenticationDenied()
        return issue

    async def current(self, application: Application, access_token: str) -> SessionIssue:
        async with self.transactions() as repository:
            return await self.current_in_transaction(repository, application, access_token)

    async def current_in_transaction(
        self, repository: AuthRepository, application: Application, access_token: str
    ) -> SessionIssue:
        """Authenticate within an operation's transaction; never commit or create a new connection."""
        claims = self.tokens.verify(access_token, application)
        session = await repository.session(claims.session_id)
        now = datetime.now(UTC)
        if (
            session is None
            or session.revoked
            or session.expires_at <= now
            or session.application != application
            or session.user_id != claims.user_id
            or session.identity_id != claims.identity_id
        ):
            raise AuthenticationDenied()
        facts = require_identity(await repository.current_identity(session.identity_id), application)
        now = datetime.now(UTC)
        if session.expires_at <= now or claims.expires_at <= now:
            raise AuthenticationDenied()
        return SessionIssue(session, facts.user, "", "", self.tokens.csrf(session.id), claims.expires_at)

    async def refresh(
        self, application: Application, refresh_token: str, csrf: str, *, logout: bool = False
    ) -> SessionIssue | None:
        result: SessionIssue | None = None
        denied = False
        async with self.transactions() as repository:
            row = await repository.refresh_session(token_digest(refresh_token))
            now = datetime.now(UTC)
            if row is None:
                raise AuthenticationDenied()
            session, consumed = row
            if session.application != application or not hmac.compare_digest(csrf, self.tokens.csrf(session.id)):
                raise AuthenticationDenied()
            if logout or consumed or session.revoked or session.expires_at <= now:
                await repository.revoke(session.id)
                denied = not logout
            else:
                try:
                    facts = require_identity(await repository.current_identity(session.identity_id), application)
                except AuthenticationDenied:
                    await repository.revoke(session.id)
                    denied = True
                else:
                    now = datetime.now(UTC)
                    if session.expires_at <= now:
                        await repository.revoke(session.id)
                        denied = True
                    else:
                        replacement = secrets.token_urlsafe(48)
                        await repository.rotate_refresh(token_digest(refresh_token), token_digest(replacement), session)
                        result = self._issue(session, facts, replacement, now)
        # Replay revocation must commit before reporting the refusal.
        if denied:
            raise AuthenticationDenied()
        return result

    async def refresh_csrf(self, application: Application, refresh_token: str) -> str:
        """Recover an in-memory CSRF value after reload without rotating a credential."""
        async with self.transactions() as repository:
            row = await repository.refresh_session(token_digest(refresh_token))
            if row is None:
                raise AuthenticationDenied()
            session, consumed = row
            if (
                consumed
                or session.revoked
                or session.expires_at <= datetime.now(UTC)
                or session.application != application
            ):
                raise AuthenticationDenied()
            require_identity(await repository.current_identity(session.identity_id), application)
            if session.expires_at <= datetime.now(UTC):
                raise AuthenticationDenied()
            return self.tokens.csrf(session.id)
