"""Exercise source fidelity, version-bound chunks and current Retriever authorization."""

import hashlib
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from app.modules.chunking.application.validation import validate_chunk_set
from app.modules.chunking.domain.contracts import Chunk, ChunkMetadata, ChunkRole, ChunkSource, ChunkSourceSpan
from app.modules.conversations.application.messages import (
    complete_sourced_answer,
    prepare_sourced_generation,
    require_owned_conversation,
    require_readable_message,
)
from app.modules.conversations.domain.contracts import (
    Conversation,
    Message,
    MessageRole,
    MessageStatus,
    StoredConversation,
)
from app.modules.documents.domain.contracts import (
    Document,
    DocumentAccessPolicy,
    DocumentSourceType,
    DocumentStatus,
    DocumentVersion,
    DocumentVersionRef,
    DocumentVersionStatus,
    StoredObjectRef,
)
from app.modules.iam.domain.contracts import ExternalIdentity, IdentityStatus, User, UserStatus
from app.modules.knowledge_base.domain.contracts import EmbeddingBinding, KnowledgeBase, KnowledgeBaseStatus
from app.modules.parsing.application.validation import validate_parser_output
from app.modules.parsing.domain.contracts import (
    BoundingBox,
    DocxSourceLocation,
    MarkdownSourceLocation,
    ParsedBlock,
    ParsedBlockType,
    ParsedDocument,
    ParsedPage,
    ParsedTable,
    ParserInput,
    ParsingWarning,
    PdfSourceLocation,
)
from app.modules.policy.application.authorization import actor_reference
from app.modules.policy.domain.contracts import (
    AccessContext,
    AccessPurpose,
    AuthorizationSnapshot,
    KnowledgePermission,
    ResourceGrant,
    ResourcePrincipalType,
)
from app.modules.rag.application.retrieval import prepare_retrieval_scope, validate_retrieval_result
from app.modules.rag.domain.contracts import (
    RetrievalDiagnostics,
    RetrievalDocumentFacts,
    RetrievalFacts,
    RetrievalFilters,
    RetrievalRequest,
    RetrievalResult,
    RetrievalSelection,
    RetrievedChunk,
    ScoreComponents,
)
from app.modules.search.domain.contracts import (
    IndexAlias,
    IndexManifest,
    IndexValidationReport,
    IndexVersionStatus,
    PublishedDocumentSnapshot,
    StoredIndexVersion,
    ValidationVerdict,
    index_binding_hash,
)
from pydantic import BaseModel, ValidationError

NOW = datetime(2026, 11, 24, 10, tzinfo=UTC)
USER, KB, DOC, VERSION, INDEX, MODEL, CHUNK = (UUID(int=i) for i in range(1, 8))
TEXT = "知🙂识证据"
FILE_HASH = hashlib.sha256(b"synthetic original file").hexdigest()


def changed[ModelT: BaseModel](model: ModelT, **updates: object) -> ModelT:
    return type(model).model_validate({**model.model_dump(), **updates})


def reference() -> DocumentVersionRef:
    return DocumentVersionRef(kb_id=KB, document_id=DOC, document_version_id=VERSION, document_version=1)


def parsed_document() -> ParsedDocument:
    return ParsedDocument(
        **reference().model_dump(),
        file_hash=FILE_HASH,
        mime_type="application/pdf",
        parser_name="synthetic-parser",
        parser_version="fixture-v1",
        pages=(
            ParsedPage(
                page_no=1,
                blocks=(
                    ParsedBlock(
                        block_id="block-1",
                        block_type=ParsedBlockType.PARAGRAPH,
                        text=TEXT,
                        heading_path=("Synthetic heading",),
                        source_location=PdfSourceLocation(page_no=1),
                    ),
                ),
            ),
        ),
    )


def chunk() -> Chunk:
    block = parsed_document().pages[0].blocks[0]
    return Chunk(
        **reference().model_dump(),
        id=CHUNK,
        chunk_index=0,
        role=ChunkRole.STANDALONE,
        parent_chunk_id=None,
        content=TEXT,
        content_hash=hashlib.sha256(TEXT.encode()).hexdigest(),
        token_count=5,
        tokenizer_version="synthetic-tokenizer-v1",
        chunking_config_version="chunks-v1",
        source=ChunkSource(
            spans=(
                ChunkSourceSpan(
                    block_id=block.block_id, char_start=0, char_end=len(TEXT), location=block.source_location
                ),
            )
        ),
        metadata=ChunkMetadata(heading_path=block.heading_path),
        created_at=NOW - timedelta(hours=1),
    )


