"""Prepare sourced answers and recheck saved messages using trusted server reads."""

from collections.abc import Iterable
from datetime import datetime
from uuid import UUID, uuid5

from app.modules.conversations.domain.contracts import (
    Citation,
    Conversation,
    Message,
    MessageStatus,
    StoredConversation,
    StoredMessage,
    citation_markers,
    evidence_version,
)
from app.modules.documents.application.access import require_published_document
from app.modules.policy.application.authorization import validate_access_context
from app.modules.policy.domain.contracts import AccessContext, AccessPurpose, AuthorizationSnapshot
from app.modules.rag.application.retrieval import validate_retrieval_result
from app.modules.rag.domain.contracts import (
    AuthorizedRetrievalScope,
    RetrievalDocumentFacts,
    RetrievalFacts,
    RetrievalResult,
)


def require_owned_conversation(
    stored: StoredConversation | None,
    context: AccessContext | None,
    authorization: AuthorizationSnapshot,
    *,
    now: datetime,
) -> Conversation:
    if context is None or validate_access_context(context, authorization, now=now, purpose=AccessPurpose.CHAT):
        raise PermissionError("Conversation access requires a current Chat identity")
    if (
        stored is None
        or stored.owner_subject_id != context.subject_id
        or stored.deleted_at is not None
        or stored.conversation.updated_at > now
    ):
        raise LookupError("Conversation is unavailable")
    return stored.conversation


def _documents_by_id(documents: Iterable[RetrievalDocumentFacts]) -> dict[UUID, RetrievalDocumentFacts]:
    by_id: dict[UUID, RetrievalDocumentFacts] = {}
    for item in documents:
        if item.published.document.id in by_id:
            raise ValueError("Current facts contain duplicate document IDs")
        by_id[item.published.document.id] = item
    return by_id


def complete_sourced_answer(
    stored: StoredConversation | None,
    pending: Message,
    answer: str,
    *,
    scope: AuthorizedRetrievalScope,
    retrieval: RetrievalResult,
    context_chunk_ids: tuple[UUID, ...],
    fresh_facts: RetrievalFacts,
    now: datetime,
) -> StoredMessage:
    """Bind model markers to the authoritative chunks sent as evidence, in prompt order."""
    context = scope.request.access_context
    conversation = require_owned_conversation(stored, context, fresh_facts.authorization, now=now)
    if (
        pending.conversation_id != conversation.id
        or pending.status is not MessageStatus.GENERATING
        or pending.trace_id != scope.request.trace_id
        or not conversation.created_at <= pending.created_at <= now
    ):
        raise ValueError("Pending answer does not belong to this generation")
    validate_retrieval_result(scope, retrieval, fresh_facts, now=now)
    retrieved = {chunk.chunk_id: chunk for chunk in retrieval.chunks}
    if len(set(context_chunk_ids)) != len(context_chunk_ids) or not set(context_chunk_ids) <= retrieved.keys():
        raise ValueError("Prompt evidence must be a unique selection from this retrieval")
    markers = citation_markers(answer)
    if not markers or max(markers) > len(context_chunk_ids):
        raise ValueError("Answer citations must refer to this generation's prompt evidence")
    documents = _documents_by_id(fresh_facts.documents)
    citations: list[Citation] = []
    for order in sorted(markers):
        chunk = retrieved[context_chunk_ids[order - 1]]
        citations.append(
            Citation(
                citation_id=uuid5(pending.id, str(order)),
                citation_order=order,
                chunk_id=chunk.chunk_id,
                kb_id=chunk.kb_id,
                document_id=chunk.document_id,
                document_version_id=chunk.document_version_id,
                document_version=chunk.document_version,
                title=documents[chunk.document_id].published.document.title,
                locations=tuple(span.location for span in chunk.source.spans),
                heading_path=chunk.metadata.heading_path,
                excerpt=chunk.content.lstrip()[:320],
            )
        )
    evidence = tuple(dict.fromkeys(evidence_version(retrieved[chunk_id]) for chunk_id in context_chunk_ids))
    return StoredMessage(
        message=Message.model_validate(
            pending.model_dump() | {"status": MessageStatus.COMPLETED, "content": answer, "citations": citations}
        ),
        evidence_versions=evidence,
    )


def require_readable_message(
    conversation: StoredConversation | None,
    stored: StoredMessage | None,
    context: AccessContext | None,
    authorization: AuthorizationSnapshot,
    documents: Iterable[RetrievalDocumentFacts],
    *,
    now: datetime,
) -> Message:
    """Guard history, citation detail and reuse as future message context."""
    owner_view = require_owned_conversation(conversation, context, authorization, now=now)
    if (
        stored is None
        or stored.message.conversation_id != owner_view.id
        or not owner_view.created_at <= stored.message.created_at <= now
    ):
        raise LookupError("Message is unavailable")
    if stored.evidence_versions:
        current = _documents_by_id(documents)
        for reference in stored.evidence_versions:
            item = current.get(reference.document_id)
            if (
                item is None
                or require_published_document(item.published, item.policy, context, authorization, now=now) != reference
            ):
                raise PermissionError("Message evidence version is unavailable")
    return stored.message
