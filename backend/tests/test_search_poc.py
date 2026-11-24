"""POC-01: real Elasticsearch interfaces with disposable, synthetic records."""

import asyncio
import json
import subprocess
from collections.abc import Generator
from pathlib import Path
from uuid import UUID, uuid4

import httpx2
import pytest
from app.adapters.elasticsearch import (
    AuthorizedSearchScope,
    HybridSearchAdapter,
    SearchAccessDeniedError,
    SearchQuery,
    SearchUnavailableError,
)
from app.core.config import load_settings
from pydantic import JsonValue, RootModel

from scripts.infrastructure import initialize_config

pytestmark = [pytest.mark.poc, pytest.mark.anyio]
ROOT = Path(__file__).resolve().parents[2]
KB = UUID(int=1)
SUBJECT = UUID(int=10)
DOCUMENT = UUID(int=20)
CHUNK = UUID(int=30)

DATASET = ROOT / "backend/tests/fixtures/search-poc.json"
MAPPING: dict[str, JsonValue] = {
    "mappings": {
        "dynamic": "strict",
        "properties": {
            "id": {"type": "keyword"},
            "document_id": {"type": "keyword"},
            "document_version": {"type": "integer"},
            "kb_id": {"type": "keyword"},
            "content": {"type": "text"},
            "status": {"type": "keyword"},
            "source_type": {"type": "keyword"},
            "acl_snapshot": {"properties": {"subject_ids": {"type": "keyword"}}},
            "embedding": {"type": "dense_vector", "dims": 3, "index": True, "similarity": "cosine"},
        },
    }
}


def current_scope() -> AuthorizedSearchScope:
    return AuthorizedSearchScope(
        subject_id=SUBJECT,
        kb_ids=frozenset({KB}),
        document_ids=frozenset(UUID(int=n) for n in (20, 21, 22, 25, 26, 27)),
        policy_version="synthetic-policy-1",
    )


def leave_query(**updates: object) -> SearchQuery:
    return SearchQuery.model_validate(
        {
            "query": "HR-001",
            "kb_ids": (KB,),
            "embedding": (1.0, 0.0, 0.0),
            "top_k": 3,
            **updates,
        }
    )


async def seed_index(url: str, index: str, *, version: int = 1) -> None:
    rows = RootModel[list[dict[str, JsonValue]]].model_validate_json(DATASET.read_text()).root
    async with httpx2.AsyncClient(base_url=url, trust_env=False, timeout=10) as http:
        response = await http.put(index, json=MAPPING)
        response.raise_for_status()
        for row in rows:
            payload = {**row, "document_version": version}
            response = await http.put(f"{index}/_doc/{row['id']}", json=payload)
            response.raise_for_status()
        (await http.post(f"{index}/_refresh")).raise_for_status()


def poc_command() -> list[str]:
    return [
        "docker",
        "compose",
        "--project-name",
        "enterprise-rag-poc-search",
        "--file",
        str(ROOT / "infra/compose/search-poc.yaml"),
        "--env-file",
        str(ROOT / "infra/compose/images.env"),
        "--env-file",
        str(ROOT / "infra/compose/.env.test"),
    ]


@pytest.fixture(scope="module")
def search_environment() -> Generator[tuple[str, str]]:
    initialize_config("test")
    command = poc_command()
    try:
        subprocess.run([*command, "up", "--detach", "--wait", "--wait-timeout", "240"], check=True)
        url = str(load_settings("test").elasticsearch_url)
        alias = f"poc-es-{uuid4().hex}"
        index = f"{alias}-v1"
        asyncio.run(seed_index(url, index))
        with httpx2.Client(base_url=url, trust_env=False, timeout=10) as http:
            http.post("_aliases", json={"actions": [{"add": {"index": index, "alias": alias}}]}).raise_for_status()
            metadata = {
                "server": RootModel[dict[str, JsonValue]].model_validate(http.get("/").json()).root,
                "license": RootModel[dict[str, JsonValue]].model_validate(http.get("_license").json()).root,
            }
            output = ROOT / ".poc-results/search"
            output.mkdir(parents=True, exist_ok=True, mode=0o700)
            (output / "environment.json").write_text(json.dumps(metadata, indent=2) + "\n")
        yield url, alias
    finally:
        subprocess.run([*command, "down", "--volumes"], check=True)