def scenario() -> tuple[RetrievalRequest, RetrievalFacts]:
    binding = EmbeddingBinding(embedding_model_id=MODEL, config_version="model-v1", dimensions=3)
    kb = KnowledgeBase(
        id=KB,
        name="Synthetic",
        status=KnowledgeBaseStatus.ACTIVE,
        embedding=binding,
        active_index_version_id=INDEX,
        created_by=USER,
        created_at=NOW - timedelta(hours=2),
        updated_at=NOW,
    )
    document = Document(
        id=DOC,
        kb_id=KB,
        title="Synthetic",
        source_type=DocumentSourceType.UPLOAD,
        current_version=2,
        status=DocumentStatus.ACTIVE,
        acl_policy_id=None,
        created_by=USER,
        created_at=NOW - timedelta(hours=2),
        updated_at=NOW,
    )
    version = DocumentVersion(
        **reference().model_dump(),
        status=DocumentVersionStatus.PUBLISHED,
        mime_type="application/pdf",
        file_size=100,
        file_hash=FILE_HASH,
        pipeline_version="pipeline-v1",
        parser_name="synthetic-parser",
        parser_version="fixture-v1",
        chunking_config_version="chunks-v1",
        created_at=NOW - timedelta(hours=2),
        updated_at=NOW,
        published_at=NOW - timedelta(hours=1),
    )
    manifest = IndexManifest(index_version_id=INDEX, kb_id=KB, documents=(reference(),))
    report = IndexValidationReport(
        id=UUID(int=20),
        index_version_id=INDEX,
        manifest_sha256=manifest.content_hash,
        binding_sha256=index_binding_hash(binding, "chunks-v1", "pipeline-v1"),
        verdict=ValidationVerdict.PASSED,
        expected_document_count=1,
        actual_document_count=1,
        expected_chunk_count=1,
        actual_chunk_count=1,
        mapping_verified=True,
        acl_verified=True,
        retrieval_verified=True,
        quality_gate_verified=True,
        checked_at=NOW - timedelta(hours=1),
    )
    index = StoredIndexVersion(
        id=INDEX,
        kb_id=KB,
        version=1,
        status=IndexVersionStatus.ACTIVE,
        embedding=binding,
        chunking_config_version="chunks-v1",
        pipeline_version="pipeline-v1",
        manifest_sha256=manifest.content_hash,
        validation_report_id=report.id,
        created_at=NOW - timedelta(hours=2),
        updated_at=NOW,
        published_at=NOW - timedelta(hours=1),
        physical_index_name="synthetic_v1",
        alias_name="synthetic_read",
        validation=report,
    )
    packet = PublishedDocumentSnapshot(
        kb=kb,
        document=document,
        version=version,
        index=index,
        manifest=manifest,
        alias=IndexAlias(
            kb_id=KB,
            alias_name=index.alias_name,
            active_index_version_id=INDEX,
            physical_index_name=index.physical_index_name,
        ),
    )
    actor = actor_reference(USER, b"synthetic-actor-key-32-bytes-long!!")
    identity = ExternalIdentity(
        id=UUID(int=21),
        user_id=USER,
        provider_key="synthetic",
        issuer="https://example.test/login",
        subject="synthetic-user",
        status=IdentityStatus.ACTIVE,
    )
    context = AccessContext(
        subject_id=USER,
        identity_id=identity.id,
        actor_ref=actor,
        environment="test",
        purpose=AccessPurpose.CHAT,
        policy_version="policy-v1",
        issued_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(minutes=10),
    )
    authority = AuthorizationSnapshot(
        user=User(id=USER, display_name="Synthetic", status=UserStatus.ACTIVE, created_at=NOW, updated_at=NOW),
        identity=identity,
        actor_ref=actor,
        environment="test",
        purpose=AccessPurpose.CHAT,
        policy_version="policy-v1",
        role_ids=frozenset(),
        group_ids=frozenset(),
        permission_codes=frozenset({"kb.read"}),
        resource_grants=(
            ResourceGrant(
                id=UUID(int=22),
                kb_id=KB,
                principal_type=ResourcePrincipalType.USER,
                principal_id=USER,
                permission=KnowledgePermission.READ,
            ),
        ),
        subject_bindings=(),
        observed_at=NOW,
        expires_at=NOW + timedelta(minutes=5),
    )
    request = RetrievalRequest(
        query="Synthetic question", kb_ids=(KB,), top_k=3, access_context=context, trace_id="a" * 32
    )
    facts = RetrievalFacts(
        authorization=authority,
        config_version="retrieval-v1",
        max_top_k=5,
        knowledge_bases=(kb,),
        documents=(
            RetrievalDocumentFacts(
                published=packet,
                policy=DocumentAccessPolicy(
                    document_id=DOC, kb_id=KB, acl_policy_id=None, allowed_subject_ids=None, policy_version="policy-v1"
                ),
            ),
        ),
        chunks=(chunk(),),
    )
    return request, facts


