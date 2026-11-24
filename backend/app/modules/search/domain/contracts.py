"""A validated immutable index manifest defines which document versions are published."""

import hashlib
import json
from enum import StrEnum
from typing import Annotated, Self
from uuid import UUID

from pydantic import Field, model_validator

from app.core.contracts import UtcTimestamp, VersionedContract
from app.modules.documents.domain.contracts import Document, DocumentVersion, DocumentVersionRef
from app.modules.knowledge_base.domain.contracts import (
    ConfigurationVersion,
    ContentHash,
    EmbeddingBinding,
    KnowledgeBase,
)

type IndexName = Annotated[str, Field(min_length=1, max_length=255, pattern=r"^[a-z0-9][a-z0-9._-]*$")]


class IndexVersionStatus(StrEnum):
    BUILDING = "BUILDING"
    VALIDATING = "VALIDATING"
    READY = "READY"
    ACTIVE = "ACTIVE"
    ROLLED_BACK = "ROLLED_BACK"
    FAILED = "FAILED"
    RETIRED = "RETIRED"


class ValidationVerdict(StrEnum):
    PASSED = "PASSED"
    FAILED = "FAILED"


def index_binding_hash(embedding: EmbeddingBinding, chunking_version: str, pipeline_version: str) -> str:
    payload = {
        "embedding": embedding.model_dump(mode="json"),
        "chunking_version": chunking_version,
        "pipeline_version": pipeline_version,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class IndexManifest(VersionedContract):
    """Internal authoritative member list; at most one version per logical document."""

    index_version_id: UUID
    kb_id: UUID
    documents: tuple[DocumentVersionRef, ...] = Field(repr=False)

    @model_validator(mode="after")
    def require_unique_members(self) -> Self:
        if any(reference.kb_id != self.kb_id for reference in self.documents):
            raise ValueError("Index manifest contains a document from another KB")
        if len({reference.document_id for reference in self.documents}) != len(self.documents):
            raise ValueError("Index manifest contains multiple versions of one document")
        if len({reference.document_version_id for reference in self.documents}) != len(self.documents):
            raise ValueError("Index manifest contains duplicate version entity IDs")
        return self

    @property
    def content_hash(self) -> str:
        ordered = sorted(self.documents, key=lambda item: str(item.document_id))
        payload = {
            "index_version_id": str(self.index_version_id),
            "kb_id": str(self.kb_id),
            "documents": [reference.model_dump(mode="json") for reference in ordered],
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class IndexValidationReport(VersionedContract):
    """Trusted validation facts; every required check is explicit, including the quality gate."""

    id: UUID
    index_version_id: UUID
    manifest_sha256: ContentHash
    binding_sha256: ContentHash
    verdict: ValidationVerdict
    expected_document_count: int = Field(ge=0, strict=True)
    actual_document_count: int = Field(ge=0, strict=True)
    expected_chunk_count: int = Field(ge=0, strict=True)
    actual_chunk_count: int = Field(ge=0, strict=True)
    mapping_verified: bool = Field(strict=True)
    acl_verified: bool = Field(strict=True)
    retrieval_verified: bool = Field(strict=True)
    quality_gate_verified: bool = Field(strict=True)
    checked_at: UtcTimestamp

    @model_validator(mode="after")
    def require_complete_validation(self) -> Self:
        if self.verdict is ValidationVerdict.PASSED and not (
            self.expected_document_count == self.actual_document_count
            and self.expected_chunk_count == self.actual_chunk_count
            and self.mapping_verified
            and self.acl_verified
            and self.retrieval_verified
            and self.quality_gate_verified
        ):
            raise ValueError("Passed validation requires all checks and matching counts")
        return self


class IndexVersion(VersionedContract):
    """Public version facts pin the full vector/configuration space and validation reference."""

    id: UUID
    kb_id: UUID
    version: int = Field(ge=1, strict=True)
    status: IndexVersionStatus
    embedding: EmbeddingBinding
    chunking_config_version: ConfigurationVersion
    pipeline_version: ConfigurationVersion
    manifest_sha256: ContentHash | None
    validation_report_id: UUID | None
    created_at: UtcTimestamp
    updated_at: UtcTimestamp
    published_at: UtcTimestamp | None

    @model_validator(mode="after")
    def require_version_times_and_references(self) -> Self:
        if self.updated_at < self.created_at:
            raise ValueError("Index update precedes creation")
        if self.status in {IndexVersionStatus.READY, IndexVersionStatus.ACTIVE, IndexVersionStatus.ROLLED_BACK}:
            if self.manifest_sha256 is None or self.validation_report_id is None:
                raise ValueError("Ready and published indexes require manifest and validation references")
        if self.status in {IndexVersionStatus.ACTIVE, IndexVersionStatus.ROLLED_BACK} and self.published_at is None:
            raise ValueError("Published index history requires its publication time")
        if self.published_at is not None and self.status not in {
            IndexVersionStatus.ACTIVE,
            IndexVersionStatus.ROLLED_BACK,
            IndexVersionStatus.RETIRED,
        }:
            raise ValueError("Published index history cannot be reused as a build attempt")
        if self.published_at is not None and not self.created_at <= self.published_at <= self.updated_at:
            raise ValueError("Index publication time is outside its lifecycle")
        return self


class StoredIndexVersion(IndexVersion):
    """Internal physical names and validation evidence do not appear in the frontend model."""

    physical_index_name: IndexName = Field(repr=False)
    alias_name: IndexName = Field(repr=False)
    validation: IndexValidationReport | None = Field(repr=False)

    @model_validator(mode="after")
    def require_bound_evidence(self) -> Self:
        if self.physical_index_name == self.alias_name:
            raise ValueError("Physical index and alias names must be distinct")
        report = self.validation
        if report is not None and (
            report.id != self.validation_report_id
            or report.index_version_id != self.id
            or report.manifest_sha256 != self.manifest_sha256
            or report.binding_sha256
            != index_binding_hash(self.embedding, self.chunking_config_version, self.pipeline_version)
        ):
            raise ValueError("Index validation evidence belongs to a different version, manifest or configuration")
        if report is not None and not self.created_at <= report.checked_at <= self.updated_at:
            raise ValueError("Index validation evidence is outside its lifecycle")
        if self.status in {IndexVersionStatus.READY, IndexVersionStatus.ACTIVE, IndexVersionStatus.ROLLED_BACK}:
            if report is None or report.verdict is not ValidationVerdict.PASSED:
                raise ValueError("Ready and published indexes require bound passed evidence")
        return self


class IndexAlias(VersionedContract):
    """Freshly observed internal alias state; both pointers must represent the same target."""

    kb_id: UUID
    alias_name: IndexName
    active_index_version_id: UUID | None
    physical_index_name: IndexName | None

    @model_validator(mode="after")
    def require_consistent_pointer(self) -> Self:
        if (self.active_index_version_id is None) != (self.physical_index_name is None):
            raise ValueError("Alias logical and physical pointers must agree")
        return self


class PublicationAction(StrEnum):
    PUBLISH = "PUBLISH"
    ROLLBACK = "ROLLBACK"


class IndexPublication(VersionedContract):
    """Confirmed historical operation; only the real execution layer records this receipt."""

    id: UUID
    kb_id: UUID
    action: PublicationAction
    previous_index_version_id: UUID | None
    target_index_version_id: UUID
    idempotency_key: str = Field(min_length=1, max_length=256, pattern=r"\S")
    actor_subject_id: UUID
    occurred_at: UtcTimestamp


class PublicationRequest(VersionedContract):
    kb_id: UUID
    action: PublicationAction
    target_index_version_id: UUID
    expected_active_index_version_id: UUID | None
    idempotency_key: str = Field(min_length=1, max_length=256, pattern=r"\S")


class PublicationSnapshot(VersionedContract):
    """Current database/alias/document facts; producer owns consistent reads and authority."""

    kb: KnowledgeBase
    target: StoredIndexVersion
    current: StoredIndexVersion | None
    alias: IndexAlias
    manifest: IndexManifest
    documents: tuple[Document, ...] = Field(repr=False)
    document_versions: tuple[DocumentVersion, ...] = Field(repr=False)


class PublicationPlan(VersionedContract):
    """Validated CAS and alias intent; constructing it performs no publication or IO."""

    request: PublicationRequest
    actor_subject_id: UUID
    alias_name: IndexName
    remove_physical_index: IndexName | None
    add_physical_index: IndexName
    embedding: EmbeddingBinding
    manifest_sha256: ContentHash
    prepared_at: UtcTimestamp


class PublishedDocumentSnapshot(VersionedContract):
    """Current read facts preserve KB, logical document, version and index/alias relationships."""

    kb: KnowledgeBase
    document: Document
    version: DocumentVersion
    index: StoredIndexVersion
    alias: IndexAlias
    manifest: IndexManifest
