"""A stable job intent does not change when the worker advances or retries a stage."""

import hashlib
import json
from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import Field, JsonValue, model_validator

from app.core.contracts import UtcTimestamp, VersionedContract
from app.modules.documents.domain.contracts import DocumentVersionRef
from app.modules.knowledge_base.domain.contracts import ConfigurationVersion, ContentHash


class IngestionStage(StrEnum):
    PARSING = "PARSING"
    NORMALIZING = "NORMALIZING"
    CHUNKING = "CHUNKING"
    EMBEDDING = "EMBEDDING"
    INDEXING = "INDEXING"
    VALIDATING = "VALIDATING"
    PUBLISHING = "PUBLISHING"
    DELETING = "DELETING"


class IngestionJobType(StrEnum):
    INGEST = "INGEST"
    REPROCESS = "REPROCESS"
    REINDEX = "REINDEX"
    DELETE = "DELETE"


class IngestionJobStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"


class IngestionFailure(VersionedContract):
    """Safe adapter-provided classification; uncertain external effects are never retryable."""

    code: str = Field(min_length=1, max_length=64, pattern=r"^[A-Z][A-Z0-9_]*$")
    message: str = Field(min_length=1, max_length=512)
    retryable: bool = Field(strict=True)
    outcome_unknown: bool = Field(strict=True)

    @model_validator(mode="after")
    def require_safe_retry_classification(self) -> Self:
        if self.outcome_unknown and self.retryable:
            raise ValueError("Unknown external outcomes cannot authorize a retry")
        return self


class IngestionProgress(VersionedContract):
    completed_units: int = Field(ge=0, strict=True)
    total_units: int | None = Field(ge=0, strict=True)

    @model_validator(mode="after")
    def require_bounded_progress(self) -> Self:
        if self.total_units is not None and self.completed_units > self.total_units:
            raise ValueError("Ingestion progress exceeds the known total")
        return self


def _intent_hash(payload: dict[str, JsonValue]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def ingestion_job_key(
    version: DocumentVersionRef,
    pipeline_version: str,
    job_type: IngestionJobType,
    terminal_stage: IngestionStage,
) -> str:
    """Stable intent key, separate from client upload keys and per-stage deduplication."""
    return _intent_hash(
        {
            "version": version.model_dump(mode="json"),
            "pipeline_version": pipeline_version,
            "job_type": job_type.value,
            "terminal_stage": terminal_stage.value,
        }
    )


def ingestion_stage_key(version: DocumentVersionRef, pipeline_version: str, stage: IngestionStage) -> str:
    return _intent_hash(
        {"version": version.model_dump(mode="json"), "pipeline_version": pipeline_version, "stage": stage.value}
    )


class IngestionJob(DocumentVersionRef):
    """Version-bound business job; Celery IDs and cached roles do not define its identity."""

    id: UUID
    job_type: IngestionJobType
    pipeline_version: ConfigurationVersion
    terminal_stage: IngestionStage
    status: IngestionJobStatus
    stage: IngestionStage
    idempotency_key: ContentHash
    requester_subject_id: UUID
    trace_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    retry_count: int = Field(ge=0, strict=True)
    max_retries: int = Field(ge=0, strict=True)
    progress: IngestionProgress
    failure: IngestionFailure | None
    created_at: UtcTimestamp
    updated_at: UtcTimestamp
    started_at: UtcTimestamp | None
    finished_at: UtcTimestamp | None

    @model_validator(mode="after")
    def require_consistent_job(self) -> Self:
        reference = DocumentVersionRef.model_validate(
            {key: getattr(self, key) for key in ("document_version_id", "document_id", "kb_id", "document_version")}
        )
        if self.idempotency_key != ingestion_job_key(
            reference, self.pipeline_version, self.job_type, self.terminal_stage
        ):
            raise ValueError("Job key does not match its immutable version/pipeline/goal intent")
        if self.retry_count > self.max_retries:
            raise ValueError("Job retry count exceeds its configured limit")
        deleting = self.job_type is IngestionJobType.DELETE
        if deleting != (self.stage is IngestionStage.DELETING) or deleting != (
            self.terminal_stage is IngestionStage.DELETING
        ):
            raise ValueError("Deletion stages require a deletion job")
        if list(IngestionStage).index(self.stage) > list(IngestionStage).index(self.terminal_stage):
            raise ValueError("Job stage exceeds its declared goal")
        terminal = self.status in {
            IngestionJobStatus.SUCCEEDED,
            IngestionJobStatus.FAILED,
            IngestionJobStatus.CANCELLED,
            IngestionJobStatus.TIMED_OUT,
        }
        if terminal != (self.finished_at is not None):
            raise ValueError("Terminal job status and completion time must agree")
        if (
            self.status
            in {
                IngestionJobStatus.RUNNING,
                IngestionJobStatus.SUCCEEDED,
                IngestionJobStatus.FAILED,
                IngestionJobStatus.TIMED_OUT,
            }
            and self.started_at is None
        ):
            raise ValueError("Executed jobs require their first start time")
        if self.status is IngestionJobStatus.SUCCEEDED and (
            self.failure is not None or self.stage is not self.terminal_stage
        ):
            raise ValueError("Succeeded jobs require their declared goal without a failure")
        if self.status in {IngestionJobStatus.FAILED, IngestionJobStatus.TIMED_OUT} and self.failure is None:
            raise ValueError("Failed jobs require a safe error classification")
        if (
            self.status in {IngestionJobStatus.QUEUED, IngestionJobStatus.RUNNING, IngestionJobStatus.SUCCEEDED}
            and self.failure is not None
        ):
            raise ValueError("Runnable/succeeded jobs cannot carry a current failure")
        if self.updated_at < self.created_at:
            raise ValueError("Job update precedes creation")
        for time in (self.started_at, self.finished_at):
            if time is not None and not self.created_at <= time <= self.updated_at:
                raise ValueError("Job execution time is outside its lifecycle")
        if self.started_at is not None and self.finished_at is not None and self.finished_at < self.started_at:
            raise ValueError("Job completion precedes its start")
        return self


class IngestionEventType(StrEnum):
    STARTED = "STARTED"
    PROGRESS = "PROGRESS"
    STAGE_SUCCEEDED = "STAGE_SUCCEEDED"
    FAILED = "FAILED"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"
    SUCCEEDED = "SUCCEEDED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"


class IngestionEvent(VersionedContract):
    """Monotonic per-job event reference; arbitrary document text and MQ headers are absent."""

    id: UUID
    job_id: UUID
    sequence_no: int = Field(ge=1, strict=True)
    stage: IngestionStage
    event_type: IngestionEventType
    attempt: int = Field(ge=1, strict=True)
    progress: IngestionProgress | None
    failure: IngestionFailure | None
    occurred_at: UtcTimestamp

    @model_validator(mode="after")
    def require_consistent_event(self) -> Self:
        if self.event_type in {
            IngestionEventType.FAILED,
            IngestionEventType.TIMED_OUT,
            IngestionEventType.RETRY_SCHEDULED,
        }:
            if self.failure is None:
                raise ValueError("Failure and retry events require a safe error classification")
            if self.event_type is IngestionEventType.RETRY_SCHEDULED and not self.failure.retryable:
                raise ValueError("Retry events require an explicitly retryable failure")
        elif self.event_type is not IngestionEventType.CANCELLED and self.failure is not None:
            raise ValueError("Progress and success events cannot carry a current failure")
        if self.event_type is IngestionEventType.PROGRESS and self.progress is None:
            raise ValueError("Progress events require their measured progress")
        return self
