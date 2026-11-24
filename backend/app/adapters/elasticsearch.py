"""Elasticsearch protocol adapter; native RRF is not required by the client fusion."""

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from urllib.parse import quote
from uuid import UUID

import httpx2
from pydantic import BaseModel, ConfigDict, Field, JsonValue, RootModel, field_validator, model_validator


@dataclass(frozen=True)
class RankedChunk:
    chunk_id: str
    score: float
    dense_rank: int | None
    bm25_rank: int | None


def reciprocal_rank_fusion(dense: Sequence[str], bm25: Sequence[str], *, rank_constant: int = 60) -> list[RankedChunk]:
    """Fuse unique chunk ranks with deterministic ties; raw search scores are not comparable."""
    if rank_constant < 1:
        raise ValueError("RRF rank constant must be positive")
    dense_ranks = {chunk_id: rank for rank, chunk_id in enumerate(dict.fromkeys(dense), 1)}
    bm25_ranks = {chunk_id: rank for rank, chunk_id in enumerate(dict.fromkeys(bm25), 1)}
    hits: list[RankedChunk] = []
    for chunk_id in dense_ranks.keys() | bm25_ranks.keys():
        dense_rank, bm25_rank = dense_ranks.get(chunk_id), bm25_ranks.get(chunk_id)
        score = (1 / (rank_constant + dense_rank) if dense_rank is not None else 0) + (
            1 / (rank_constant + bm25_rank) if bm25_rank is not None else 0
        )
        hits.append(RankedChunk(chunk_id, score, dense_rank, bm25_rank))
    return sorted(hits, key=lambda hit: (-hit.score, hit.chunk_id))


class SearchAccessDeniedError(ValueError):
    """The trusted current scope is missing or does not authorize the requested resources."""


class SearchUnavailableError(RuntimeError):
    """The search projection cannot provide a complete, validated result."""


