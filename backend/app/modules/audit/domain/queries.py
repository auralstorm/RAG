"""Validated audit search intent and its transaction-bound persistence port."""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator

from app.core.contracts import TraceId, UtcTimestamp
from app.modules.audit.domain.contracts import AuditAction, AuditEvent, AuditResult, AuditRisk
from app.modules.iam.domain.rbac import RbacRepository


class AuditModule(StrEnum):
    IAM = "iam"
    PROVIDER = "provider"
    MODEL = "model"
    KB = "kb"
    RAG = "rag"
    TRACE = "trace"
    LIFECYCLE = "lifecycle"


class AuditCriteria(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    module: AuditModule | None = None
    action: AuditAction | None = None
    result: AuditResult | None = None
    risk: AuditRisk | None = None
    actor_user_id: UUID | None = None
    object_id: UUID | None = None
    request_id: UUID | None = None
    trace_id: TraceId | None = None
    occurred_from: UtcTimestamp | None = None
    occurred_until: UtcTimestamp | None = None

    @model_validator(mode="after")
    def require_increasing_interval(self) -> Self:
        if (
            self.occurred_from is not None
            and self.occurred_until is not None
            and self.occurred_from >= self.occurred_until
        ):
            raise ValueError("Audit time range must increase")
        return self


@dataclass(frozen=True)
class AuditPage:
    events: tuple[AuditEvent, ...]
    total: int


class AuditUnavailable(RuntimeError):
    """Audit storage or a stored fact cannot be read safely."""


class AuditRepository(RbacRepository, Protocol):
    async def search_audit(self, criteria: AuditCriteria, *, limit: int, offset: int) -> AuditPage: ...


type AuditTransaction = Callable[[], AbstractAsyncContextManager[AuditRepository]]
