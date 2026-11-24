"""Exercise version lifecycles, retry intent, publication and current document access."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from app.modules.documents.application.access import require_published_document
from app.modules.documents.domain.contracts import (
    Document,
    DocumentAccessPolicy,
    DocumentSourceType,
    DocumentStatus,
    DocumentVersion,
    DocumentVersionRef,
    DocumentVersionStatus,
    StoredDocumentVersion,
    StoredObjectRef,
)
from app.modules.iam.domain.contracts import ExternalIdentity, IdentityStatus, User, UserStatus
from app.modules.ingestion.application.lifecycle import (
    advance_document_version,
    advance_ingestion_job,
    retry_ingestion_job,
)
from app.modules.ingestion.domain.contracts import (
    IngestionEvent,
    IngestionEventType,
    IngestionFailure,
    IngestionJob,
    IngestionJobStatus,
    IngestionJobType,
    IngestionProgress,
    IngestionStage,
    ingestion_job_key,
    ingestion_stage_key,
)
from app.modules.knowledge_base.domain.contracts import EmbeddingBinding, KnowledgeBase, KnowledgeBaseStatus
from app.modules.policy.application.authorization import actor_reference
from app.modules.policy.domain.contracts import (
    AccessContext,
    AccessPurpose,
    AuthorizationSnapshot,
    KnowledgePermission,
    ResourceGrant,
    ResourcePrincipalType,
)
from app.modules.search.application.lifecycle import advance_index_build
from app.modules.search.application.publication import PublicationRefusedError, prepare_index_publication
from app.modules.search.domain.contracts import (
    IndexAlias,
    IndexManifest,
    IndexValidationReport,
    IndexVersionStatus,
    PublicationAction,
    PublicationRequest,
    PublicationSnapshot,
    PublishedDocumentSnapshot,
    StoredIndexVersion,
    ValidationVerdict,
    index_binding_hash,
)
from pydantic import BaseModel, ValidationError

NOW = datetime(2026, 11, 24, 8, tzinfo=UTC)
USER_ID, KB_ID, DOC_ID, VERSION_ID = (UUID(int=value) for value in (1, 10, 20, 21))
CURRENT_INDEX, TARGET_INDEX = UUID(int=30), UUID(int=31)
MODEL_ID = UUID(int=40)
HASH = "a" * 64


def changed[ModelT: BaseModel](model: ModelT, **updates: object) -> ModelT:
    return type(model).model_validate({**model.model_dump(), **updates})


def embedding(*, dimensions: int = 3, model_id: UUID = MODEL_ID) -> EmbeddingBinding:
    return EmbeddingBinding(embedding_model_id=model_id, config_version="model-v1", dimensions=dimensions)


def kb(*, binding: EmbeddingBinding | None = None, active: UUID | None = CURRENT_INDEX) -> KnowledgeBase:
    return KnowledgeBase(
        id=KB_ID,
        name="Synthetic KB",
        status=KnowledgeBaseStatus.ACTIVE,
        embedding=binding or embedding(),
        active_index_version_id=active,
        created_by=USER_ID,
        created_at=NOW - timedelta(hours=2),
        updated_at=NOW - timedelta(minutes=1),
    )


def document() -> Document:
    return Document(
        id=DOC_ID,
        kb_id=KB_ID,
        title="Synthetic Document",
        source_type=DocumentSourceType.UPLOAD,
        current_version=2,
        status=DocumentStatus.ACTIVE,
        acl_policy_id=None,
        created_by=USER_ID,
        created_at=NOW - timedelta(hours=2),
        updated_at=NOW - timedelta(minutes=1),
    )


def reference() -> DocumentVersionRef:
    return DocumentVersionRef(document_version_id=VERSION_ID, document_id=DOC_ID, kb_id=KB_ID, document_version=1)


def version(*, status: DocumentVersionStatus = DocumentVersionStatus.PUBLISHED) -> DocumentVersion:
    return DocumentVersion(
        **reference().model_dump(),
        status=status,
        mime_type="application/pdf",
        file_size=128,
        file_hash=HASH,
        pipeline_version="pipeline-v1",
        parser_name="synthetic-parser",
        parser_version="fixture-1",
        chunking_config_version="chunks-v1",
        created_at=NOW - timedelta(hours=2),
        updated_at=NOW - timedelta(minutes=1),
        published_at=NOW - timedelta(minutes=10) if status is DocumentVersionStatus.PUBLISHED else None,
    )


def index(
    *,
    index_id: UUID = CURRENT_INDEX,
    status: IndexVersionStatus = IndexVersionStatus.ACTIVE,
    binding: EmbeddingBinding | None = None,
) -> tuple[StoredIndexVersion, IndexManifest]:
    pinned = binding or embedding()
    manifest = IndexManifest(index_version_id=index_id, kb_id=KB_ID, documents=(reference(),))
    report = IndexValidationReport(
        id=UUID(int=index_id.int + 100),
        index_version_id=index_id,
        manifest_sha256=manifest.content_hash,
        binding_sha256=index_binding_hash(pinned, "chunks-v1", "pipeline-v1"),
        verdict=ValidationVerdict.PASSED,
        expected_document_count=1,
        actual_document_count=1,
        expected_chunk_count=2,
        actual_chunk_count=2,
        mapping_verified=True,
        acl_verified=True,
        retrieval_verified=True,
        quality_gate_verified=True,
        checked_at=NOW - timedelta(minutes=10),
    )
    record = StoredIndexVersion(
        id=index_id,
        kb_id=KB_ID,
        version=index_id.int,
        status=status,
        embedding=pinned,
        chunking_config_version="chunks-v1",
        pipeline_version="pipeline-v1",
        manifest_sha256=manifest.content_hash,
        validation_report_id=report.id,
        created_at=NOW - timedelta(hours=2),
        updated_at=NOW - timedelta(minutes=1),
        published_at=NOW - timedelta(minutes=10)
        if status in (IndexVersionStatus.ACTIVE, IndexVersionStatus.ROLLED_BACK)
        else None,
        physical_index_name=f"kb_synthetic_v{index_id.int}",
        alias_name="kb_synthetic_read",
        validation=report,
    )
    return record, manifest


def authority() -> tuple[AccessContext, AuthorizationSnapshot]:
    actor = actor_reference(USER_ID, b"synthetic-server-pseudonymization-key")
    principal = User(
        id=USER_ID, display_name="Synthetic User", status=UserStatus.ACTIVE, created_at=NOW, updated_at=NOW
    )
    identity = ExternalIdentity(
        id=UUID(int=50),
        user_id=USER_ID,
        provider_key="synthetic",
        issuer="https://login.example",
        subject="synthetic-subject",
        status=IdentityStatus.ACTIVE,
    )
    context = AccessContext(
        subject_id=USER_ID,
        identity_id=identity.id,
        actor_ref=actor,
        environment="test",
        purpose=AccessPurpose.ADMIN,
        policy_version="policy-v1",
        issued_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(minutes=10),
    )
    snapshot = AuthorizationSnapshot(
        user=principal,
        identity=identity,
        actor_ref=actor,
        environment="test",
        purpose=AccessPurpose.ADMIN,
        policy_version="policy-v1",
        role_ids=frozenset(),
        group_ids=frozenset(),
        permission_codes=frozenset({"kb.read", "kb.manage"}),
        resource_grants=(
            ResourceGrant(
                id=UUID(int=60),
                kb_id=KB_ID,
                principal_type=ResourcePrincipalType.USER,
                principal_id=USER_ID,
                permission=KnowledgePermission.MANAGE,
            ),
        ),
        subject_bindings=(),
        observed_at=NOW,
        expires_at=NOW + timedelta(minutes=5),
    )
    return context, snapshot


def publication() -> tuple[PublicationRequest, PublicationSnapshot]:
    current, _ = index()
    target, manifest = index(index_id=TARGET_INDEX, status=IndexVersionStatus.READY)
    request = PublicationRequest(
        kb_id=KB_ID,
        action=PublicationAction.PUBLISH,
        target_index_version_id=TARGET_INDEX,
        expected_active_index_version_id=CURRENT_INDEX,
        idempotency_key="synthetic-publication",
    )
    snapshot = PublicationSnapshot(
        kb=kb(),
        target=target,
        current=current,
        alias=IndexAlias(
            kb_id=KB_ID,
            alias_name=current.alias_name,
            active_index_version_id=current.id,
            physical_index_name=current.physical_index_name,
        ),
        manifest=manifest,
        documents=(document(),),
        document_versions=(version(),),
    )
    return request, snapshot


def readable() -> tuple[PublishedDocumentSnapshot, DocumentAccessPolicy]:
    current, manifest = index()
    packet = PublishedDocumentSnapshot(
        kb=kb(),
        document=document(),
        version=version(),
        index=current,
        alias=IndexAlias(
            kb_id=KB_ID,
            alias_name=current.alias_name,
            active_index_version_id=current.id,
            physical_index_name=current.physical_index_name,
        ),
        manifest=manifest,
    )
    policy = DocumentAccessPolicy(
        document_id=DOC_ID, kb_id=KB_ID, acl_policy_id=None, allowed_subject_ids=None, policy_version="policy-v1"
    )
    return packet, policy


def job() -> IngestionJob:
    return IngestionJob(
        **reference().model_dump(),
        id=UUID(int=70),
        job_type=IngestionJobType.INGEST,
        pipeline_version="pipeline-v1",
        terminal_stage=IngestionStage.VALIDATING,
        status=IngestionJobStatus.QUEUED,
        stage=IngestionStage.PARSING,
        idempotency_key=ingestion_job_key(
            reference(), "pipeline-v1", IngestionJobType.INGEST, IngestionStage.VALIDATING
        ),
        requester_subject_id=USER_ID,
        trace_id="1" * 32,
        retry_count=0,
        max_retries=1,
        progress=IngestionProgress(completed_units=0, total_units=None),
        failure=None,
        created_at=NOW,
        updated_at=NOW,
        started_at=None,
        finished_at=None,
    )


def test_private_source_references_and_parsed_states_are_version_bound() -> None:
    original = StoredObjectRef(bucket="synthetic-private", object_key="kb/doc/v1/original", sha256=HASH, size_bytes=128)
    parsed = StoredObjectRef(bucket="synthetic-private", object_key="kb/doc/v1/parsed", sha256="b" * 64, size_bytes=64)
    stored = StoredDocumentVersion(**version().model_dump(), original=original, parsed_artifact=parsed)
    with pytest.raises(ValidationError, match="source digest and size"):
        changed(stored, original=changed(original, size_bytes=129))
    with pytest.raises(ValidationError, match="persisted artifact"):
        changed(stored, parsed_artifact=None)
    with pytest.raises(ValidationError, match="not signed URLs"):
        changed(original, object_key="https://private.example/object?token=synthetic")
    assert original.object_key not in repr(stored)


@pytest.mark.parametrize(
    "update", [{"file_size": 0}, {"file_hash": "invalid"}, {"mime_type": "text/html"}, {"parser_version": None}]
)
def test_version_metadata_rejects_empty_invalid_or_incomplete_inputs(update: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        changed(version(), **update)


def test_document_version_transitions_do_not_reprocess_published_content() -> None:
    uploaded = version(status=DocumentVersionStatus.UPLOADED)
    parsing = advance_document_version(uploaded, DocumentVersionStatus.PARSING, now=NOW)
    parsed = advance_document_version(parsing, DocumentVersionStatus.PARSED, now=NOW)
    assert parsed.status is DocumentVersionStatus.PARSED and uploaded.status is DocumentVersionStatus.UPLOADED
    with pytest.raises(ValueError, match="Illegal"):
        advance_document_version(uploaded, DocumentVersionStatus.PUBLISHED, now=NOW)
    with pytest.raises(ValueError, match="Illegal"):
        advance_document_version(version(), DocumentVersionStatus.PARSING, now=NOW)
    deleted = advance_document_version(
        advance_document_version(version(), DocumentVersionStatus.DELETING, now=NOW),
        DocumentVersionStatus.DELETED,
        now=NOW,
    )
    assert deleted.published_at == version().published_at


def test_ingestion_keys_separate_stable_job_intent_and_per_stage_deduplication() -> None:
    original = job()
    assert original.idempotency_key == job().idempotency_key
    assert ingestion_stage_key(reference(), "pipeline-v1", IngestionStage.PARSING) != ingestion_stage_key(
        reference(), "pipeline-v1", IngestionStage.INDEXING
    )
    with pytest.raises(ValidationError, match="immutable"):
        changed(original, pipeline_version="pipeline-v2")
    with pytest.raises(ValidationError, match="immutable"):
        changed(original, document_version=2)


def test_retry_preserves_identity_budget_and_failure_stage() -> None:
    running = advance_ingestion_job(job(), IngestionJobStatus.RUNNING, now=NOW)
    failure = IngestionFailure(
        code="PARSER_TIMEOUT", message="Temporary parser failure", retryable=True, outcome_unknown=False
    )
    failed = advance_ingestion_job(running, IngestionJobStatus.FAILED, now=NOW, failure=failure)
    retried = retry_ingestion_job(failed, now=NOW)
    assert (retried.id, retried.idempotency_key, retried.stage, retried.requester_subject_id) == (
        failed.id,
        failed.idempotency_key,
        failed.stage,
        USER_ID,
    )
    assert retried.retry_count == 1 and retried.max_retries == 1 and retried.started_at == running.started_at
    assert retried.finished_at is None and retried.failure is None
    failed_again = advance_ingestion_job(
        advance_ingestion_job(retried, IngestionJobStatus.RUNNING, now=NOW),
        IngestionJobStatus.FAILED,
        now=NOW,
        failure=failure,
    )
    with pytest.raises(ValueError, match="exhausted"):
        retry_ingestion_job(failed_again, now=NOW)
    with pytest.raises(ValidationError, match="Unknown external outcomes"):
        changed(failure, outcome_unknown=True)


def test_job_success_requires_its_goal_and_running_stage_cannot_move_backwards() -> None:
    running = advance_ingestion_job(job(), IngestionJobStatus.RUNNING, now=NOW)
    with pytest.raises(ValidationError, match="declared goal"):
        advance_ingestion_job(running, IngestionJobStatus.SUCCEEDED, now=NOW)
    indexing = advance_ingestion_job(running, IngestionJobStatus.RUNNING, stage=IngestionStage.INDEXING, now=NOW)
    with pytest.raises(ValueError, match="backwards"):
        advance_ingestion_job(indexing, IngestionJobStatus.RUNNING, stage=IngestionStage.PARSING, now=NOW)
    succeeded = advance_ingestion_job(indexing, IngestionJobStatus.SUCCEEDED, stage=IngestionStage.VALIDATING, now=NOW)
    assert succeeded.status is IngestionJobStatus.SUCCEEDED
    assert version(status=DocumentVersionStatus.INDEXED).published_at is None


def test_publication_returns_only_a_validated_plan_without_mutating_active_state() -> None:
    request, packet = publication()
    context, authorization = authority()
    before = packet.model_dump_json()
    plan = prepare_index_publication(request, packet, context, authorization, now=NOW)
    assert plan.request.idempotency_key == request.idempotency_key
    assert (
        plan.remove_physical_index == packet.alias.physical_index_name
        and plan.add_physical_index == packet.target.physical_index_name
    )
    assert plan.embedding == packet.target.embedding and packet.model_dump_json() == before


@pytest.mark.parametrize(
    "state",
    [IndexVersionStatus.BUILDING, IndexVersionStatus.VALIDATING, IndexVersionStatus.FAILED, IndexVersionStatus.RETIRED],
)
def test_only_ready_indexes_can_publish(state: IndexVersionStatus) -> None:
    request, packet = publication()
    context, authorization = authority()
    with pytest.raises(PublicationRefusedError, match="ready target"):
        prepare_index_publication(
            request, changed(packet, target=changed(packet.target, status=state)), context, authorization, now=NOW
        )


def test_validation_is_bound_and_unknown_quality_cannot_become_ready() -> None:
    target, _ = index(index_id=TARGET_INDEX, status=IndexVersionStatus.READY)
    assert target.validation is not None
    for update in ({"quality_gate_verified": False}, {"actual_chunk_count": 3}, {"acl_verified": False}):
        with pytest.raises(ValidationError, match="all checks"):
            changed(target.validation, **update)
    with pytest.raises(ValidationError, match="different version"):
        changed(target, validation=changed(target.validation, binding_sha256="b" * 64))
    validating = changed(target, status=IndexVersionStatus.VALIDATING)
    assert advance_index_build(validating, IndexVersionStatus.READY, now=NOW).status is IndexVersionStatus.READY
    with pytest.raises(ValueError, match="publication cannot be inferred"):
        advance_index_build(validating, IndexVersionStatus.ACTIVE, now=NOW)
    with pytest.raises(ValidationError, match="passed evidence"):
        changed(target, validation=None)


def test_publication_checks_cas_alias_configuration_and_current_permission() -> None:
    request, packet = publication()
    context, authorization = authority()
    with pytest.raises(PublicationRefusedError, match="CAS"):
        prepare_index_publication(
            changed(request, expected_active_index_version_id=None), packet, context, authorization, now=NOW
        )
    with pytest.raises(PublicationRefusedError, match="do not agree"):
        prepare_index_publication(
            request,
            changed(packet, alias=changed(packet.alias, physical_index_name="another_index")),
            context,
            authorization,
            now=NOW,
        )
    with pytest.raises(PublicationRefusedError, match="embedding configuration"):
        prepare_index_publication(
            request, changed(packet, kb=kb(binding=embedding(dimensions=4))), context, authorization, now=NOW
        )
    with pytest.raises(PermissionError):
        prepare_index_publication(
            request, packet, context, changed(authorization, permission_codes=frozenset({"kb.read"})), now=NOW
        )


@pytest.mark.parametrize("state", [DocumentStatus.DELETING, DocumentStatus.DELETED])
def test_deleted_documents_cannot_be_published_or_read(state: DocumentStatus) -> None:
    request, packet = publication()
    context, authorization = authority()
    dead = changed(
        document(), status=state, deleted_at=NOW if state is DocumentStatus.DELETED else None, updated_at=NOW
    )
    with pytest.raises(PublicationRefusedError):
        prepare_index_publication(request, changed(packet, documents=(dead,)), context, authorization, now=NOW)
    read, policy = readable()
    with pytest.raises(PermissionError):
        require_published_document(changed(read, document=dead), policy, context, authorization, now=NOW)


def test_rollback_restores_a_retained_older_vector_space_in_its_plan() -> None:
    request, packet = publication()
    context, authorization = authority()
    older, manifest = index(
        index_id=TARGET_INDEX, status=IndexVersionStatus.ROLLED_BACK, binding=embedding(dimensions=2)
    )
    plan = prepare_index_publication(
        changed(request, action=PublicationAction.ROLLBACK),
        changed(packet, target=older, manifest=manifest),
        context,
        authorization,
        now=NOW,
    )
    assert plan.embedding.dimensions == 2 and packet.kb.embedding.dimensions == 3
    with pytest.raises(PublicationRefusedError, match="previously published"):
        prepare_index_publication(
            changed(request, action=PublicationAction.ROLLBACK), packet, context, authorization, now=NOW
        )


def test_new_kb_first_publication_has_no_old_alias_removal() -> None:
    request, packet = publication()
    context, authorization = authority()
    empty = changed(
        packet,
        kb=kb(active=None),
        current=None,
        alias=changed(packet.alias, active_index_version_id=None, physical_index_name=None),
    )
    plan = prepare_index_publication(
        changed(request, expected_active_index_version_id=None), empty, context, authorization, now=NOW
    )
    assert plan.remove_physical_index is None


def test_older_published_version_survives_a_newer_failed_attempt() -> None:
    packet, policy = readable()
    context, authorization = authority()
    newest_failed = changed(
        version(status=DocumentVersionStatus.FAILED), document_version_id=UUID(int=22), document_version=2
    )
    assert newest_failed.status is DocumentVersionStatus.FAILED
    assert packet.document.current_version == 2
    assert require_published_document(packet, policy, context, authorization, now=NOW).document_version == 1


def test_document_policy_can_only_restrict_current_kb_access() -> None:
    packet, inherited = readable()
    context, authorization = authority()
    restricted_document = changed(packet.document, acl_policy_id=UUID(int=80))
    restricted = changed(packet, document=restricted_document)
    deny_all = changed(inherited, acl_policy_id=UUID(int=80), allowed_subject_ids=frozenset[UUID]())
    with pytest.raises(PermissionError, match="restriction"):
        require_published_document(restricted, deny_all, context, authorization, now=NOW)
    allowed = changed(deny_all, allowed_subject_ids=frozenset({USER_ID}))
    assert require_published_document(restricted, allowed, context, authorization, now=NOW) == reference()
    with pytest.raises(PermissionError, match="KB permission"):
        require_published_document(restricted, allowed, context, changed(authorization, resource_grants=()), now=NOW)
    with pytest.raises(PermissionError, match="missing or inconsistent"):
        require_published_document(restricted, inherited, context, authorization, now=NOW)


def test_read_refuses_cross_kb_versions_stale_policy_and_alias_disagreement() -> None:
    packet, policy = readable()
    context, authorization = authority()
    for update in (
        {"kb_id": UUID(int=99)},
        {"document_id": UUID(int=99)},
        {"document_version": 3},
        {"pipeline_version": "other-pipeline"},
    ):
        with pytest.raises(PermissionError):
            require_published_document(
                changed(packet, version=changed(packet.version, **update)), policy, context, authorization, now=NOW
            )
    with pytest.raises(PermissionError):
        require_published_document(
            packet, changed(policy, policy_version="old-policy"), context, authorization, now=NOW
        )
    with pytest.raises(PermissionError):
        require_published_document(
            changed(packet, alias=changed(packet.alias, physical_index_name="other_index")),
            policy,
            context,
            authorization,
            now=NOW,
        )
    with pytest.raises(PermissionError):
        require_published_document(
            changed(packet, index=changed(packet.index, status=IndexVersionStatus.ROLLED_BACK)),
            policy,
            context,
            authorization,
            now=NOW,
        )


def test_manifest_unique_versions_and_model_dimension_contract() -> None:
    with pytest.raises(ValidationError, match="multiple versions"):
        IndexManifest(index_version_id=CURRENT_INDEX, kb_id=KB_ID, documents=(reference(), reference()))
    with pytest.raises(ValidationError, match="another KB"):
        IndexManifest(
            index_version_id=CURRENT_INDEX, kb_id=KB_ID, documents=(changed(reference(), kb_id=UUID(int=99)),)
        )
    with pytest.raises(ValidationError):
        embedding(dimensions=0)
    with pytest.raises(ValidationError):
        changed(document(), schema_version="2.0")


def test_full_version_retry_discards_derived_evidence_and_requires_a_new_parse() -> None:
    original = StoredObjectRef(bucket="synthetic-private", object_key="original", sha256=HASH, size_bytes=128)
    parsed = StoredObjectRef(bucket="synthetic-private", object_key="parsed", sha256="b" * 64, size_bytes=64)
    failed = StoredDocumentVersion(
        **version(status=DocumentVersionStatus.FAILED).model_dump(), original=original, parsed_artifact=parsed
    )
    restarted = advance_document_version(failed, DocumentVersionStatus.PARSING, now=NOW)
    assert restarted.original == original and restarted.pipeline_version == failed.pipeline_version
    assert restarted.parsed_artifact is None and restarted.parser_name is None
    assert restarted.parser_version is None and restarted.chunking_config_version is None
    assert failed.parsed_artifact == parsed
    with pytest.raises(ValidationError, match="parser binding"):
        advance_document_version(restarted, DocumentVersionStatus.PARSED, now=NOW)


def test_version_processing_reaches_publication_only_with_stage_evidence() -> None:
    processed = version(status=DocumentVersionStatus.UPLOADED)
    for stage in (
        DocumentVersionStatus.PARSING,
        DocumentVersionStatus.PARSED,
        DocumentVersionStatus.CHUNKING,
        DocumentVersionStatus.EMBEDDING,
        DocumentVersionStatus.INDEXING,
        DocumentVersionStatus.INDEXED,
    ):
        processed = advance_document_version(processed, stage, now=NOW)
    assert processed.published_at is None
    published = advance_document_version(processed, DocumentVersionStatus.PUBLISHED, now=NOW)
    assert published.published_at == NOW and processed.status is DocumentVersionStatus.INDEXED


@pytest.mark.parametrize("clock", [NOW.replace(tzinfo=None), NOW - timedelta(hours=3)])
def test_lifecycle_changes_reject_naive_or_regressing_clocks(clock: datetime) -> None:
    with pytest.raises(ValueError, match="clock"):
        advance_document_version(
            version(status=DocumentVersionStatus.UPLOADED), DocumentVersionStatus.PARSING, now=clock
        )
    with pytest.raises(ValueError, match="clock"):
        advance_ingestion_job(job(), IngestionJobStatus.RUNNING, now=clock)
    validating, _ = index(index_id=TARGET_INDEX, status=IndexVersionStatus.VALIDATING)
    with pytest.raises(ValueError, match="clock"):
        advance_index_build(validating, IndexVersionStatus.READY, now=clock)


@pytest.mark.parametrize("terminal", [IngestionJobStatus.CANCELLED, IngestionJobStatus.TIMED_OUT])
def test_cancellation_and_timeout_do_not_authorize_replay(terminal: IngestionJobStatus) -> None:
    running = advance_ingestion_job(job(), IngestionJobStatus.RUNNING, now=NOW)
    failure = IngestionFailure(code="TIMEOUT", message="Execution timed out", retryable=True, outcome_unknown=False)
    stopped = advance_ingestion_job(
        running, terminal, now=NOW, failure=failure if terminal is IngestionJobStatus.TIMED_OUT else None
    )
    assert stopped.finished_at == NOW
    with pytest.raises(ValueError, match="Only explicitly"):
        retry_ingestion_job(stopped, now=NOW)
    with pytest.raises(ValueError, match="Illegal"):
        advance_ingestion_job(stopped, IngestionJobStatus.RUNNING, now=NOW)
    with pytest.raises(ValidationError, match="first start time"):
        changed(stopped, status=IngestionJobStatus.TIMED_OUT, failure=failure, started_at=None)


def test_unknown_external_outcome_and_deletion_job_keep_safe_boundaries() -> None:
    failure = IngestionFailure(
        code="OUTCOME_UNKNOWN", message="Operation needs reconciliation", retryable=False, outcome_unknown=True
    )
    failed = advance_ingestion_job(
        advance_ingestion_job(job(), IngestionJobStatus.RUNNING, now=NOW),
        IngestionJobStatus.FAILED,
        failure=failure,
        now=NOW,
    )
    with pytest.raises(ValueError, match="Only explicitly"):
        retry_ingestion_job(failed, now=NOW)
    with pytest.raises(ValidationError, match="first start time"):
        changed(failed, started_at=None)
    with pytest.raises(ValidationError, match="Deletion stages"):
        changed(job(), stage=IngestionStage.DELETING)
    deletion = changed(
        job(),
        job_type=IngestionJobType.DELETE,
        stage=IngestionStage.DELETING,
        terminal_stage=IngestionStage.DELETING,
        idempotency_key=ingestion_job_key(reference(), "pipeline-v1", IngestionJobType.DELETE, IngestionStage.DELETING),
    )
    completed = advance_ingestion_job(
        advance_ingestion_job(deletion, IngestionJobStatus.RUNNING, now=NOW),
        IngestionJobStatus.SUCCEEDED,
        now=NOW,
    )
    assert completed.status is IngestionJobStatus.SUCCEEDED
    with pytest.raises(ValidationError, match="first start time"):
        changed(completed, started_at=None)


@pytest.mark.parametrize("kind", list(IngestionEventType))
def test_event_payloads_agree_with_progress_failure_and_retry_semantics(kind: IngestionEventType) -> None:
    error_kind = kind in {IngestionEventType.FAILED, IngestionEventType.TIMED_OUT, IngestionEventType.RETRY_SCHEDULED}
    failure = IngestionFailure(code="TEMPORARY", message="Temporary failure", retryable=True, outcome_unknown=False)
    event = IngestionEvent(
        id=UUID(int=90),
        job_id=job().id,
        sequence_no=1,
        stage=IngestionStage.PARSING,
        event_type=kind,
        attempt=1,
        progress=IngestionProgress(completed_units=1, total_units=2),
        failure=failure if error_kind else None,
        occurred_at=NOW,
    )
    if error_kind:
        with pytest.raises(ValidationError, match="error classification"):
            changed(event, failure=None)
    elif kind is not IngestionEventType.CANCELLED:
        with pytest.raises(ValidationError, match="current failure"):
            changed(event, failure=failure)
    if kind is IngestionEventType.RETRY_SCHEDULED:
        with pytest.raises(ValidationError, match="explicitly retryable"):
            changed(event, failure=changed(failure, retryable=False, outcome_unknown=True))
    if kind is IngestionEventType.PROGRESS:
        with pytest.raises(ValidationError, match="measured progress"):
            changed(event, progress=None)


@pytest.mark.parametrize(
    "state",
    [IndexVersionStatus.BUILDING, IndexVersionStatus.VALIDATING, IndexVersionStatus.READY, IndexVersionStatus.FAILED],
)
def test_published_index_history_cannot_return_to_build_states(state: IndexVersionStatus) -> None:
    current, _ = index()
    with pytest.raises(ValidationError, match="build attempt"):
        changed(current, status=state)
    assert changed(current, status=IndexVersionStatus.RETIRED).published_at == current.published_at


def test_publication_refuses_physical_index_reuse_and_alias_name_collision() -> None:
    request, packet = publication()
    context, authorization = authority()
    with pytest.raises(ValidationError, match="names must be distinct"):
        changed(packet.target, physical_index_name=packet.target.alias_name)
    assert packet.current is not None
    reused = changed(packet.target, physical_index_name=packet.current.physical_index_name)
    with pytest.raises(PublicationRefusedError, match="distinct physical indexes"):
        prepare_index_publication(request, changed(packet, target=reused), context, authorization, now=NOW)


@pytest.mark.parametrize("missing", ["documents", "document_versions", "current"])
def test_publication_requires_complete_current_member_and_index_facts(missing: str) -> None:
    request, packet = publication()
    context, authorization = authority()
    with pytest.raises(PublicationRefusedError):
        prepare_index_publication(
            request, changed(packet, **{missing: None if missing == "current" else ()}), context, authorization, now=NOW
        )


def test_rollback_cannot_restore_a_member_without_confirmed_publication_history() -> None:
    request, packet = publication()
    context, authorization = authority()
    older, manifest = index(index_id=TARGET_INDEX, status=IndexVersionStatus.ROLLED_BACK)
    with pytest.raises(PublicationRefusedError, match="not indexed"):
        prepare_index_publication(
            changed(request, action=PublicationAction.ROLLBACK),
            changed(
                packet,
                target=older,
                manifest=manifest,
                document_versions=(version(status=DocumentVersionStatus.INDEXED),),
            ),
            context,
            authorization,
            now=NOW,
        )


def test_manifest_and_validation_counts_cannot_disagree_during_publish_or_read() -> None:
    request, packet = publication()
    read, policy = readable()
    context, authorization = authority()
    for record in (packet.target, read.index):
        assert record.validation is not None
        mismatched = changed(
            record,
            validation=changed(record.validation, expected_document_count=2, actual_document_count=2),
        )
        if record.id == packet.target.id:
            with pytest.raises(PublicationRefusedError, match="manifest count"):
                prepare_index_publication(request, changed(packet, target=mismatched), context, authorization, now=NOW)
        else:
            with pytest.raises(PermissionError, match="manifest facts"):
                require_published_document(changed(read, index=mismatched), policy, context, authorization, now=NOW)


def test_future_document_facts_cannot_authorize_publication_or_online_read() -> None:
    request, packet = publication()
    read, policy = readable()
    context, authorization = authority()
    future = changed(document(), updated_at=NOW + timedelta(minutes=1))
    with pytest.raises(PublicationRefusedError, match="future"):
        prepare_index_publication(request, changed(packet, documents=(future,)), context, authorization, now=NOW)
    with pytest.raises(PermissionError, match="future"):
        require_published_document(changed(read, document=future), policy, context, authorization, now=NOW)


@pytest.mark.parametrize(
    "state", [KnowledgeBaseStatus.DISABLED, KnowledgeBaseStatus.DELETING, KnowledgeBaseStatus.DELETED]
)
def test_inactive_kb_blocks_both_publication_and_online_read(state: KnowledgeBaseStatus) -> None:
    request, packet = publication()
    read, policy = readable()
    context, authorization = authority()
    inactive = changed(
        kb(), status=state, updated_at=NOW, deleted_at=NOW if state is KnowledgeBaseStatus.DELETED else None
    )
    with pytest.raises(PublicationRefusedError):
        prepare_index_publication(request, changed(packet, kb=inactive), context, authorization, now=NOW)
    with pytest.raises(PermissionError):
        require_published_document(changed(read, kb=inactive), policy, context, authorization, now=NOW)


def test_missing_identity_context_and_removed_manifest_member_deny_read() -> None:
    packet, policy = readable()
    context, authorization = authority()
    with pytest.raises(PermissionError, match="KB permission"):
        require_published_document(packet, policy, None, authorization, now=NOW)
    manifest = changed(packet.manifest, documents=())
    assert packet.index.validation is not None
    report = changed(
        packet.index.validation,
        manifest_sha256=manifest.content_hash,
        expected_document_count=0,
        actual_document_count=0,
    )
    current = changed(packet.index, manifest_sha256=manifest.content_hash, validation=report)
    with pytest.raises(PermissionError, match="not a member"):
        require_published_document(
            changed(packet, manifest=manifest, index=current), policy, context, authorization, now=NOW
        )
