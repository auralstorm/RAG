"""A chunk cites precise slices of normalized parsed blocks, separately from source coordinates."""

import hashlib
from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import Field, model_validator

from app.core.contracts import UtcTimestamp, VersionedContract
from app.modules.documents.domain.contracts import DocumentVersionRef
from app.modules.knowledge_base.domain.contracts import ConfigurationVersion, ContentHash
from app.modules.parsing.domain.contracts import SourceLocation


class ChunkSourceSpan(VersionedContract):
    block_id: str = Field(min_length=1, max_length=128, pattern=r"\S")
    char_start: int = Field(ge=0, strict=True)
    char_end: int = Field(gt=0, strict=True)
    location: SourceLocation

    @model_validator(mode="after")
    def require_nonempty_slice(self) -> Self:
        if self.char_end <= self.char_start:
            raise ValueError("Chunk spans require nonempty half-open parsed-block text ranges")
        return self


class ChunkSource(VersionedContract):
    spans: tuple[ChunkSourceSpan, ...] = Field(min_length=1)


class ChunkMetadata(VersionedContract):
    heading_path: tuple[str, ...] = ()

    @model_validator(mode="after")
    def require_headings(self) -> Self:
        if any(not heading.strip() for heading in self.heading_path):
            raise ValueError("Chunk heading paths cannot contain blank entries")
        return self


class ChunkRole(StrEnum):
    STANDALONE = "STANDALONE"
    PARENT = "PARENT"
    CHILD = "CHILD"


class Chunk(DocumentVersionRef):
    id: UUID
    chunk_index: int = Field(ge=0, strict=True)
    role: ChunkRole
    parent_chunk_id: UUID | None
    content: str = Field(min_length=1, pattern=r"\S", repr=False)
    content_hash: ContentHash
    token_count: int = Field(gt=0, strict=True)
    tokenizer_version: ConfigurationVersion
    chunking_config_version: ConfigurationVersion
    source: ChunkSource
    metadata: ChunkMetadata
    created_at: UtcTimestamp

    @model_validator(mode="after")
    def require_integrity(self) -> Self:
        if self.content_hash != hashlib.sha256(self.content.encode("utf-8")).hexdigest():
            raise ValueError("Chunk content digest does not match its UTF-8 text")
        if (self.role is ChunkRole.CHILD) != (self.parent_chunk_id is not None) or self.parent_chunk_id == self.id:
            raise ValueError("Only child chunks require a distinct parent chunk ID")
        return self
