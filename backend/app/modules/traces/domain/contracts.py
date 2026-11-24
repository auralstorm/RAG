"""Anonymous trace diagnostics and a separately controlled identity link."""

from collections import defaultdict
from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import Field, model_validator

from app.core.contracts import SpanId, TraceId, UtcTimestamp, VersionedContract
from app.modules.documents.domain.contracts import DocumentVersionRef
from app.modules.knowledge_base.domain.contracts import ConfigurationVersion
from app.modules.model_gateway.domain.contracts import ModelUsage


class TraceStage(StrEnum):
    ANSWER = "rag.answer"
    POLICY = "auth.policy"
    ROUTE = "query.route"
    HISTORY = "conversation.load"
    REWRITE = "query.rewrite"
    EMBED = "embedding.query"
    DENSE = "retrieval.dense"
    BM25 = "retrieval.bm25"
    FUSE = "retrieval.fusion"
    RERANK = "retrieval.rerank"
    CONTEXT = "context.assemble"
    GENERATE = "llm.generate"
    CITE = "citation.validate"
    STREAM = "response.stream"


class TraceStatus(StrEnum):
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    REFUSED = "REFUSED"


class TraceError(StrEnum):
    TIMEOUT = "TIMEOUT"
    ACCESS_DENIED = "ACCESS_DENIED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    INVALID_CITATION = "INVALID_CITATION"
    DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class TraceSpan(VersionedContract):
    span_id: SpanId
    parent_span_id: SpanId | None = None
    stage: TraceStage
    status: TraceStatus
    started_at: UtcTimestamp
    finished_at: UtcTimestamp | None = None
    error_code: TraceError | None = None
    model_id: UUID | None = None
    model_config_version: ConfigurationVersion | None = None
    prompt_version: ConfigurationVersion | None = None
    token_usage: ModelUsage | None = None
    candidate_count: int | None = Field(default=None, ge=0, strict=True)
    document_versions: tuple[DocumentVersionRef, ...] = Field(default=(), max_length=100, repr=False)

    @model_validator(mode="after")
    def require_consistent_span(self) -> Self:
        if (self.status is TraceStatus.RUNNING) != (self.finished_at is None):
            raise ValueError("A finished span requires a terminal status and finish time")
        if self.finished_at is not None and self.finished_at < self.started_at:
            raise ValueError("Span finish cannot precede its start")
        if (self.error_code is not None) != (self.status in (TraceStatus.FAILED, TraceStatus.REFUSED)):
            raise ValueError("Failed and refused spans require a stable error code")
        if (self.model_id is None) != (self.model_config_version is None):
            raise ValueError("Model diagnostics require both model ID and configuration version")
        return self


class Trace(VersionedContract):
    trace_id: TraceId
    request_id: UUID
    config_version: ConfigurationVersion
    index_version_ids: tuple[UUID, ...] = Field(default=(), max_length=100)
    spans: tuple[TraceSpan, ...] = Field(min_length=1, max_length=1000, repr=False)

    @model_validator(mode="after")
    def require_answer_tree(self) -> Self:
        by_id = {span.span_id: span for span in self.spans}
        roots = [span for span in self.spans if span.parent_span_id is None]
        if len(by_id) != len(self.spans) or len(roots) != 1 or roots[0].stage is not TraceStage.ANSWER:
            raise ValueError("Trace requires unique span IDs and one answer root")
        children: dict[str, list[str]] = defaultdict(list)
        for span in self.spans:
            if span.parent_span_id is None:
                continue
            parent = by_id.get(span.parent_span_id)
            if parent is None or span.stage is TraceStage.ANSWER:
                raise ValueError("Child span requires a parent in the same trace")
            if span.started_at < parent.started_at or (
                parent.finished_at is not None and (span.finished_at is None or span.finished_at > parent.finished_at)
            ):
                raise ValueError("Child span must fit within its parent's lifetime")
            children[parent.span_id].append(span.span_id)
        pending = [roots[0].span_id]
        visited = 0
        while pending:
            span_id = pending.pop()
            visited += 1
            pending.extend(children[span_id])
        if visited != len(self.spans):
            raise ValueError("Every span must connect to the answer root")
        return self


class TraceIdentityLink(VersionedContract):
    trace_id: TraceId
    request_id: UUID
    protected_identity_ref: UUID = Field(repr=False)
    expires_at: UtcTimestamp
