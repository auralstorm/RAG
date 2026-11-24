"""Knowledge base facts keep desired configuration separate from a published index."""

from enum import StrEnum
from typing import Annotated, Self
from uuid import UUID

from pydantic import Field, model_validator

from app.core.contracts import UtcTimestamp, VersionedContract

type ContentHash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
type ConfigurationVersion = Annotated[str, Field(min_length=1, max_length=128, pattern=r"\S")]


class KnowledgeBaseStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    DELETING = "DELETING"
    DELETED = "DELETED"


class EmbeddingBinding(VersionedContract):
    """Exact model/configuration/vector-space identity; dimensions have no inferred default."""

    embedding_model_id: UUID
    config_version: ConfigurationVersion
    dimensions: int = Field(ge=1, strict=True)


class KnowledgeBase(VersionedContract):
    """Logical KB metadata; query embedding always uses its active index's pinned binding."""

    id: UUID
    name: str = Field(min_length=1, max_length=200, pattern=r"\S")
    description: str = Field(default="", max_length=4000)
    status: KnowledgeBaseStatus
    embedding: EmbeddingBinding
    active_index_version_id: UUID | None
    created_by: UUID
    created_at: UtcTimestamp
    updated_at: UtcTimestamp
    deleted_at: UtcTimestamp | None = None

    @model_validator(mode="after")
    def require_lifecycle_times(self) -> Self:
        if self.updated_at < self.created_at:
            raise ValueError("KB update precedes creation")
        if (self.status is KnowledgeBaseStatus.DELETED) != (self.deleted_at is not None):
            raise ValueError("Completed KB deletion requires its deletion time")
        if self.deleted_at is not None and not self.created_at <= self.deleted_at <= self.updated_at:
            raise ValueError("KB deletion time is outside its lifecycle")
        return self
