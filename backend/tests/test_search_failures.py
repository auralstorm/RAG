"""Observe fail-closed behavior at the public adapter's HTTP system boundary."""

import asyncio
from uuid import UUID

import httpx2
import pytest
from app.adapters.elasticsearch import (
    AuthorizedSearchScope,
    HybridSearchAdapter,
    SearchAccessDeniedError,
    SearchQuery,
    SearchUnavailableError,
)

pytestmark = pytest.mark.anyio


def scope() -> AuthorizedSearchScope:
    return AuthorizedSearchScope(
        subject_id=UUID(int=10),
        kb_ids=frozenset({UUID(int=1)}),
        document_ids=frozenset({UUID(int=20)}),
        policy_version="test-policy-1",
    )


def query() -> SearchQuery:
    return SearchQuery(query="policy", kb_ids=(UUID(int=1),), embedding=(1.0, 0.0, 0.0))


@pytest.mark.parametrize("context", [None, scope().model_copy(update={"document_ids": frozenset()})])
async def test_missing_current_scope_is_rejected_before_any_search_io(context: AuthorizedSearchScope | None) -> None:
    def deny_io(_request: httpx2.Request) -> httpx2.Response:
        raise AssertionError("Unapproved search reached the external service")

    async with httpx2.AsyncClient(base_url="http://search.invalid", transport=httpx2.MockTransport(deny_io)) as http:
        with pytest.raises(SearchAccessDeniedError):
            await HybridSearchAdapter(http, alias="read-alias", dimensions=3).search(query(), context)


@pytest.mark.parametrize("failure", ["timeout", "failed_shard", "out_of_scope", "invalid_response", "unavailable"])
async def test_partial_unavailable_and_invalid_results_are_never_returned(failure: str) -> None:
    def reply(request: httpx2.Request) -> httpx2.Response:
        if request.url.path.startswith("/_alias/"):
            return httpx2.Response(200, json={"physical-v1": {"aliases": {"read-alias": {}}}})
        if failure == "unavailable":
            raise httpx2.ConnectError("private-connection-details", request=request)
        if failure == "invalid_response":
            return httpx2.Response(200, json={"unexpected": "response"})
        return httpx2.Response(
            200,
            json={
                "timed_out": failure == "timeout",
                "_shards": {"failed": 1 if failure == "failed_shard" else 0},
                "hits": {
                    "hits": [
                        {
                            "_id": str(UUID(int=30)),
                            "_source": {
                                "id": str(UUID(int=30)),
                                "document_id": str(UUID(int=999 if failure == "out_of_scope" else 20)),
                                "document_version": 1,
                                "kb_id": str(UUID(int=1)),
                                "content": "synthetic policy",
                                "status": "PUBLISHED",
                                "source_type": "pdf",
                                "acl_snapshot": {"subject_ids": [str(UUID(int=10))]},
                            },
                        }
                    ]
                },
            },
        )

    async with httpx2.AsyncClient(base_url="http://search.invalid", transport=httpx2.MockTransport(reply)) as http:
        with pytest.raises(SearchUnavailableError) as result:
            await HybridSearchAdapter(http, alias="read-alias", dimensions=3).search(query(), scope())
        assert "private-connection-details" not in str(result.value)


async def test_cancellation_is_propagated_to_the_caller() -> None:
    async def cancel(_request: httpx2.Request) -> httpx2.Response:
        raise asyncio.CancelledError

    async with httpx2.AsyncClient(base_url="http://search.invalid", transport=httpx2.MockTransport(cancel)) as http:
        with pytest.raises(asyncio.CancelledError):
            await HybridSearchAdapter(http, alias="read-alias", dimensions=3).search(query(), scope())
