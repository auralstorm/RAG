"""Transactional Policy/audit bridge with bounded parameterized PostgreSQL search."""

from psycopg import sql
from pydantic import ValidationError

from app.adapters.rbac import PostgresRbacRepository
from app.modules.audit.domain.contracts import AuditEvent
from app.modules.audit.domain.queries import AuditCriteria, AuditPage, AuditUnavailable


class PostgresAuditRepository(PostgresRbacRepository):
    async def search_audit(self, criteria: AuditCriteria, *, limit: int, offset: int) -> AuditPage:
        if not 1 <= limit <= 100 or offset < 0:
            raise ValueError("Audit search requires bounded pagination")
        clauses: list[sql.Composable] = []
        values: list[object] = []
        # Identifiers and operators are server constants; inputs are always bound values.
        for name in ("action", "result", "risk", "actor_user_id", "object_id", "request_id", "trace_id"):
            value = getattr(criteria, name)
            if value is not None:
                clauses.append(sql.SQL("e.{}=%s").format(sql.Identifier(name)))
                values.append(value)
        if criteria.module is not None:
            clauses.append(sql.SQL("split_part(e.action,'.',1)=%s"))
            values.append(criteria.module.value)
        for clause, value in (
            (sql.SQL("e.occurred_at>=%s"), criteria.occurred_from),
            (sql.SQL("e.occurred_at<%s"), criteria.occurred_until),
        ):
            if value is not None:
                clauses.append(clause)
                values.append(value)
        where = sql.SQL(" AND ").join(clauses) if clauses else sql.SQL("true")
        # Both count and page use one statement snapshot, even during concurrent appends.
        # Private reason references never enter the validated public AuditEvent projection.
        cursor = await self.connection.execute(
            sql.SQL(
                "SELECT (SELECT count(*) FROM audit_events e WHERE {where}), "
                "COALESCE((SELECT jsonb_agg(item ORDER BY occurred_at DESC,id DESC) FROM ("
                "SELECT to_jsonb(e)-ARRAY['created_at','protected_reason_ref','before_snapshot','after_snapshot'] "
                "|| jsonb_build_object('before',e.before_snapshot,'after',e.after_snapshot,'ip_address',host(e.ip_address)) AS item, "
                "e.occurred_at,e.id FROM audit_events e WHERE {where} "
                "ORDER BY e.occurred_at DESC,e.id DESC LIMIT %s OFFSET %s) page),'[]'::jsonb)"
            ).format(where=where),
            (*values, *values, limit, offset),
        )
        row = await cursor.fetchone()
        if row is None:
            raise AuditUnavailable()
        try:
            return AuditPage(tuple(AuditEvent.model_validate(item) for item in row[1]), int(row[0]))
        except (ValidationError, TypeError, ValueError) as error:
            raise AuditUnavailable() from error