def result() -> RetrievalResult:
    item = chunk()
    return RetrievalResult(
        chunks=(
            RetrievedChunk(
                **reference().model_dump(),
                chunk_id=item.id,
                index_version_id=INDEX,
                content=item.content,
                score=1 / 61,
                score_components=ScoreComponents(dense_rank=1, rrf_score=1 / 61),
                source=item.source,
                metadata=item.metadata,
            ),
        ),
        diagnostics=RetrievalDiagnostics(
            trace_id="a" * 32, config_version="retrieval-v1", returned_chunk_count=1, elapsed_ms=10
        ),
    )


def pending_answer() -> tuple[StoredConversation, Message]:
    conversation = Conversation(id=UUID(int=20), title="问答", created_at=NOW, updated_at=NOW)
    return StoredConversation(conversation=conversation, owner_subject_id=USER), Message(
        id=UUID(int=21),
        conversation_id=conversation.id,
        sequence=2,
        role=MessageRole.ASSISTANT,
        status=MessageStatus.GENERATING,
        created_at=NOW,
        trace_id=result().diagnostics.trace_id,
    )


def test_answer_citation_uses_authoritative_metadata_and_can_be_read_by_the_owner() -> None:
    request, facts = scenario()
    owner, pending = pending_answer()
    retrieved = result()
    generation = prepare_sourced_generation(
        owner,
        pending,
        scope=prepare_retrieval_scope(request, facts, now=NOW),
        retrieval=retrieved,
        context_chunk_ids=(CHUNK,),
        fresh_facts=facts,
        now=NOW,
    )
    completed = complete_sourced_answer(
        owner, generation, "答案 [[cite:1]]，补充说明 [[cite:1]]", fresh_facts=facts, now=NOW
    )
    assert completed.evidence_versions == (reference(),)
    (citation,) = completed.message.citations
    assert completed.message.status is MessageStatus.COMPLETED
    assert citation.title == facts.documents[0].published.document.title
    assert citation.excerpt == TEXT
    assert citation.locations == tuple(span.location for span in retrieved.chunks[0].source.spans)
    assert (
        require_readable_message(
            owner, completed, request.access_context, facts.authorization, facts.documents, now=NOW
        )
        == completed.message
    )


@pytest.mark.parametrize("answer", ["答案", "答案 [[cite:2]]", "答案 [[cite:01]]", "答案 [[cite:1]] [[CITE:1]]"])
def test_answer_rejects_missing_unknown_or_malformed_markers(answer: str) -> None:
    request, facts = scenario()
    owner, pending = pending_answer()
    generation = prepare_sourced_generation(
        owner,
        pending,
        scope=prepare_retrieval_scope(request, facts, now=NOW),
        retrieval=result(),
        context_chunk_ids=(CHUNK,),
        fresh_facts=facts,
        now=NOW,
    )
    with pytest.raises(ValueError, match="citation"):
        complete_sourced_answer(owner, generation, answer, fresh_facts=facts, now=NOW)


@pytest.mark.parametrize("selection", [(), (CHUNK, CHUNK), (UUID(int=99),)])
def test_model_cannot_cite_chunks_outside_the_prompt_selection(selection: tuple[UUID, ...]) -> None:
    request, facts = scenario()
    owner, pending = pending_answer()
    with pytest.raises(ValueError, match="evidence"):
        prepare_sourced_generation(
            owner,
            pending,
            scope=prepare_retrieval_scope(request, facts, now=NOW),
            retrieval=result(),
            context_chunk_ids=selection,
            fresh_facts=facts,
            now=NOW,
        )


