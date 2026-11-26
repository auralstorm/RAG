"""Read-only audit HTTP selection and explicit public view."""

from app.api.schemas.common import PaginationQuery
from app.modules.audit.domain.contracts import AuditEvent
from app.modules.audit.domain.queries import AuditCriteria, AuditModule


class AuditQuery(AuditCriteria, PaginationQuery):
    """Select an inclusive start/exclusive end interval and a bounded page."""


class AuditLogView(AuditEvent):
    module: AuditModule
