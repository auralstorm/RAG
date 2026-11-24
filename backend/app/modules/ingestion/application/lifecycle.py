"""Validate stage ordering, terminal states and bounded retries without writing external state."""

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from app.modules.documents.domain.contracts import DocumentVersion, DocumentVersionRef, DocumentVersionStatus
from app.modules.ingestion.domain.contracts import IngestionFailure, IngestionJob, IngestionJobStatus, IngestionStage

VERSION_TRANSITIONS = {
    DocumentVersionStatus.UPLOADED: {DocumentVersionStatus.PARSING, DocumentVersionStatus.DELETING},
    DocumentVersionStatus.PARSING: {
        DocumentVersionStatus.PARSED,
        DocumentVersionStatus.FAILED,
        DocumentVersionStatus.DELETING,
    },
    DocumentVersionStatus.PARSED: {DocumentVersionStatus.CHUNKING, DocumentVersionStatus.DELETING},
    DocumentVersionStatus.CHUNKING: {
        DocumentVersionStatus.EMBEDDING,
        DocumentVersionStatus.FAILED,
        DocumentVersionStatus.DELETING,
    },
    DocumentVersionStatus.EMBEDDING: {
        DocumentVersionStatus.INDEXING,
        DocumentVersionStatus.FAILED,
        DocumentVersionStatus.DELETING,
    },
    DocumentVersionStatus.INDEXING: {
        DocumentVersionStatus.INDEXED,
        DocumentVersionStatus.FAILED,
        DocumentVersionStatus.DELETING,
    },
    DocumentVersionStatus.INDEXED: {DocumentVersionStatus.PUBLISHED, DocumentVersionStatus.DELETING},
    DocumentVersionStatus.PUBLISHED: {DocumentVersionStatus.DELETING},
    DocumentVersionStatus.FAILED: {DocumentVersionStatus.PARSING, DocumentVersionStatus.DELETING},
    DocumentVersionStatus.DELETING: {DocumentVersionStatus.DELETED},
    DocumentVersionStatus.DELETED: set[DocumentVersionStatus](),
}


def _time(now: datetime, previous: datetime) -> datetime:
    if now.tzinfo is None or now.utcoffset() is None or now < previous:
        raise ValueError("Lifecycle changes require a nondecreasing timezone-aware server clock")
    return now.astimezone(UTC)


class DeletionTarget(StrEnum):
    ORIGINAL = "original"
    PARSED_ARTIFACTS = "parsed_artifacts"
    CHUNKS = "chunks"
    SEARCH = "search"
    CACHE = "cache"
    ASSOCIATED_DATA = "associated_data"


@dataclass(frozen=True, slots=True)
class VerifiedDeletionCleanup:
    """Trusted cleanup evidence that each recorded target is absent for this version."""

    version: DocumentVersionRef
    absent_targets: frozenset[DeletionTarget]
    verified_at: datetime


def advance_document_version[VersionT: DocumentVersion](
    version: VersionT, target: DocumentVersionStatus, *, now: datetime, cleanup: VerifiedDeletionCleanup | None = None
) -> VersionT:
    """Advance one version; published content cannot become a new processing attempt.

    Parsing/chunking evidence is attached by the owning use case before the transition.
    Failed-to-parsing is a full restart; later-stage recovery requires verified checkpoints
    in the actual Worker implementation and is not inferred by this helper.
    """
    if target not in VERSION_TRANSITIONS[version.status]:
        raise ValueError("Illegal document-version state transition")
    at = _time(now, version.updated_at)
    if target is DocumentVersionStatus.DELETED:
        reference = DocumentVersionRef.model_validate(version.model_dump(include=set(DocumentVersionRef.model_fields)))
        if cleanup is None or cleanup.version != reference or cleanup.absent_targets != frozenset(DeletionTarget):
            raise ValueError("Deletion requires verified cleanup of every target for this document version")
        _time(cleanup.verified_at, version.updated_at)
        _time(at, cleanup.verified_at)
    data = {**version.model_dump(), "status": target, "updated_at": at}
    if version.status is DocumentVersionStatus.FAILED and target is DocumentVersionStatus.PARSING:
        data.update(parser_name=None, parser_version=None, chunking_config_version=None)
        if "parsed_artifact" in data:
            data["parsed_artifact"] = None
    if target is DocumentVersionStatus.PUBLISHED:
        data["published_at"] = at
    return type(version).model_validate(data)


def advance_ingestion_job(
    job: IngestionJob,
    target: IngestionJobStatus,
    *,
    now: datetime,
    stage: IngestionStage | None = None,
    failure: IngestionFailure | None = None,
) -> IngestionJob:
    """Record a valid job update; stage success does not claim that a version is published."""
    allowed = {
        IngestionJobStatus.QUEUED: {IngestionJobStatus.RUNNING, IngestionJobStatus.CANCELLED},
        IngestionJobStatus.RUNNING: {
            IngestionJobStatus.RUNNING,
            IngestionJobStatus.SUCCEEDED,
            IngestionJobStatus.FAILED,
            IngestionJobStatus.CANCELLED,
            IngestionJobStatus.TIMED_OUT,
        },
    }
    if target not in allowed.get(job.status, set()):
        raise ValueError("Illegal ingestion-job state transition")
    at = _time(now, job.updated_at)
    next_stage = stage or job.stage
    if list(IngestionStage).index(next_stage) < list(IngestionStage).index(job.stage):
        raise ValueError("Running stages cannot move backwards")
    data = {**job.model_dump(), "status": target, "stage": next_stage, "updated_at": at, "failure": failure}
    if target is IngestionJobStatus.RUNNING:
        data["started_at"] = job.started_at or at
    else:
        data["finished_at"] = at
    return IngestionJob.model_validate(data)


def retry_ingestion_job(job: IngestionJob, *, now: datetime) -> IngestionJob:
    """Retry the same intent at its recorded stage, preserving ID, key, owner and budget."""
    if job.status is not IngestionJobStatus.FAILED or job.failure is None or not job.failure.retryable:
        raise ValueError("Only explicitly retryable failed jobs can be queued again")
    if job.retry_count >= job.max_retries:
        raise ValueError("Ingestion retry budget is exhausted")
    at = _time(now, job.updated_at)
    return IngestionJob.model_validate(
        {
            **job.model_dump(),
            "status": IngestionJobStatus.QUEUED,
            "retry_count": job.retry_count + 1,
            "failure": None,
            "finished_at": None,
            "updated_at": at,
        }
    )
