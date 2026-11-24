"""Chat records and client views; owner and evidence dependencies are server facts."""

import re
from enum import StrEnum
from typing import Self
from uuid import UUID, uuid5

from pydantic import Field, model_validator

from app.core.contracts import UtcTimestamp, VersionedContract
from app.modules.documents.domain.contracts import DocumentVersionRef
from app.modules.parsing.domain.contracts import SourceLocation

MARKER = re.compile(r"\[\[cite:([1-9][0-9]{0,2})\]\]")


def citation_markers(content: str) -> set[int]:
    if re.search(r"\[\[cite", MARKER.sub("", content), flags=re.IGNORECASE):
        raise ValueError("Malformed citation marker")
    return {int(match.group(1)) for match in MARKER.finditer(content)}


class Conversation(VersionedContract):
    id: UUID
    title: str = Field(min_length=1, max_length=256, pattern=r"\S", repr=False)
    created_at: UtcTimestamp
    updated_at: UtcTimestamp

    @model_validator(mode="after")
    def require_valid_timestamps(self) -> Self:
        if self.updated_at < self.created_at:
            raise ValueError("Conversation update cannot precede creation")
        return self


class StoredConversation(VersionedContract):
    conversation: Conversation = Field(repr=False)
    owner_subject_id: UUID = Field(repr=False)
    deleted_at: UtcTimestamp | None = None

    @model_validator(mode="after")
    def require_valid_deletion(self) -> Self:
        if self.deleted_at is not None and not (
            self.conversation.created_at <= self.deleted_at <= self.conversation.updated_at
        ):
            raise ValueError("Deletion must occur during the recorded conversation lifetime")
        return self


class MessageRole(StrEnum):
    USER = "USER"
    ASSISTANT = "ASSISTANT"


class MessageStatus(StrEnum):
    GENERATING = "GENERATING"
    COMPLETED = "COMPLETED"
    REFUSED = "REFUSED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class Citation(DocumentVersionRef):
    citation_id: UUID
    chunk_id: UUID
    citation_order: int = Field(ge=1, le=100, strict=True)
    title: str = Field(min_length=1, max_length=512, pattern=r"\S", repr=False)
    locations: tuple[SourceLocation, ...] = Field(min_length=1, repr=False)
    heading_path: tuple[str, ...] = Field(repr=False)
    excerpt: str = Field(min_length=1, max_length=320, pattern=r"\S", repr=False)


class Message(VersionedContract):
    id: UUID
    conversation_id: UUID
    sequence: int = Field(ge=1, strict=True)
    role: MessageRole
    status: MessageStatus
    created_at: UtcTimestamp
    trace_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")
    content: str | None = Field(default=None, min_length=1, pattern=r"\S", repr=False)
    citations: tuple[Citation, ...] = Field(default=(), max_length=100, repr=False)

    @model_validator(mode="after")
    def require_consistent_message(self) -> Self:
        if self.role is MessageRole.USER:
            if self.status is not MessageStatus.COMPLETED or self.content is None or self.citations or self.trace_id:
                raise ValueError("A user message requires completed text without citations or a generation trace")
            return self
        if self.trace_id is None or self.trace_id == "0" * 32:
            raise ValueError("An assistant message requires a nonzero generation trace")
        if self.status is not MessageStatus.COMPLETED:
            if self.content is not None or self.citations:
                raise ValueError("Only completed assistant messages carry answer text and citations")
            return self
        orders = [citation.citation_order for citation in self.citations]
        if (
            self.content is None
            or not orders
            or orders != sorted(set(orders))
            or set(orders) != citation_markers(self.content)
            or len({citation.chunk_id for citation in self.citations}) != len(self.citations)
            or any(citation.citation_id != uuid5(self.id, str(citation.citation_order)) for citation in self.citations)
        ):
            raise ValueError("A completed answer requires matching ordered message citations")
        return self


def evidence_version(source: DocumentVersionRef) -> DocumentVersionRef:
    return DocumentVersionRef(
        kb_id=source.kb_id,
        document_id=source.document_id,
        document_version_id=source.document_version_id,
        document_version=source.document_version,
    )


class StoredMessage(VersionedContract):
    message: Message = Field(repr=False)
    evidence_versions: tuple[DocumentVersionRef, ...] = Field(default=(), max_length=100, repr=False)

    @model_validator(mode="after")
    def require_evidence_dependencies(self) -> Self:
        if len(set(self.evidence_versions)) != len(self.evidence_versions):
            raise ValueError("Message evidence dependencies must be unique")
        if any(evidence_version(citation) not in self.evidence_versions for citation in self.message.citations):
            raise ValueError("Every citation must belong to the recorded evidence dependencies")
        if not self.message.citations and self.evidence_versions:
            raise ValueError("Evidence dependencies require a completed sourced answer")
        return self