async def test_bm25_and_dense_can_retrieve_the_authorized_chunk(search_environment: tuple[str, str]) -> None:
    url, alias = search_environment
    async with httpx2.AsyncClient(base_url=url, trust_env=False, timeout=10) as http:
        adapter = HybridSearchAdapter(http, alias=alias, dimensions=3)
        result = await adapter.search(
            SearchQuery(query="HR-001", kb_ids=(KB,), embedding=(1.0, 0.0, 0.0), top_k=1),
            AuthorizedSearchScope(
                subject_id=SUBJECT,
                kb_ids=frozenset({KB}),
                document_ids=frozenset({DOCUMENT}),
                policy_version="fixture-1",
            ),
        )
        assert [hit.chunk_id for hit in result.hits] == [CHUNK]
        assert (result.hits[0].dense_rank, result.hits[0].bm25_rank) == (1, 1)


async def test_basic_license_blocks_native_rrf_but_client_fusion_works(search_environment: tuple[str, str]) -> None:
    url, alias = search_environment
    async with httpx2.AsyncClient(base_url=url, trust_env=False, timeout=10) as http:
        assert (await http.get("_license")).json()["license"]["type"] == "basic"
        query: dict[str, JsonValue] = {
            "size": 1,
            "retriever": {
                "rrf": {
                    "retrievers": [
                        {"standard": {"query": {"match_none": {}}}},
                        {"standard": {"query": {"match_none": {}}}},
                    ]
                }
            },
        }
        response = await http.post(f"{alias}/_search", json=query)
        assert response.status_code == 403
        assert "Reciprocal Rank Fusion" in response.json()["error"]["reason"]
        result = await HybridSearchAdapter(http, alias=alias, dimensions=3).search(leave_query(), current_scope())
        assert result.hits[0].chunk_id == CHUNK


async def test_keyword_rank_can_promote_an_exact_identifier(search_environment: tuple[str, str]) -> None:
    url, alias = search_environment
    async with httpx2.AsyncClient(base_url=url, trust_env=False, timeout=10) as http:
        result = await HybridSearchAdapter(http, alias=alias, dimensions=3).search(
            leave_query(query="INV-2026"),
            current_scope(),
        )
        assert result.hits[0].chunk_id == UUID(int=32)
        assert (result.hits[0].dense_rank, result.hits[0].bm25_rank) == (3, 1)


async def test_dense_retrieval_survives_no_keyword_overlap(search_environment: tuple[str, str]) -> None:
    url, alias = search_environment
    async with httpx2.AsyncClient(base_url=url, trust_env=False, timeout=10) as http:
        result = await HybridSearchAdapter(http, alias=alias, dimensions=3).search(
            leave_query(query="holiday entitlement", top_k=2),
            current_scope(),
        )
        assert [hit.chunk_id for hit in result.hits] == [CHUNK, UUID(int=31)]
        assert all(hit.bm25_rank is None for hit in result.hits)


@pytest.mark.parametrize("types,expected", [(("docx",), [UUID(int=32)]), (("xlsx",), [])])
async def test_metadata_filters_apply_to_both_branches(
    search_environment: tuple[str, str],
    types: tuple[str, ...],
    expected: list[UUID],
) -> None:
    url, alias = search_environment
    async with httpx2.AsyncClient(base_url=url, trust_env=False, timeout=10) as http:
        result = await HybridSearchAdapter(http, alias=alias, dimensions=3).search(
            leave_query(source_types=types),
            current_scope(),
        )
        assert [hit.chunk_id for hit in result.hits] == expected


async def test_acl_applies_before_ranking_and_excludes_drafts_and_deleted_documents(
    search_environment: tuple[str, str],
) -> None:
    url, alias = search_environment
    async with httpx2.AsyncClient(base_url=url, trust_env=False, timeout=10) as http:
        adapter = HybridSearchAdapter(http, alias=alias, dimensions=3)
        result = await adapter.search(leave_query(candidate_k=1, top_k=1), current_scope())
        assert [hit.chunk_id for hit in result.hits] == [CHUNK]
        widened = current_scope().model_copy(update={"document_ids": frozenset(UUID(int=n) for n in range(20, 28))})
        result = await adapter.search(leave_query(), widened)
        assert {hit.chunk_id for hit in result.hits} == {CHUNK, UUID(int=31), UUID(int=32)}


async def test_revocation_is_effective_while_index_acl_snapshot_is_stale(search_environment: tuple[str, str]) -> None:
    url, alias = search_environment
    async with httpx2.AsyncClient(base_url=url, trust_env=False, timeout=10) as http:
        adapter = HybridSearchAdapter(http, alias=alias, dimensions=3)
        before = await adapter.search(leave_query(), current_scope())
        assert CHUNK in {hit.chunk_id for hit in before.hits}
        revoked = current_scope().model_copy(
            update={
                "document_ids": current_scope().document_ids - {DOCUMENT},
                "policy_version": "synthetic-policy-2",
            }
        )
        after = await adapter.search(leave_query(), revoked)
        assert CHUNK not in {hit.chunk_id for hit in after.hits}
        source = (await http.get(f"{alias}/_doc/{CHUNK}")).json()["_source"]
        assert str(SUBJECT) in source["acl_snapshot"]["subject_ids"]


