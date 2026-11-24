"""Typed business filters cannot replace current Policy/Manifest constraints."""

from typing import Protocol, Self
from uuid import UUID

from pydantic import Field, model_validator

from app.core.contracts import UtcTimestamp, VersionedContract
from app.modules.chunking.domain.contracts import Chunk, ChunkMetadata, ChunkSource
from app.modules.documents.domain.contracts import DocumentAccessPolicy, DocumentSourceType, DocumentVersionRef
from app.modules.knowledge_base.domain.contracts import ConfigurationVersion, EmbeddingBinding, KnowledgeBase
from app.modules.policy.domain.contracts import AccessContext, AuthorizationSnapshot
from app.modules.search.domain.contracts import PublishedDocumentSnapshot


class RetrievalFilters(VersionedContract):
    document_ids: tuple[UUID, ...] = ()
    source_types: tuple[DocumentSourceType, ...] = ()

    @model_validator(mode="after")
    def require_unique_filters(self) -> Self:
        if len(set(self.document_ids)) != len(self.document_ids) or len(set(self.source_types)) != len(
            self.source_types
        ):
            raise ValueError("Retrieval filter selections cannot contain duplicates")
        return self


class RetrievalSelection(VersionedContract):
    """Client-selectable business intent; identity, trace and resolved configuration are server-owned."""

    query: str = Field(min_length=1, max_length=4000, pattern=r"\S", repr=False)
    kb_ids: tuple[UUID, ...] = Field(min_length=1, max_length=100)
    filters: RetrievalFilters = Field(default_factory=RetrievalFilters)
    top_k: int = Field(ge=1, le=100, strict=True)
    config_version: ConfigurationVersion | None = None

    @model_validator(mode="after")
    def require_unique_kbs(self) -> Self:
        if len(set(self.kb_ids)) != len(self.kb_ids):
            raise ValueError("Retrieval KB selections cannot contain duplicates")
        return self


class RetrievalRequest(RetrievalSelection):
    access_context: AccessContext = Field(repr=False)
    trace_id: str = Field(pattern=r"^[0-9a-f]{32}$")

    @model_validator(mode="after")
    def require_trace(self) -> Self:
        if self.trace_id == "0" * 32:
            raise ValueError("Retrieval requires a nonzero server trace ID")
        return self


class ScoreComponents(VersionedContract):
    """Optional search ranks/scores, never a probability of answer correctness."""

    dense_rank: int | None = Field(default=None, ge=1, strict=True)
    bm25_rank: int | None = Field(default=None, ge=1, strict=True)
    rrf_score: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    reranker_score: float | None = Field(default=None, allow_inf_nan=False)

    @model_validator(mode="after")
    def require_fusion_ranks(self) -> Self:
        if self.rrf_score is not None and self.dense_rank is None and self.bm25_rank is None:
            raise ValueError("RRF diagnostics require at least one source rank")
        return self


class RetrievedChunk(DocumentVersionRef):
    chunk_id: UUID
    index_version_id: UUID
    content: str = Field(min_length=1, pattern=r"\S", repr=False)
    score: float = Field(allow_inf_nan=False)
    score_components: ScoreComponents
    source: ChunkSource
    metadata: ChunkMetadata


class RetrievalDiagnostics(VersionedContract):
    trace_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    config_version: ConfigurationVersion
    returned_chunk_count: int = Field(ge=0, strict=True)
    elapsed_ms: float = Field(ge=0, allow_inf_nan=False)


class RetrievalResult(VersionedContract):
    chunks: tuple[RetrievedChunk, ...] = Field(repr=False)
    diagnostics: RetrievalDiagnostics

    @model_validator(mode="after")
    def require_result_consistency(self) -> Self:
        if len({chunk.chunk_id for chunk in self.chunks}) != len(self.chunks):
            raise ValueError("Retrieval results cannot contain duplicate chunk IDs")
        if self.diagnostics.returned_chunk_count != len(self.chunks):
            raise ValueError("Retrieval diagnostics must match the returned chunk count")
        return self


class RetrievalDocumentFacts(VersionedContract):
    published: PublishedDocumentSnapshot = Field(repr=False)
    policy: DocumentAccessPolicy = Field(repr=False)


class RetrievalFacts(VersionedContract):
    """Trusted current reads; producers own consistency and resolve exact versioned retrieval configuration."""

    authorization: AuthorizationSnapshot = Field(repr=False)
    config_version: ConfigurationVersion
    max_top_k: int = Field(ge=1, le=100, strict=True)
    knowledge_bases: tuple[KnowledgeBase, ...] = Field(repr=False)
    documents: tuple[RetrievalDocumentFacts, ...] = Field(repr=False)
    chunks: tuple[Chunk, ...] = Field(repr=False)


class RetrievalIndexBinding(VersionedContract):
    kb_id: UUID
    index_version_id: UUID
    embedding: EmbeddingBinding
    chunking_config_version: ConfigurationVersion
    pipeline_version: ConfigurationVersion


class AuthorizedRetrievalScope(VersionedContract):
    """Internal current bounds for adapters; an empty version set must skip search IO."""

    request: RetrievalRequest = Field(repr=False)
    config_version: ConfigurationVersion
    index_bindings: tuple[RetrievalIndexBinding, ...]
    document_versions: tuple[DocumentVersionRef, ...]
    prepared_at: UtcTimestamp
    expires_at: UtcTimestamp


class Retriever(Protocol):
    """Implementations own bounded retrieval plus current authorization before search and before return."""

    async def retrieve(self, request: RetrievalRequest) -> RetrievalResult: ...
