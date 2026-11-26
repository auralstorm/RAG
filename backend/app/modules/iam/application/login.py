"""Verify any configured identity source before establishing a platform session."""

from collections.abc import Callable
from datetime import UTC, datetime
from ipaddress import IPv4Address, IPv6Address
from uuid import UUID

from app.modules.audit.application.recording import security_event
from app.modules.audit.domain.contracts import AuditAction, AuditResult
from app.modules.audit.domain.recording import AuditContext
from app.modules.iam.application.sessions import SessionService, token_digest
from app.modules.iam.domain.identity_providers import IdentityProvider
from app.modules.iam.domain.sessions import Application, AuthenticationDenied, AuthenticationThrottled, SessionIssue


class LoginService[CredentialsT]:
    """The composition root selects the provider; HTTP input cannot select an Adapter."""

    def __init__(
        self,
        sessions: SessionService,
        provider: IdentityProvider[CredentialsT],
        *,
        account_key: Callable[[CredentialsT], str] | None = None,
    ) -> None:
        self.sessions = sessions
        self.provider = provider
        # Optional account-level budgets use a stable login name, never a code or Token.
        self.account_key = account_key

    async def login(
        self,
        application: Application,
        credentials: CredentialsT,
        *,
        client_key: str,
        request_id: UUID,
        trace_id: str,
        ip_address: IPv4Address | IPv6Address | None = None,
    ) -> SessionIssue:
        context = AuditContext(request_id, trace_id, ip_address)
        now = datetime.now(UTC)
        network_bucket = token_digest(self.sessions.tokens.csrf(UUID(int=1)) + client_key)
        async with self.sessions.transactions() as repository:
            account_ok = True
            if self.account_key is not None:
                account_bucket = token_digest(
                    self.sessions.tokens.csrf(UUID(int=0)) + application + ":" + self.account_key(credentials)
                )
                account_ok = await repository.login_budget(account_bucket, now, 5)
            network_ok = await repository.login_budget(network_bucket, now, 30)
            if not account_ok or not network_ok:
                await repository.audit(security_event(context, AuditAction.LOGIN, AuditResult.DENIED))
        if not account_ok or not network_ok:
            raise AuthenticationThrottled()

        # External verification never holds a database transaction open.
        try:
            key = await self.provider.authenticate(credentials)
        except AuthenticationDenied:
            await self.sessions.denied_login(context)
            raise
        return await self.sessions.establish(application, key, context)
