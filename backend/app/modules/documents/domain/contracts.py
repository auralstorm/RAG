"""Source inputs and storage references belong to a particular document version."""

from enum import StrEnum
from typing import Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from app.core.contracts import UtcTimestamp, VersionedContract
from app.modules.knowledge_base.domain.contracts import ConfigurationVersion, ContentHash
from app.modules.policy.domain.contracts import PolicyVersion

type DocumentMimeType = Literal[
    "text/markdown", "application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
]


class DocumentStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DELETING = "DELETING"
    DELETED = "DELETED"


class DocumentSourceType(StrEnum):
    UPLOAD = "UPLOAD"
    CONNECTOR = "CONNECTOR"


class DocumentVersionStatus(StrEnum):
    UPLOADED = "UPLOADED"
    PARSING = "PARSING"
    PARSED = "PARSED"
    CHUNKING = "CHUNKING"
    EMBEDDING = "EMBEDDING"
    INDEXING = "INDEXING"
    INDEXED = "INDEXED"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"
    DELETING = "DELETING"
    DELETED = "DELETED"


class DocumentVersionRef(VersionedContract):
    """Stable version entity ID plus the numeric version used by retrieval projections."""

    document_version_id: UUID
    document_id: UUID
    kb_id: UUID
    document_version: int = Field(ge=1, strict=True)


class Document(VersionedContract):
    """Logical resource; a newer failed processing version does not unpublish older content."""

    id: UUID
    kb_id: UUID
    title: str = Field(min_length=1, max_length=512, pattern=r"\S", repr=False)
    source_type: DocumentSourceType
    current_version: int = Field(ge=1, strict=True)
    status: DocumentStatus
    acl_policy_id: UUID | None
    created_by: UUID
    created_at: UtcTimestamp
    updated_at: UtcTimestamp
    deleted_at: UtcTimestamp | None = None

    @model_validator(mode="after")
    def require_lifecycle_times(self) -> Self:
        if self.updated_at < self.created_at:
            raise ValueError("Document update precedes creation")
        if (self.status is DocumentStatus.DELETED) != (self.deleted_at is not None):
            raise ValueError("Completed document deletion requires its deletion time")
        if self.deleted_at is not None and not self.created_at <= self.deleted_at <= self.updated_at:
            raise ValueError("Document deletion time is outside its lifecycle")
        return self


class DocumentVersion(DocumentVersionRef):
    """Public version facts exclude private keys, source URLs and parser-specific payloads."""

    status: DocumentVersionStatus
    mime_type: DocumentMimeType
    file_size: int = Field(gt=0, strict=True)
    file_hash: ContentHash
    pipeline_version: ConfigurationVersion
    parser_name: str | None = Field(default=None, min_length=1, max_length=64)
    parser_version: ConfigurationVersion | None = None
    chunking_config_version: ConfigurationVersion | None = None
    created_at: UtcTimestamp
    updated_at: UtcTimestamp
    published_at: UtcTimestamp | None = None

    @model_validator(mode="after")
    def require_consistent_version(self) -> Self:
        if self.updated_at < self.created_at:
            raise ValueError("Version update precedes creation")
        if (self.parser_name is None) != (self.parser_version is None):
            raise ValueError("Parser name and version must be pinned together")
        parsed = {
            DocumentVersionStatus.PARSED,
            DocumentVersionStatus.CHUNKING,
            DocumentVersionStatus.EMBEDDING,
            DocumentVersionStatus.INDEXING,
            DocumentVersionStatus.INDEXED,
            DocumentVersionStatus.PUBLISHED,
        }
        if self.status in parsed and self.parser_name is None:
            raise ValueError("Parsed and later versions require their actual parser binding")
        if (
            self.status
            in {
                DocumentVersionStatus.EMBEDDING,
                DocumentVersionStatus.INDEXING,
                DocumentVersionStatus.INDEXED,
                DocumentVersionStatus.PUBLISHED,
            }
            and self.chunking_config_version is None
        ):
            raise ValueError("Embedding and later versions require their chunking configuration")
        if self.status is DocumentVersionStatus.PUBLISHED and self.published_at is None:
            raise ValueError("Published versions require a confirmed publication time")
        if self.published_at is not None and self.status not in {
            DocumentVersionStatus.PUBLISHED,
            DocumentVersionStatus.DELETING,
            DocumentVersionStatus.DELETED,
        }:
            raise ValueError("Published version history cannot be reused as a processing attempt")
        if self.published_at is not None and not self.created_at <= self.published_at <= self.updated_at:
            raise ValueError("Version publication time is outside its lifecycle")
        return self


class StoredObjectRef(VersionedContract):
    """Server-resolved S3 reference, never a URL or permission to download its contents."""

    bucket: str = Field(min_length=3, max_length=63, pattern=r"^[a-z0-9][a-z0-9.-]*[a-z0-9]$", repr=False)
    object_key: str = Field(min_length=1, max_length=1024, pattern=r"\S", repr=False)
    sha256: ContentHash
    size_bytes: int = Field(gt=0, strict=True)

    @model_validator(mode="after")
    def require_opaque_key(self) -> Self:
        if "://" in self.object_key:
            raise ValueError("Stored references accept object keys, not signed URLs")
        return self


class StoredDocumentVersion(DocumentVersion):
    """Internal version record pins the original and optional parsed artifact independently."""

    original: StoredObjectRef = Field(repr=False)
    parsed_artifact: StoredObjectRef | None = Field(default=None, repr=False)

    @model_validator(mode="after")
    def require_original_integrity(self) -> Self:
        if self.original.sha256 != self.file_hash or self.original.size_bytes != self.file_size:
            raise ValueError("Original reference does not match the version's source digest and size")
        if (
            self.status
            in {
                DocumentVersionStatus.PARSED,
                DocumentVersionStatus.CHUNKING,
                DocumentVersionStatus.EMBEDDING,
                DocumentVersionStatus.INDEXING,
                DocumentVersionStatus.INDEXED,
                DocumentVersionStatus.PUBLISHED,
            }
            and self.parsed_artifact is None
        ):
            raise ValueError("Parsed version states require their persisted artifact reference")
        return self


class DocumentAccessPolicy(VersionedContract):
    """Current document restriction intersects KB permission; None explicitly means inherit."""

    document_id: UUID
    kb_id: UUID
    acl_policy_id: UUID | None
    allowed_subject_ids: frozenset[UUID] | None
    policy_version: PolicyVersion

    @model_validator(mode="after")
    def require_explicit_restriction(self) -> Self:
        if (self.acl_policy_id is None) != (self.allowed_subject_ids is None):
            raise ValueError("Document policy reference and explicit subject restriction must agree")
        return self
