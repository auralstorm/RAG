"""Build trusted authorization views from current transactional facts for each operation."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from app.modules.iam.application.sessions import SessionService
from app.modules.iam.domain.rbac import (
    DELEGABLE_PERMISSIONS,
    SYSTEM_ROLE_PERMISSIONS,
    AuthorizationDenied,
    RbacRepository,
    RoleDetails,
)
from app.modules.iam.domain.sessions import Application, SessionIssue
from app.modules.policy.application.authorization import actor_reference, authorize
from app.modules.policy.domain.contracts import (
    AccessContext,
    AccessPurpose,
    AuthorizationRequest,
    AuthorizationSnapshot,
    Environment,
)


@dataclass(frozen=True)
class Authority:
    session: SessionIssue
    roles: tuple[RoleDetails, ...]
    context: AccessContext
    snapshot: AuthorizationSnapshot


class PolicyEnforcer:
    def __init__(self, sessions: SessionService, environment: Environment, pseudonymization_key: bytes) -> None:
        self.sessions = sessions
        self.environment: Environment = environment
        self.pseudonymization_key = pseudonymization_key

    async def load(self, repository: RbacRepository, application: Application, token: str, version: str) -> Authority:
        session = await self.sessions.current_in_transaction(repository, application, token)
        roles = await repository.roles(session.user.id)
        bindings = await repository.bindings(session.user.id)
        grants = await repository.grants(application, session.user.id, roles, bindings)
        permission_codes = (
            frozenset(
                code
                for item in roles
                for code in item.permission_codes
                if code in SYSTEM_ROLE_PERMISSIONS.get(item.role.code, DELEGABLE_PERMISSIONS)
            )
            if application == "admin"
            else frozenset({"kb.read"})
        )
        facts = await repository.current_identity(session.session.identity_id)
        if facts is None:
            raise AuthorizationDenied()
        now = datetime.now(UTC)
        expires = min(session.access_expires_at, session.session.expires_at)
        if now >= expires:
            raise AuthorizationDenied()
        actor = actor_reference(session.user.id, self.pseudonymization_key)
        context = AccessContext(
            subject_id=session.user.id,
            identity_id=facts.identity.id,
            actor_ref=actor,
            environment=self.environment,
            purpose=AccessPurpose(application),
            policy_version=version,
            issued_at=now,
            expires_at=expires,
        )
        snapshot = AuthorizationSnapshot(
            user=facts.user,
            identity=facts.identity,
            actor_ref=actor,
            environment=self.environment,
            purpose=AccessPurpose(application),
            policy_version=version,
            role_ids=frozenset(item.role.id for item in roles),
            group_ids=frozenset(),
            permission_codes=permission_codes,
            resource_grants=grants,
            subject_bindings=bindings,
            observed_at=now,
            expires_at=expires,
        )
        return Authority(session, roles, context, snapshot)

    def require(self, authority: Authority, permission_code: str, *, kb_id: UUID | None = None) -> None:
        if authority.context.purpose is AccessPurpose.CHAT and permission_code != "kb.read":
            raise AuthorizationDenied()
        decision = authorize(
            AuthorizationRequest(permission_code=permission_code, purpose=authority.context.purpose, kb_id=kb_id),
            authority.context,
            authority.snapshot,
            now=datetime.now(UTC),
        )
        if not decision.allowed:
            raise AuthorizationDenied()