async def test_cross_kb_and_missing_scope_requests_are_rejected(search_environment: tuple[str, str]) -> None:
    url, alias = search_environment
    async with httpx2.AsyncClient(base_url=url, trust_env=False, timeout=10) as http:
        adapter = HybridSearchAdapter(http, alias=alias, dimensions=3)
        with pytest.raises(SearchAccessDeniedError):
            await adapter.search(leave_query(kb_ids=(UUID(int=2),)), current_scope())
        with pytest.raises(SearchAccessDeniedError):
            await adapter.search(leave_query(), None)


async def test_wrong_vector_dimension_is_rejected_by_adapter_and_elasticsearch(
    search_environment: tuple[str, str],
) -> None:
    url, alias = search_environment
    async with httpx2.AsyncClient(base_url=url, trust_env=False, timeout=10) as http:
        with pytest.raises(ValueError, match="dimension"):
            await HybridSearchAdapter(http, alias=alias, dimensions=3).search(
                leave_query(embedding=(1.0, 0.0)),
                current_scope(),
            )
        response = await http.put(f"{alias}/_doc/invalid-dimension", json={"embedding": [1.0, 0.0]})
        assert response.status_code == 400
        assert (await http.get(f"{alias}/_doc/invalid-dimension")).status_code == 404


async def test_atomic_publication_rollback_and_concurrent_reads_use_one_index(
    search_environment: tuple[str, str],
) -> None:
    url, alias = search_environment
    first, second = f"{alias}-v1", f"{alias}-v2"
    await seed_index(url, second, version=2)
    async with httpx2.AsyncClient(base_url=url, trust_env=False, timeout=10) as http:
        adapter = HybridSearchAdapter(http, alias=alias, dimensions=3)

        async def switch(source: str, target: str) -> None:
            response = await http.post(
                "_aliases",
                json={
                    "actions": [
                        {"remove": {"index": source, "alias": alias}},
                        {"add": {"index": target, "alias": alias}},
                    ]
                },
            )
            response.raise_for_status()

        try:
            assert (await adapter.search(leave_query(), current_scope())).physical_index == first
            await switch(first, second)
            published = await adapter.search(leave_query(), current_scope())
            assert published.physical_index == second
            assert {hit.document_version for hit in published.hits} == {2}
            await switch(second, first)
            rolled_back = await adapter.search(leave_query(), current_scope())
            assert rolled_back.physical_index == first
            assert {hit.document_version for hit in rolled_back.hits} == {1}

            async def toggle() -> None:
                for _ in range(10):
                    await switch(first, second)
                    await switch(second, first)

            async def read() -> None:
                for _ in range(20):
                    result = await adapter.search(leave_query(), current_scope())
                    versions = {hit.document_version for hit in result.hits}
                    assert versions in ({1}, {2})
                    assert versions == ({1} if result.physical_index == first else {2})

            await asyncio.gather(toggle(), read())
            (
                await http.post("_aliases", json={"actions": [{"add": {"index": second, "alias": alias}}]})
            ).raise_for_status()
            with pytest.raises(SearchUnavailableError, match="exactly one"):
                await adapter.search(leave_query(), current_scope())
        finally:
            (
                await http.post(
                    "_aliases",
                    json={
                        "actions": [
                            {"remove": {"index": second, "alias": alias}},
                            {"add": {"index": first, "alias": alias}},
                        ]
                    },
                )
            ).raise_for_status()


async def test_service_outage_fails_closed_and_restart_preserves_search_data(
    search_environment: tuple[str, str],
) -> None:
    url, alias = search_environment
    await asyncio.to_thread(subprocess.run, [*poc_command(), "stop", "elasticsearch"], check=True)
    try:
        async with httpx2.AsyncClient(base_url=url, trust_env=False, timeout=0.5) as http:
            with pytest.raises(SearchUnavailableError):
                await HybridSearchAdapter(http, alias=alias, dimensions=3).search(leave_query(), current_scope())
    finally:
        await asyncio.to_thread(
            subprocess.run,
            [*poc_command(), "up", "--detach", "--wait", "--wait-timeout", "240"],
            check=True,
        )
    async with httpx2.AsyncClient(base_url=url, trust_env=False, timeout=10) as http:
        result = await HybridSearchAdapter(http, alias=alias, dimensions=3).search(leave_query(), current_scope())
        assert result.hits[0].chunk_id == CHUNK