class AuthorizedSearchScope(BaseModel):
    """Internal adapter input computed by Policy; never deserialize this from an API request.

    POC uses a synthetic current-permission fixture. Identity/Policy integration is P0-04/P1 work.
    Document IDs limit stale index ACL snapshots during revocation; they do not grant permission.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    subject_id: UUID
    kb_ids: frozenset[UUID]
    document_ids: frozenset[UUID]
    policy_version: str = Field(min_length=1)


class SearchQuery(BaseModel):
    """Bounded adapter query, separate from the eventual platform Retriever DTO."""

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
    query: str = Field(min_length=1, max_length=4000)
    kb_ids: tuple[UUID, ...] = Field(min_length=1, max_length=100)
    embedding: tuple[float, ...] = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=100)
    candidate_k: int = Field(default=40, ge=1, le=1000)
    source_types: tuple[str, ...] = ()

    @field_validator("query")
    @classmethod
    def require_query(cls, query: str) -> str:
        if not query.strip():
            raise ValueError("Search query must not be blank")
        return query

    @model_validator(mode="after")
    def bound_candidates(self) -> "SearchQuery":
        if self.top_k > self.candidate_k:
            raise ValueError("top_k exceeds the candidate limit")
        return self


class _AclSnapshot(BaseModel):
    subject_ids: tuple[UUID, ...]


class _ChunkSource(BaseModel):
    id: UUID
    document_id: UUID
    document_version: int = Field(ge=1)
    kb_id: UUID
    content: str
    status: str
    source_type: str
    acl_snapshot: _AclSnapshot


class _SearchHit(BaseModel):
    id: str = Field(alias="_id")
    source: _ChunkSource = Field(alias="_source")


class _SearchHits(BaseModel):
    hits: list[_SearchHit]


class _ShardStatus(BaseModel):
    failed: int


class _SearchResponse(BaseModel):
    timed_out: bool
    shards: _ShardStatus = Field(alias="_shards")
    hits: _SearchHits


class _AliasEntry(BaseModel):
    aliases: dict[str, JsonValue]


class SearchCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)
    chunk_id: UUID
    document_id: UUID
    document_version: int
    kb_id: UUID
    content: str
    source_type: str
    score: float
    dense_rank: int | None
    bm25_rank: int | None


class SearchResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    hits: tuple[SearchCandidate, ...]
    physical_index: str


class HybridSearchAdapter:
    """Own ES queries and RRF; the caller owns the bounded HTTP client's lifespan.

    Resolve the read alias once per call so concurrent publication cannot mix the two branches.
    Both branches apply the same current scope before ranking. Partial/invalid results fail closed.
    """

    def __init__(self, http: httpx2.AsyncClient, *, alias: str, dimensions: int, rank_constant: int = 60) -> None:
        if not alias or dimensions < 1 or rank_constant < 1:
            raise ValueError("Alias, vector dimension and positive RRF constant are required")
        self.http, self.alias = http, alias
        self.dimensions, self.rank_constant = dimensions, rank_constant

    async def search(self, query: SearchQuery, scope: AuthorizedSearchScope | None) -> SearchResult:
        if scope is None or not scope.kb_ids or not scope.document_ids or not set(query.kb_ids) <= scope.kb_ids:
            raise SearchAccessDeniedError("Current resource scope does not authorize this search")
        if len(query.embedding) != self.dimensions or not any(query.embedding):
            raise ValueError("Query embedding dimension is invalid or the vector is zero")
        kb_values: list[JsonValue] = [str(kb) for kb in sorted(query.kb_ids)]
        document_values: list[JsonValue] = [str(document) for document in sorted(scope.document_ids)]
        filters: list[JsonValue] = [
            {"terms": {"kb_id": kb_values}},
            {"terms": {"document_id": document_values}},
            {"term": {"acl_snapshot.subject_ids": str(scope.subject_id)}},
            {"term": {"status": "PUBLISHED"}},
        ]
        if query.source_types:
            filters.append({"terms": {"source_type": list(query.source_types)}})
        fields: list[JsonValue] = [
            "id",
            "document_id",
            "document_version",
            "kb_id",
            "content",
            "status",
            "source_type",
            "acl_snapshot",
        ]
        bm25: dict[str, JsonValue] = {
            "size": query.candidate_k,
            "_source": fields,
            "query": {"bool": {"must": [{"match": {"content": query.query}}], "filter": filters}},
            "sort": [{"_score": "desc"}, {"id": "asc"}],
        }
        dense: dict[str, JsonValue] = {
            "size": query.candidate_k,
            "_source": fields,
            "knn": {
                "field": "embedding",
                "query_vector": list(query.embedding),
                "k": query.candidate_k,
                "num_candidates": min(10000, query.candidate_k * 4),
                "filter": {"bool": {"filter": filters}},
            },
            "sort": [{"_score": "desc"}, {"id": "asc"}],
        }
        try:
            alias_response = await self.http.get(f"_alias/{quote(self.alias, safe='')}")
            alias_response.raise_for_status()
            indices = RootModel[dict[str, _AliasEntry]].model_validate(alias_response.json()).root
            if len(indices) != 1 or self.alias not in next(iter(indices.values())).aliases:
                raise SearchUnavailableError("Read alias must resolve to exactly one index")
            index = next(iter(indices))
            responses = await asyncio.gather(
                self.http.post(f"{quote(index, safe='')}/_search", json=dense),
                self.http.post(f"{quote(index, safe='')}/_search", json=bm25),
            )
            branches: list[list[_SearchHit]] = []
            sources: dict[str, _ChunkSource] = {}
            for response in responses:
                response.raise_for_status()
                envelope = _SearchResponse.model_validate(response.json())
                if envelope.timed_out or envelope.shards.failed:
                    raise SearchUnavailableError("Search returned incomplete results")
                branches.append(envelope.hits.hits)
                for hit in envelope.hits.hits:
                    source = hit.source
                    if (
                        hit.id != str(source.id)
                        or source.kb_id not in query.kb_ids
                        or source.document_id not in scope.document_ids
                        or source.status != "PUBLISHED"
                        or scope.subject_id not in source.acl_snapshot.subject_ids
                        or (query.source_types and source.source_type not in query.source_types)
                    ):
                        raise SearchUnavailableError("Search returned a candidate outside the authorized scope")
                    sources[hit.id] = source
            ranking = reciprocal_rank_fusion(
                [hit.id for hit in branches[0]],
                [hit.id for hit in branches[1]],
                rank_constant=self.rank_constant,
            )
            candidates: list[SearchCandidate] = []
            for hit in ranking[: query.top_k]:
                source = sources[hit.chunk_id]
                candidates.append(
                    SearchCandidate(
                        chunk_id=source.id,
                        document_id=source.document_id,
                        document_version=source.document_version,
                        kb_id=source.kb_id,
                        content=source.content,
                        source_type=source.source_type,
                        score=hit.score,
                        dense_rank=hit.dense_rank,
                        bm25_rank=hit.bm25_rank,
                    )
                )
            return SearchResult(hits=tuple(candidates), physical_index=index)
        except (httpx2.HTTPError, ValueError) as error:
            raise SearchUnavailableError(
                "Elasticsearch search is unavailable or returned an invalid response"
            ) from error
