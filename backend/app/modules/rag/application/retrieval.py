"""Pure Retriever guards; no model calls, ES DSL, queries or cached authorization are inferred."""

from datetime import datetime
from uuid import UUID

from app.modules.documents.application.access import require_published_document
from app.modules.documents.domain.contracts import DocumentVersionRef
from app.modules.knowledge_base.domain.contracts import KnowledgeBaseStatus
from app.modules.policy.application.authorization import authorize
from app.modules.policy.domain.contracts import AuthorizationRequest
from app.modules.rag.domain.contracts import (
    AuthorizedRetrievalScope,
    RetrievalFacts,
    RetrievalIndexBinding,
    RetrievalRequest,
    RetrievalResult,
)


def prepare_retrieval_scope(
    request: RetrievalRequest, facts: RetrievalFacts, *, now: datetime
) -> AuthorizedRetrievalScope:
    """Authorize all selected KBs and intersect documents with current publication and ACL facts.

    Producer supplies current resource facts independently of client inputs. Document-level
    refusal removes that document; explicit inaccessible document selections refuse the request.
    No authorized versions means no search, never an unbounded fallback.
    """
    kbs = {kb.id: kb for kb in facts.knowledge_bases}
    if len(kbs) != len(facts.knowledge_bases):
        raise ValueError("Retrieval facts contain duplicate KB IDs")
    if request.top_k > facts.max_top_k or (
        request.config_version is not None and request.config_version != facts.config_version
    ):
        raise ValueError("Retrieval configuration or limit does not match the resolved server configuration")
    for kb_id in request.kb_ids:
        decision = authorize(
            AuthorizationRequest(permission_code="kb.read", purpose=request.access_context.purpose, kb_id=kb_id),
            request.access_context,
            facts.authorization,
            now=now,
        )
        kb = kbs.get(kb_id)
        if not decision.allowed or kb is None or kb.status is not KnowledgeBaseStatus.ACTIVE or now < kb.updated_at:
            raise PermissionError("Retrieval requires current permission for every selected active KB")
    bindings: dict[UUID, RetrievalIndexBinding] = {}
    references: list[DocumentVersionRef] = []
    seen_documents: set[UUID] = set()
    for item in facts.documents:
        published = item.published
        if published.document.id in seen_documents:
            raise ValueError("Retrieval facts contain duplicate logical document IDs")
        seen_documents.add(published.document.id)
        if published.kb.id not in request.kb_ids:
            continue
        if published.kb != kbs[published.kb.id]:
            raise ValueError("Document facts disagree with the selected current KB")
        try:
            reference = require_published_document(
                published, item.policy, request.access_context, facts.authorization, now=now
            )
        except PermissionError:
            continue
        if request.filters.source_types and published.document.source_type not in request.filters.source_types:
            continue
        if request.filters.document_ids and reference.document_id not in request.filters.document_ids:
            continue
        references.append(reference)
        binding = RetrievalIndexBinding(
            kb_id=reference.kb_id,
            index_version_id=published.index.id,
            embedding=published.index.embedding,
            chunking_config_version=published.index.chunking_config_version,
            pipeline_version=published.index.pipeline_version,
        )
        previous = bindings.get(reference.kb_id)
        if previous is not None and previous != binding:
            raise ValueError("Retrieved documents disagree about their active vector space")
        bindings[reference.kb_id] = binding
    if request.filters.document_ids and not set(request.filters.document_ids) <= {
        ref.document_id for ref in references
    }:
        raise PermissionError("Explicit document selection includes an inaccessible document")
    return AuthorizedRetrievalScope(
        request=request,
        config_version=facts.config_version,
        index_bindings=tuple(bindings.values()),
        document_versions=tuple(references),
        prepared_at=now,
        expires_at=min(request.access_context.expires_at, facts.authorization.expires_at),
    )


def validate_retrieval_result(
    scope: AuthorizedRetrievalScope, result: RetrievalResult, fresh_facts: RetrievalFacts, *, now: datetime
) -> RetrievalResult:
    """Recheck current authorization and authoritative chunk text/source before content leaves Retriever.

    Index/configuration switches require a new retrieval. Current chunks come from the trusted
    version artifact, not from search response fields; missing evidence refuses the entire result.
    """
    if now.tzinfo is None or now.utcoffset() is None or not scope.prepared_at <= now < scope.expires_at:
        raise PermissionError("Prepared retrieval scope is expired or has an invalid server clock")
    fresh = prepare_retrieval_scope(scope.request, fresh_facts, now=now)
    if fresh.config_version != scope.config_version:
        raise ValueError("Retrieval configuration changed during execution")
    if (
        result.diagnostics.trace_id != scope.request.trace_id
        or result.diagnostics.config_version != scope.config_version
    ):
        raise ValueError("Retrieval diagnostics do not belong to this request")
    if len(result.chunks) > scope.request.top_k:
        raise ValueError("Retrieval returned more chunks than requested")
    chunks = {chunk.id: chunk for chunk in fresh_facts.chunks}
    if len(chunks) != len(fresh_facts.chunks):
        raise ValueError("Current candidate evidence contains duplicate chunk IDs")
    indices = {binding.kb_id: binding for binding in fresh.index_bindings}
    original_indices = {binding.kb_id: binding for binding in scope.index_bindings}
    readable_versions = frozenset(scope.document_versions).intersection(fresh.document_versions)
    for candidate in result.chunks:
        chunk = chunks.get(candidate.chunk_id)
        binding = indices.get(candidate.kb_id)
        if chunk is None or binding is None or binding != original_indices.get(candidate.kb_id):
            raise PermissionError("Candidate chunk or active index is outside the current retrieval scope")
        if candidate.index_version_id != binding.index_version_id:
            raise PermissionError("Candidate came from a different index version")
        if chunk.chunking_config_version != binding.chunking_config_version:
            raise PermissionError("Candidate chunk uses a different chunking configuration")
        reference = DocumentVersionRef(
            kb_id=candidate.kb_id,
            document_id=candidate.document_id,
            document_version_id=candidate.document_version_id,
            document_version=candidate.document_version,
        )
        if reference not in readable_versions:
            raise PermissionError("Candidate document version is no longer authorized")
        if (
            any(
                getattr(candidate, field) != getattr(chunk, field)
                for field in (
                    "kb_id",
                    "document_id",
                    "document_version_id",
                    "document_version",
                    "content",
                    "source",
                    "metadata",
                )
            )
            or now < chunk.created_at
        ):
            raise PermissionError("Candidate content or source does not match the authoritative chunk")
    return result