def test_conversation_owner_check_conceals_missing_deleted_and_foreign_records() -> None:
    request, facts = scenario()
    owner, _pending = pending_answer()
    for record in (None, changed(owner, owner_subject_id=UUID(int=99)), changed(owner, deleted_at=NOW)):
        with pytest.raises(LookupError, match="Conversation is unavailable"):
            require_owned_conversation(record, request.access_context, facts.authorization, now=NOW)
    with pytest.raises(PermissionError, match="current Chat identity"):
        require_owned_conversation(owner, None, facts.authorization, now=NOW)
    admin = changed(request.access_context, purpose=AccessPurpose.ADMIN)
    with pytest.raises(PermissionError, match="current Chat identity"):
        require_owned_conversation(owner, admin, changed(facts.authorization, purpose=AccessPurpose.ADMIN), now=NOW)


def test_revocation_hides_the_entire_answer_during_completion_and_history() -> None:
    request, facts = scenario()
    owner, pending = pending_answer()
    scope = prepare_retrieval_scope(request, facts, now=NOW)
    generation = prepare_sourced_generation(
        owner,
        pending,
        scope=scope,
        retrieval=result(),
        context_chunk_ids=(CHUNK,),
        fresh_facts=facts,
        now=NOW,
    )
    completed = complete_sourced_answer(owner, generation, "答案 [[cite:1]]", fresh_facts=facts, now=NOW)
    document = facts.documents[0]
    policy_id = UUID(int=50)
    restricted = changed(
        document,
        published=changed(document.published, document=changed(document.published.document, acl_policy_id=policy_id)),
        policy=changed(document.policy, acl_policy_id=policy_id, allowed_subject_ids=frozenset({UUID(int=99)})),
    )
    with pytest.raises(PermissionError):
        complete_sourced_answer(
            owner,
            generation,
            "答案 [[cite:1]]",
            fresh_facts=changed(facts, documents=(restricted,)),
            now=NOW,
        )
    for documents in ((), (restricted,)):
        with pytest.raises(PermissionError):
            require_readable_message(owner, completed, request.access_context, facts.authorization, documents, now=NOW)
    with pytest.raises(LookupError, match="Message is unavailable"):
        require_readable_message(
            owner,
            changed(completed, message=changed(completed.message, conversation_id=UUID(int=99))),
            request.access_context,
            facts.authorization,
            facts.documents,
            now=NOW,
        )


def test_history_requires_uncited_dependencies_and_valid_message_states() -> None:
    request, facts = scenario()
    owner, pending = pending_answer()
    with pytest.raises(ValidationError, match="Only completed"):
        changed(pending, status=MessageStatus.CANCELLED, content="partial private output")
    with pytest.raises(ValidationError, match="matching ordered"):
        changed(pending, status=MessageStatus.COMPLETED, content="answer without evidence")
    uncited = changed(reference(), document_id=UUID(int=90), document_version_id=UUID(int=91))
    source = facts.documents[0]
    packet = source.published
    manifest = changed(packet.manifest, documents=(reference(), uncited))
    assert packet.index.validation is not None
    report = changed(
        packet.index.validation,
        manifest_sha256=manifest.content_hash,
        expected_document_count=2,
        actual_document_count=2,
        expected_chunk_count=2,
        actual_chunk_count=2,
    )
    packet = changed(
        packet, manifest=manifest, index=changed(packet.index, manifest_sha256=manifest.content_hash, validation=report)
    )
    second_source = changed(
        source,
        published=changed(
            packet,
            document=changed(packet.document, id=uncited.document_id),
            version=changed(
                packet.version, document_id=uncited.document_id, document_version_id=uncited.document_version_id
            ),
        ),
        policy=changed(source.policy, document_id=uncited.document_id),
    )
    second_chunk = changed(
        chunk(), id=UUID(int=92), document_id=uncited.document_id, document_version_id=uncited.document_version_id
    )
    facts = changed(facts, documents=(changed(source, published=packet), second_source), chunks=(chunk(), second_chunk))
    retrieved = result()
    first_chunk = retrieved.chunks[0]
    retrieved = changed(
        retrieved,
        chunks=(
            first_chunk,
            changed(
                first_chunk,
                chunk_id=second_chunk.id,
                document_id=uncited.document_id,
                document_version_id=uncited.document_version_id,
            ),
        ),
        diagnostics=changed(retrieved.diagnostics, returned_chunk_count=2),
    )
    generation = prepare_sourced_generation(
        owner,
        pending,
        scope=prepare_retrieval_scope(request, facts, now=NOW),
        retrieval=retrieved,
        context_chunk_ids=(CHUNK, second_chunk.id),
        fresh_facts=facts,
        now=NOW,
    )
    completed = complete_sourced_answer(owner, generation, "答案 [[cite:1]]", fresh_facts=facts, now=NOW)
    assert completed.evidence_versions == (reference(), uncited)
    assert tuple(citation.chunk_id for citation in completed.message.citations) == (CHUNK,)
    with pytest.raises(PermissionError, match="evidence version is unavailable"):
        require_readable_message(
            owner, completed, request.access_context, facts.authorization, facts.documents[:1], now=NOW
        )
    with pytest.raises(ValidationError, match="recorded evidence dependencies"):
        changed(completed, evidence_versions=())


