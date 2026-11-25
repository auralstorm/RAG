"""IAM PostgreSQL facts participate in the application-owned transaction."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.adapters.audit_writer import PostgresAuditWriter
from app.modules.iam.domain.contracts import ExternalIdentity, IdentityKey, Role, User
from app.modules.iam.domain.sessions import Application, CurrentIdentity, PlatformSession


class SessionRow(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    id: UUID
    user_id: UUID
    identity_id: UUID
    application: Application
    expires_at: datetime
    revoked: bool

    def session(self) -> PlatformSession:
        return PlatformSession(self.id, self.user_id, self.identity_id, self.application, self.expires_at, self.revoked)


class PostgresAuthRepository(PostgresAuditWriter):
    async def find_identity(self, key: IdentityKey) -> CurrentIdentity | None:
        cursor = await self.connection.execute(
            "SELECT id FROM identities WHERE provider_key = %s AND issuer = %s AND subject = %s "
            "AND identity_key_digest(issuer) = identity_key_digest(%s) "
            "AND identity_key_digest(subject) = identity_key_digest(%s)",
            (key.provider_key, key.issuer, key.subject, key.issuer, key.subject),
        )
        row = await cursor.fetchone()
        return await self.current_identity(UUID(str(row[0]))) if row else None

    async def current_identity(self, identity_id: UUID) -> CurrentIdentity | None:
        cursor = await self.connection.execute(
            "SELECT jsonb_build_object('id', u.id, 'display_name', u.display_name, 'status', u.status, "
            "'created_at', u.created_at, 'updated_at', u.updated_at), "
            "jsonb_build_object('id', i.id, 'user_id', i.user_id, 'provider_key', i.provider_key, "
            "'issuer', i.issuer, 'subject', i.subject, 'status', i.status) "
            "FROM identities i JOIN users u ON u.id = i.user_id "
            "WHERE i.id = %s AND i.deleted_at IS NULL AND u.deleted_at IS NULL FOR SHARE OF i, u",
            (identity_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        applications = await self.connection.execute(
            "SELECT application FROM identity_applications WHERE identity_id = %s FOR SHARE", (identity_id,)
        )
        return CurrentIdentity(
            User.model_validate(row[0]),
            ExternalIdentity.model_validate(row[1]),
            frozenset(str(item[0]) for item in await applications.fetchall()),
        )

    async def insert_session(self, session: PlatformSession, refresh_hash: str) -> None:
        await self.connection.execute(
            "INSERT INTO auth_sessions(id, user_id, identity_id, application, expires_at) VALUES (%s,%s,%s,%s,%s)",
            (session.id, session.user_id, session.identity_id, session.application, session.expires_at),
        )
        await self.connection.execute(
            "INSERT INTO auth_refresh_tokens(token_hash, session_id) VALUES (%s,%s)", (refresh_hash, session.id)
        )

    async def session(self, session_id: UUID) -> PlatformSession | None:
        cursor = await self.connection.execute(
            "SELECT to_jsonb(s) - 'created_at' - 'revoked_at' || "
            "jsonb_build_object('revoked', s.revoked_at IS NOT NULL) FROM auth_sessions s WHERE id = %s FOR SHARE",
            (session_id,),
        )
        row = await cursor.fetchone()
        return SessionRow.model_validate(row[0]).session() if row else None

    async def refresh_session(self, token_hash: str) -> tuple[PlatformSession, bool] | None:
        cursor = await self.connection.execute(
            "SELECT to_jsonb(s) - 'created_at' - 'revoked_at' || "
            "jsonb_build_object('revoked', s.revoked_at IS NOT NULL), t.consumed_at IS NOT NULL "
            "FROM auth_refresh_tokens t JOIN auth_sessions s ON s.id=t.session_id "
            "WHERE t.token_hash = %s FOR UPDATE OF s, t",
            (token_hash,),
        )
        row = await cursor.fetchone()
        return (SessionRow.model_validate(row[0]).session(), bool(row[1])) if row else None

    async def rotate_refresh(self, token_hash: str, replacement_hash: str, session: PlatformSession) -> None:
        await self.connection.execute(
            "UPDATE auth_refresh_tokens SET consumed_at = CURRENT_TIMESTAMP WHERE token_hash=%s", (token_hash,)
        )
        await self.connection.execute(
            "INSERT INTO auth_refresh_tokens(token_hash,session_id) VALUES (%s,%s)", (replacement_hash, session.id)
        )

    async def revoke(self, session_id: UUID) -> None:
        await self.connection.execute(
            "UPDATE auth_sessions SET revoked_at = COALESCE(revoked_at, CURRENT_TIMESTAMP) WHERE id=%s", (session_id,)
        )

    async def login_budget(self, bucket: str, now: datetime, limit: int) -> bool:
        cursor = await self.connection.execute(
            "INSERT INTO auth_login_budgets(bucket,window_start,attempts) VALUES (%s,%s,1) "
            "ON CONFLICT(bucket) DO UPDATE SET "
            "attempts=CASE WHEN auth_login_budgets.window_start <= %s - interval '60 seconds' "
            "THEN 1 ELSE auth_login_budgets.attempts + 1 END, "
            "window_start=CASE WHEN auth_login_budgets.window_start <= %s - interval '60 seconds' "
            "THEN %s ELSE auth_login_budgets.window_start END RETURNING attempts",
            (bucket, now, now, now, now),
        )
        row = await cursor.fetchone()
        return row is not None and int(row[0]) <= limit

    async def audit_roles(self, user_id: UUID) -> tuple[Role, ...]:
        cursor = await self.connection.execute(
            "SELECT to_jsonb(r)-'created_at'-'updated_at'-'deleted_at' FROM roles r "
            "JOIN user_roles ur ON ur.role_id=r.id WHERE ur.user_id=%s AND r.deleted_at IS NULL "
            "ORDER BY r.id FOR SHARE OF r,ur",
            (user_id,),
        )
        return tuple(Role.model_validate(row[0]) for row in await cursor.fetchall())
