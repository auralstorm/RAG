"""One PostgreSQL append implementation shared by IAM and later business adapters."""

from psycopg import AsyncConnection
from psycopg.rows import TupleRow
from psycopg.types.json import Jsonb

from app.modules.audit.domain.contracts import AuditEvent


class PostgresAuditWriter:
    def __init__(self, connection: AsyncConnection[TupleRow]) -> None:
        self.connection = connection

    async def audit(self, event: AuditEvent) -> None:
        """Persist public audit facts; protected reveal reasons require the P5-specific writer."""
        await self.connection.execute(
            "INSERT INTO audit_events(id,schema_version,occurred_at,action,result,risk,request_id,trace_id,"
            "actor_user_id,actor_system_roles,actor_role_ids,ip_address,object_id,target_trace_id,before_snapshot,after_snapshot) "
            "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                event.id,
                event.schema_version,
                event.occurred_at,
                event.action.value,
                event.result.value,
                event.risk.value,
                event.request_id,
                event.trace_id,
                event.actor_user_id,
                [role.value for role in event.actor_system_roles],
                list(event.actor_role_ids),
                str(event.ip_address) if event.ip_address is not None else None,
                event.object_id,
                event.target_trace_id,
                Jsonb(event.before.model_dump(mode="json")) if event.before else None,
                Jsonb(event.after.model_dump(mode="json")) if event.after else None,
            ),
        )