def test_parser_output_is_bound_to_authorized_source_version() -> None:
    source = ParserInput(
        **reference().model_dump(),
        mime_type="application/pdf",
        original=StoredObjectRef(bucket="synthetic", object_key="source", sha256=FILE_HASH, size_bytes=100),
    )
    parsed = parsed_document()
    assert validate_parser_output(source, parsed) == parsed
    for update in ({"kb_id": UUID(int=50)}, {"document_version": 2}, {"file_hash": "b" * 64}):
        with pytest.raises(ValueError, match="authorized source"):
            validate_parser_output(source, changed(parsed, **update))
    assert "object_key" not in parsed.model_dump() and TEXT not in repr(parsed)


@pytest.mark.parametrize("kind", ["markdown", "docx"])
def test_unpaginated_formats_keep_real_source_coordinates_without_fake_pages(kind: str) -> None:
    parsed = parsed_document()
    location = (
        MarkdownSourceLocation(char_start=10, char_end=15)
        if kind == "markdown"
        else DocxSourceLocation(element_index=0, element_type="paragraph")
    )
    block = changed(parsed.pages[0].blocks[0], source_location=location)
    mime = (
        "text/markdown"
        if kind == "markdown"
        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    unpaged = changed(parsed, mime_type=mime, pages=(ParsedPage(page_no=None, blocks=(block,)),))
    assert unpaged.pages[0].page_no is None
    with pytest.raises(ValidationError, match="invented page"):
        changed(unpaged, pages=(ParsedPage(page_no=1, blocks=(block,)),))


@pytest.mark.parametrize("error", ["duplicate", "page", "format", "warning"])
def test_parser_rejects_ambiguous_or_wrong_source_locations(error: str) -> None:
    parsed = parsed_document()
    block = parsed.pages[0].blocks[0]
    with pytest.raises(ValidationError):
        if error == "duplicate":
            changed(parsed, pages=(ParsedPage(page_no=1, blocks=(block, block)),))
        elif error == "page":
            changed(
                parsed,
                pages=(ParsedPage(page_no=1, blocks=(changed(block, source_location=PdfSourceLocation(page_no=2)),)),),
            )
        elif error == "format":
            changed(
                parsed,
                pages=(
                    ParsedPage(
                        page_no=1,
                        blocks=(changed(block, source_location=MarkdownSourceLocation(char_start=0, char_end=1)),),
                    ),
                ),
            )
        else:
            changed(
                parsed, warnings=(ParsingWarning(code="STRUCTURE_LOSS", source_location=PdfSourceLocation(page_no=2)),)
            )


def test_blank_pdf_pages_retain_original_page_number_and_table_cells_are_structured() -> None:
    parsed = parsed_document()
    block = changed(
        parsed.pages[0].blocks[0],
        block_type=ParsedBlockType.TABLE,
        source_location=PdfSourceLocation(page_no=2),
        table=ParsedTable(rows=(("a", "b"), ("c", "d"))),
    )
    document = changed(parsed, pages=(ParsedPage(page_no=1, blocks=()), ParsedPage(page_no=2, blocks=(block,))))
    assert document.pages[1].blocks[0].table is not None
    with pytest.raises(ValidationError, match="structured cells"):
        changed(block, table=None)
    with pytest.raises(ValidationError, match="column count"):
        ParsedTable(rows=(("a", "b"), ("c",)))


@pytest.mark.parametrize("update", [{"right": 0}, {"left": -0.1}, {"bottom": float("nan")}])
def test_pdf_coordinates_reject_degenerate_or_nonfinite_boxes(update: dict[str, object]) -> None:
    box = BoundingBox(left=0, top=0, right=1, bottom=1)
    with pytest.raises(ValidationError):
        changed(box, **update)


def test_chunk_spans_use_unicode_codepoints_and_can_preserve_parent_context() -> None:
    parent = changed(chunk(), role=ChunkRole.PARENT)
    child_text = TEXT[1:3]
    child = changed(
        chunk(),
        id=UUID(int=30),
        chunk_index=1,
        role=ChunkRole.CHILD,
        parent_chunk_id=parent.id,
        content=child_text,
        content_hash=hashlib.sha256(child_text.encode()).hexdigest(),
        source=ChunkSource(spans=(changed(parent.source.spans[0], char_start=1, char_end=3),)),
    )
    assert child.content == "🙂识"
    assert validate_chunk_set(parsed_document(), (parent, child)) == (parent, child)
    with pytest.raises(ValueError, match="parent in the same"):
        validate_chunk_set(parsed_document(), (child,))
    shortened = changed(
        parent,
        content=TEXT[:2],
        content_hash=hashlib.sha256(TEXT[:2].encode()).hexdigest(),
        source=ChunkSource(spans=(changed(parent.source.spans[0], char_end=2),)),
    )
    with pytest.raises(ValueError, match="outside its parent"):
        validate_chunk_set(parsed_document(), (shortened, child))


@pytest.mark.parametrize("error", ["version", "offset", "location", "fabricated", "heading", "duplicate", "config"])
def test_chunk_set_rejects_invalid_version_text_sources_and_configuration(error: str) -> None:
    item = chunk()
    items = (item,)
    if error == "version":
        items = (changed(item, document_version=2),)
    elif error == "offset":
        items = (changed(item, source=ChunkSource(spans=(changed(item.source.spans[0], char_end=100),))),)
    elif error == "location":
        items = (
            changed(
                item, source=ChunkSource(spans=(changed(item.source.spans[0], location=PdfSourceLocation(page_no=2)),))
            ),
        )
    elif error == "fabricated":
        items = (changed(item, content="fabricated", content_hash=hashlib.sha256(b"fabricated").hexdigest()),)
    elif error == "heading":
        items = (changed(item, metadata=ChunkMetadata(heading_path=("wrong",))),)
    elif error == "duplicate":
        items = (item, item)
    else:
        items = (item, changed(item, id=UUID(int=40), chunk_index=1, chunking_config_version="other"))
    with pytest.raises(ValueError):
        validate_chunk_set(parsed_document(), items)


def test_chunk_digest_and_ranges_reject_invalid_boundary_data() -> None:
    with pytest.raises(ValidationError, match="digest"):
        changed(chunk(), content="tampered")
    with pytest.raises(ValidationError, match="half-open"):
        changed(chunk().source.spans[0], char_start=5, char_end=5)
    with pytest.raises(ValidationError, match="half-open"):
        MarkdownSourceLocation(char_start=2, char_end=1)
    with pytest.raises(ValidationError):
        changed(chunk(), schema_version="2.0")
    assert validate_chunk_set(changed(parsed_document(), pages=(ParsedPage(page_no=1, blocks=()),)), ()) == ()


def test_chunk_source_spans_preserve_reading_order_and_do_not_repeat_overlaps() -> None:
    parsed = parsed_document()
    span = chunk().source.spans[0]
    repeated_text = TEXT + "\n\n" + TEXT
    repeated = changed(
        chunk(),
        content=repeated_text,
        content_hash=hashlib.sha256(repeated_text.encode()).hexdigest(),
        source=ChunkSource(spans=(span, span)),
    )
    with pytest.raises(ValueError, match="reading order"):
        validate_chunk_set(parsed, (repeated,))
    second = changed(parsed.pages[0].blocks[0], block_id="block-2", text="second")
    parsed = changed(parsed, pages=(changed(parsed.pages[0], blocks=(parsed.pages[0].blocks[0], second)),))
    reversed_text = "second\n\n" + TEXT
    reversed_chunk = changed(
        chunk(),
        content=reversed_text,
        content_hash=hashlib.sha256(reversed_text.encode()).hexdigest(),
        source=ChunkSource(spans=(changed(span, block_id="block-2", char_end=6), span)),
    )
    with pytest.raises(ValueError, match="reading order"):
        validate_chunk_set(parsed, (reversed_chunk,))


@pytest.mark.parametrize("field", ["access_context", "filter_expr", "acl_snapshot", "trace_id"])
def test_public_selection_rejects_identity_raw_dsl_and_other_server_fields(field: str) -> None:
    with pytest.raises(ValidationError):
        RetrievalSelection.model_validate(
            {"query": "question", "kb_ids": [str(KB)], "top_k": 3, field: {"synthetic": True}}
        )
    with pytest.raises(ValidationError):
        RetrievalRequest.model_validate({"query": "question", "kb_ids": [str(KB)], "top_k": 3, "trace_id": "a" * 32})


def test_scope_uses_current_index_vector_space_and_empty_filters_are_bounded() -> None:
    request, facts = scenario()
    current = facts.documents[0].published
    desired = changed(current.kb, embedding=changed(current.kb.embedding, dimensions=4))
    updated = changed(
        facts,
        knowledge_bases=(desired,),
        documents=(changed(facts.documents[0], published=changed(current, kb=desired)),),
    )
    scope = prepare_retrieval_scope(request, updated, now=NOW)
    assert scope.document_versions == (reference(),) and scope.index_bindings[0].embedding.dimensions == 3
    assert scope.expires_at == facts.authorization.expires_at
    empty = prepare_retrieval_scope(
        changed(request, filters=RetrievalFilters(source_types=(DocumentSourceType.CONNECTOR,))), facts, now=NOW
    )
    assert empty.document_versions == () and empty.index_bindings == ()


@pytest.mark.parametrize("error", ["grant", "inactive", "other_kb", "top_k", "config", "document"])
def test_retrieval_preparation_requires_current_authority_and_server_limits(error: str) -> None:
    request, facts = scenario()
    if error == "grant":
        facts = changed(facts, authorization=changed(facts.authorization, resource_grants=()))
    elif error == "inactive":
        facts = changed(
            facts,
            authorization=changed(
                facts.authorization, user=changed(facts.authorization.user, status=UserStatus.DISABLED)
            ),
        )
    elif error == "other_kb":
        request = changed(request, kb_ids=(KB, UUID(int=50)))
    elif error == "top_k":
        request = changed(request, top_k=6)
    elif error == "config":
        request = changed(request, config_version="unknown")
    else:
        request = changed(request, filters=RetrievalFilters(document_ids=(UUID(int=50),)))
    with pytest.raises((PermissionError, ValueError)):
        prepare_retrieval_scope(request, facts, now=NOW)


def test_current_document_acl_intersects_kb_access_before_search_and_before_return() -> None:
    request, facts = scenario()
    scope = prepare_retrieval_scope(request, facts, now=NOW)
    item = facts.documents[0]
    denied = changed(
        item,
        published=changed(item.published, document=changed(item.published.document, acl_policy_id=UUID(int=50))),
        policy=changed(item.policy, acl_policy_id=UUID(int=50), allowed_subject_ids=frozenset[UUID]()),
    )
    fresh = changed(facts, documents=(denied,))
    assert prepare_retrieval_scope(request, fresh, now=NOW).document_versions == ()
    with pytest.raises(PermissionError):
        validate_retrieval_result(scope, result(), fresh, now=NOW)
    with pytest.raises(PermissionError):
        validate_retrieval_result(
            scope, result(), changed(facts, authorization=changed(facts.authorization, resource_grants=())), now=NOW
        )


@pytest.mark.parametrize("error", ["content", "source", "version", "index", "missing_chunk", "chunk_config"])
def test_result_validation_refuses_tampered_or_unbound_candidates(error: str) -> None:
    request, facts = scenario()
    scope = prepare_retrieval_scope(request, facts, now=NOW)
    response = result()
    candidate = response.chunks[0]
    if error == "content":
        candidate = changed(candidate, content="tampered")
    elif error == "source":
        candidate = changed(
            candidate,
            source=ChunkSource(spans=(changed(candidate.source.spans[0], location=PdfSourceLocation(page_no=2)),)),
        )
    elif error == "version":
        candidate = changed(candidate, document_version=2)
    elif error == "index":
        candidate = changed(candidate, index_version_id=UUID(int=50))
    elif error == "missing_chunk":
        facts = changed(facts, chunks=())
    else:
        facts = changed(facts, chunks=(changed(chunk(), chunking_config_version="other-chunks"),))
    with pytest.raises(PermissionError):
        validate_retrieval_result(scope, changed(response, chunks=(candidate,)), facts, now=NOW)


@pytest.mark.parametrize("has_chunks", [True, False])
def test_result_validation_rechecks_index_publication_and_rejects_stale_results(has_chunks: bool) -> None:
    request, facts = scenario()
    scope = prepare_retrieval_scope(request, facts, now=NOW)
    packet = facts.documents[0].published
    target_id = UUID(int=60)
    manifest = changed(packet.manifest, index_version_id=target_id)
    assert packet.index.validation is not None
    report = changed(packet.index.validation, index_version_id=target_id, manifest_sha256=manifest.content_hash)
    active = changed(
        packet.index,
        id=target_id,
        manifest_sha256=manifest.content_hash,
        validation=report,
        physical_index_name="synthetic_v2",
    )
    kb = changed(packet.kb, active_index_version_id=target_id)
    packet = changed(
        packet,
        kb=kb,
        index=active,
        manifest=manifest,
        alias=changed(packet.alias, active_index_version_id=target_id, physical_index_name=active.physical_index_name),
    )
    fresh = changed(facts, knowledge_bases=(kb,), documents=(changed(facts.documents[0], published=packet),))
    response = result()
    if not has_chunks:
        response = changed(response, chunks=(), diagnostics=changed(response.diagnostics, returned_chunk_count=0))
    with pytest.raises(PermissionError, match="active index"):
        validate_retrieval_result(scope, response, fresh, now=NOW)


def test_result_metadata_limits_and_expiry_are_checked_without_exposing_content() -> None:
    request, facts = scenario()
    scope = prepare_retrieval_scope(request, facts, now=NOW)
    response = result()
    assert validate_retrieval_result(scope, response, facts, now=NOW) == response
    for diagnostics in (
        changed(response.diagnostics, trace_id="b" * 32),
        changed(response.diagnostics, config_version="other"),
    ):
        with pytest.raises(ValueError, match="diagnostics"):
            validate_retrieval_result(scope, changed(response, diagnostics=diagnostics), facts, now=NOW)
    with pytest.raises(PermissionError, match="expired"):
        validate_retrieval_result(scope, response, facts, now=scope.expires_at)
    with pytest.raises(ValidationError, match="duplicate"):
        changed(
            response,
            chunks=(response.chunks[0], response.chunks[0]),
            diagnostics=changed(response.diagnostics, returned_chunk_count=2),
        )
    with pytest.raises(ValidationError):
        changed(response.chunks[0], score=float("nan"))
    assert TEXT not in repr(response)


def test_result_limit_configuration_changes_and_empty_authorized_scope() -> None:
    request, facts = scenario()
    scope = prepare_retrieval_scope(changed(request, top_k=1), facts, now=NOW)
    response = result()
    extra = changed(response.chunks[0], chunk_id=UUID(int=99))
    oversized = changed(
        response, chunks=(response.chunks[0], extra), diagnostics=changed(response.diagnostics, returned_chunk_count=2)
    )
    with pytest.raises(ValueError, match="more chunks"):
        validate_retrieval_result(scope, oversized, facts, now=NOW)
    with pytest.raises(ValueError, match="configuration changed"):
        validate_retrieval_result(scope, response, changed(facts, config_version="retrieval-v2"), now=NOW)
    empty_scope = prepare_retrieval_scope(request, changed(facts, documents=(), chunks=()), now=NOW)
    empty = changed(response, chunks=(), diagnostics=changed(response.diagnostics, returned_chunk_count=0))
    assert validate_retrieval_result(empty_scope, empty, changed(facts, documents=(), chunks=()), now=NOW) == empty
    with pytest.raises(ValidationError, match="source rank"):
        ScoreComponents(rrf_score=0.5)
