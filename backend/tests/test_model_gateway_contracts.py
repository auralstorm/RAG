"""Verify exact model/configuration, current invocation authority and safe provider output mapping."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from app.modules.iam.domain.contracts import ExternalIdentity, IdentityStatus, User, UserStatus
from app.modules.knowledge_base.domain.contracts import EmbeddingBinding
from app.modules.model_gateway.application.invocation import (
    ModelCallRefusedError,
    prepare_model_call,
    prepare_model_retry,
    validate_model_response,
    validate_model_result,
    validate_model_stream,
)
from app.modules.model_gateway.domain.contracts import (
    ChatMessage,
    ChatOutput,
    ChatRequest,
    EmbeddingOutput,
    EmbeddingRequest,
    EmbeddingVector,
    ModelCallFacts,
    ModelCallRequest,
    ModelCapability,
    ModelCost,
    ModelErrorCode,
    ModelFailure,
    ModelOperation,
    ModelRequest,
    ModelResponse,
    ModelStreamEvent,
    ModelUsage,
    RegistryStatus,
    RerankOutput,
    RerankRequest,
    RerankScore,
    SecretReference,
    StoredModelConfig,
    StoredProvider,
    TokenMeasurement,
    UsageSource,
    model_request_hash,
)
from app.modules.policy.application.authorization import actor_reference
from app.modules.policy.domain.contracts import AccessContext, AccessPurpose, AuthorizationSnapshot
from pydantic import BaseModel, HttpUrl, ValidationError

NOW = datetime(2026, 11, 24, 10, tzinfo=UTC)
USER, PROVIDER, MODEL, REQUEST, IDENTITY = (UUID(int=i) for i in range(1, 6))


def changed[ModelT: BaseModel](record: ModelT, **updates: object) -> ModelT:
    return type(record).model_validate({**record.model_dump(), **updates})


def scenario(operation: ModelOperation = ModelOperation.CHAT) -> tuple[ModelRequest, AccessContext, ModelCallFacts]:
    actor = actor_reference(USER, b"synthetic-pseudonym-key-at-least-32-bytes")
    identity = ExternalIdentity(
        id=IDENTITY,
        user_id=USER,
        provider_key="synthetic",
        issuer="https://identity.example.test",
        subject="synthetic",
        status=IdentityStatus.ACTIVE,
    )
    context = AccessContext(
        subject_id=USER,
        identity_id=IDENTITY,
        actor_ref=actor,
        environment="test",
        purpose=AccessPurpose.CHAT,
        policy_version="policy-v1",
        issued_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(minutes=5),
    )
    authority = AuthorizationSnapshot(
        user=User(id=USER, display_name="Synthetic", status=UserStatus.ACTIVE, created_at=NOW, updated_at=NOW),
        identity=identity,
        actor_ref=actor,
        environment="test",
        purpose=AccessPurpose.CHAT,
        policy_version="policy-v1",
        role_ids=frozenset[UUID](),
        group_ids=frozenset[UUID](),
        permission_codes=frozenset[str](),
        resource_grants=(),
        subject_bindings=(),
        observed_at=NOW,
        expires_at=NOW + timedelta(minutes=5),
    )
    provider = StoredProvider(
        id=PROVIDER,
        name="Synthetic",
        provider_type="synthetic",
        config_version="provider-v1",
        status=RegistryStatus.ACTIVE,
        has_credential=True,
        created_at=NOW,
        updated_at=NOW,
        base_url=HttpUrl("https://model.example.test/v1"),
        credential_ref=SecretReference(secret_id=UUID(int=6), version=1, environment="test"),
        timeout_seconds=30,
    )
    common = ModelCallRequest(
        request_id=REQUEST,
        trace_id="a" * 32,
        model_id=MODEL,
        config_version="model-v1",
        deadline_at=NOW + timedelta(minutes=1),
    ).model_dump()
    if operation is ModelOperation.CHAT:
        request: ModelRequest = ChatRequest(
            **common, messages=(ChatMessage(role="user", content="Synthetic prompt"),), max_output_tokens=10
        )
        capabilities = frozenset({ModelCapability.CHAT, ModelCapability.STREAMING, ModelCapability.JSON_MODE})
    elif operation is ModelOperation.EMBEDDING:
        request = EmbeddingRequest(
            **common,
            texts=("one", "two"),
            input_type="document",
            binding=EmbeddingBinding(embedding_model_id=MODEL, config_version="model-v1", dimensions=3),
        )
        capabilities = frozenset({ModelCapability.EMBEDDING})
    else:
        request = RerankRequest(**common, query="question", documents=("one", "two"), top_n=1)
        capabilities = frozenset({ModelCapability.RERANKER})
    model = StoredModelConfig(
        id=MODEL,
        provider_id=PROVIDER,
        config_version="model-v1",
        display_name="Synthetic",
        status=RegistryStatus.ACTIVE,
        capabilities=capabilities,
        tokenizer_version="tokenizer-v1",
        max_input_tokens=60,
        context_window=100 if operation is ModelOperation.CHAT else None,
        max_output_tokens=30 if operation is ModelOperation.CHAT else None,
        embedding_dimension=3 if operation is ModelOperation.EMBEDDING else None,
        max_batch_size=2 if operation is not ModelOperation.CHAT else None,
        vendor_model_key="synthetic/private-vendor-key",
    )
    facts = ModelCallFacts(
        authorization=authority,
        provider=provider,
        model=model,
        allowed_model_ids=frozenset({MODEL}),
        allowed_operations=frozenset({operation}),
        measurement=TokenMeasurement(
            request_sha256=model_request_hash(request),
            tokenizer_version="tokenizer-v1",
            input_tokens=(3, 3) if operation is ModelOperation.EMBEDDING else (5,),
        ),
        capabilities_verified=True,
        endpoint_approved=True,
        admission_allowed=True,
        max_attempts=2,
    )
    return request, context, facts


def response(request: ModelRequest) -> ModelResponse:
    if isinstance(request, ChatRequest):
        output = ChatOutput(content="answer", finish_reason="stop")
    elif isinstance(request, EmbeddingRequest):
        output = EmbeddingOutput(
            vectors=(EmbeddingVector(index=1, values=(1, 0, 0)), EmbeddingVector(index=0, values=(0, 1, 0)))
        )
    else:
        output = RerankOutput(scores=(RerankScore(index=1, score=0.9),))
    return ModelResponse(
        request_id=request.request_id,
        trace_id=request.trace_id,
        model_id=request.model_id,
        config_version=request.config_version,
        output=output,
        usage=ModelUsage(input_tokens=5, output_tokens=2, total_tokens=7, source=UsageSource.REPORTED),
        elapsed_ms=10,
    )


@pytest.mark.parametrize("operation", list(ModelOperation))
def test_known_operation_is_prepared_and_response_is_bound_without_external_io(operation: ModelOperation) -> None:
    request, context, facts = scenario(operation)
    before = facts.model_dump_json()
    prepared = prepare_model_call(request, context, facts, now=NOW)
    assert prepared.timeout_seconds == 30 and prepared.request_sha256 == model_request_hash(request)
    assert prepared.attempt == 1 and prepared.max_attempts == 2 and facts.model_dump_json() == before
    assert validate_model_response(request, response(request)).request_id == REQUEST
    assert "Synthetic prompt" not in repr(prepared) and facts.model.vendor_model_key not in repr(prepared)


@pytest.mark.parametrize("field", ["api_key", "base_url", "vendor_model_key", "credential_ref", "access_context"])
def test_business_requests_reject_credentials_and_provider_overrides(field: str) -> None:
    request, _, _ = scenario()
    with pytest.raises(ValidationError):
        changed(request, **{field: "synthetic forbidden value"})


@pytest.mark.parametrize(
    "url",
    [
        "https://user:password@example.test/v1",
        "https://example.test/v1?key=synthetic",
        "https://example.test/v1#secret",
    ],
)
def test_provider_endpoints_cannot_embed_secret_material(url: str) -> None:
    _, _, facts = scenario()
    with pytest.raises(ValidationError, match="credentials"):
        changed(facts.provider, base_url=url)
    assert facts.provider.credential_ref is not None
    with pytest.raises(ValidationError):
        changed(facts.provider.credential_ref, secret_id="synthetic plaintext key")


@pytest.mark.parametrize(
    "error,code",
    [
        ("missing_context", ModelErrorCode.ACCESS_DENIED),
        ("disabled_user", ModelErrorCode.ACCESS_DENIED),
        ("allowlist", ModelErrorCode.ACCESS_DENIED),
        ("operation", ModelErrorCode.ACCESS_DENIED),
        ("provider", ModelErrorCode.PROVIDER_DISABLED),
        ("model", ModelErrorCode.MODEL_DISABLED),
        ("config", ModelErrorCode.CONFIG_MISMATCH),
        ("secret_env", ModelErrorCode.ACCESS_DENIED),
        ("endpoint", ModelErrorCode.ACCESS_DENIED),
        ("capabilities", ModelErrorCode.CAPABILITY_UNSUPPORTED),
        ("deadline", ModelErrorCode.DEADLINE_EXCEEDED),
        ("admission", ModelErrorCode.RATE_LIMITED),
        ("measurement", ModelErrorCode.INVALID_REQUEST),
        ("context_window", ModelErrorCode.INVALID_REQUEST),
    ],
)
def test_model_calls_require_current_permissions_registry_and_measured_limits(error: str, code: ModelErrorCode) -> None:
    request, context, facts = scenario()
    access: AccessContext | None = context
    if error == "missing_context":
        access = None
    elif error == "disabled_user":
        facts = changed(
            facts,
            authorization=changed(
                facts.authorization, user=changed(facts.authorization.user, status=UserStatus.DISABLED)
            ),
        )
    elif error == "allowlist":
        facts = changed(facts, allowed_model_ids=frozenset[UUID]())
    elif error == "operation":
        facts = changed(facts, allowed_operations=frozenset[ModelOperation]())
    elif error == "provider":
        facts = changed(facts, provider=changed(facts.provider, status=RegistryStatus.DISABLED))
    elif error == "model":
        facts = changed(facts, model=changed(facts.model, status=RegistryStatus.DISABLED))
    elif error == "config":
        request = changed(request, config_version="other")
    elif error == "secret_env":
        assert facts.provider.credential_ref is not None
        facts = changed(
            facts,
            provider=changed(
                facts.provider, credential_ref=changed(facts.provider.credential_ref, environment="production")
            ),
        )
    elif error == "endpoint":
        facts = changed(facts, endpoint_approved=False)
    elif error == "capabilities":
        facts = changed(facts, capabilities_verified=False)
    elif error == "deadline":
        request = changed(request, deadline_at=NOW)
    elif error == "admission":
        facts = changed(facts, admission_allowed=False)
    elif error == "measurement":
        facts = changed(facts, measurement=changed(facts.measurement, request_sha256="b" * 64))
    else:
        facts = changed(
            facts,
            model=changed(facts.model, context_window=60),
            measurement=changed(facts.measurement, input_tokens=(55,)),
        )
    with pytest.raises(ModelCallRefusedError) as caught:
        prepare_model_call(request, access, facts, now=NOW)
    assert caught.value.code is code


def test_streaming_json_and_embedding_capabilities_are_exact_not_inferred() -> None:
    request, context, facts = scenario()
    assert isinstance(request, ChatRequest)
    request = changed(request, stream=True)
    facts = changed(
        facts,
        measurement=changed(facts.measurement, request_sha256=model_request_hash(request)),
        model=changed(facts.model, capabilities=frozenset({ModelCapability.CHAT})),
    )
    with pytest.raises(ModelCallRefusedError, match="CAPABILITY"):
        prepare_model_call(request, context, facts, now=NOW)
    request = changed(request, stream=False, response_format="json_object")
    facts = changed(facts, measurement=changed(facts.measurement, request_sha256=model_request_hash(request)))
    with pytest.raises(ModelCallRefusedError, match="CAPABILITY"):
        prepare_model_call(request, context, facts, now=NOW)
    embedding_request, context, embedding_facts = scenario(ModelOperation.EMBEDDING)
    assert isinstance(embedding_request, EmbeddingRequest)
    with pytest.raises(ValidationError, match="exact model"):
        changed(embedding_request, model_id=UUID(int=99))
    with pytest.raises(ModelCallRefusedError, match="CONFIG_MISMATCH"):
        prepare_model_call(
            embedding_request,
            context,
            changed(embedding_facts, model=changed(embedding_facts.model, embedding_dimension=4)),
            now=NOW,
        )
    with pytest.raises(ValidationError, match="capability"):
        changed(embedding_facts.model, capabilities=frozenset({ModelCapability.STREAMING}))


def test_usage_keeps_unknown_values_and_separates_reported_tokens_from_estimated_cost() -> None:
    unknown = ModelUsage(input_tokens=None, output_tokens=None, total_tokens=None, source=UsageSource.UNAVAILABLE)
    assert unknown.total_tokens is None
    partial = changed(
        unknown,
        input_tokens=5,
        source=UsageSource.REPORTED,
        cost=ModelCost(amount=Decimal("0.001"), currency="CNY", source="ESTIMATED"),
    )
    assert partial.total_tokens is None and partial.cost is not None and partial.cost.source == "ESTIMATED"
    with pytest.raises(ValidationError):
        changed(unknown, total_tokens=0)
    with pytest.raises(ValidationError, match="equal input"):
        changed(partial, output_tokens=2, total_tokens=10)
    with pytest.raises(ValidationError):
        ModelCost(amount=Decimal("NaN"), currency="CNY", source="ESTIMATED")


@pytest.mark.parametrize(
    "error", ["request_id", "config_version", "vector_count", "vector_dimension", "rerank_index", "json"]
)
def test_model_output_rejects_wrong_identity_incomplete_vectors_and_invalid_rank_or_json(error: str) -> None:
    operation = (
        ModelOperation.EMBEDDING
        if error.startswith("vector")
        else ModelOperation.RERANK
        if error.startswith("rerank")
        else ModelOperation.CHAT
    )
    request, _, _ = scenario(operation)
    answer = response(request)
    if error == "request_id":
        answer = changed(answer, request_id=UUID(int=99))
    elif error == "config_version":
        answer = changed(answer, config_version="other")
    elif error == "vector_count":
        answer = changed(answer, output=EmbeddingOutput(vectors=(EmbeddingVector(index=0, values=(1, 0, 0)),)))
    elif error == "vector_dimension":
        answer = changed(
            answer,
            output=EmbeddingOutput(
                vectors=(EmbeddingVector(index=0, values=(1, 0)), EmbeddingVector(index=1, values=(0, 1)))
            ),
        )
    elif error == "rerank_index":
        answer = changed(answer, output=RerankOutput(scores=(RerankScore(index=9, score=1),)))
    else:
        assert isinstance(request, ChatRequest)
        request = changed(request, response_format="json_object")
        answer = changed(answer, output=ChatOutput(content="[]", finish_reason="stop"))
    with pytest.raises(ModelCallRefusedError, match="INVALID_RESPONSE"):
        validate_model_response(request, answer)


def test_vectors_cannot_be_zero_or_nonfinite() -> None:
    for values in ((0, 0, 0), (float("nan"), 1, 0)):
        with pytest.raises(ValidationError):
            EmbeddingVector(index=0, values=values)


def test_retries_preserve_original_intent_budget_and_recheck_current_authority() -> None:
    request, context, facts = scenario()
    original = prepare_model_call(request, context, facts, now=NOW)
    failure = ModelFailure(code=ModelErrorCode.UNAVAILABLE, retryable=True, outcome_unknown=False)
    retried = prepare_model_retry(
        original, failure, context, facts, now=NOW + timedelta(seconds=5), stream_started=False
    )
    assert retried.request == original.request and retried.attempt == 2 and retried.max_attempts == 2
    for current in (facts, changed(facts, max_attempts=20)):
        with pytest.raises(ModelCallRefusedError):
            prepare_model_retry(
                retried, failure, context, current, now=NOW + timedelta(seconds=6), stream_started=False
            )
    with pytest.raises(ModelCallRefusedError, match="ACCESS_DENIED"):
        prepare_model_retry(
            original,
            failure,
            context,
            changed(facts, allowed_model_ids=frozenset[UUID]()),
            now=NOW,
            stream_started=False,
        )
    with pytest.raises(ModelCallRefusedError, match="CONFIG_MISMATCH"):
        prepare_model_retry(
            original,
            failure,
            context,
            changed(facts, provider=changed(facts.provider, config_version="provider-v2")),
            now=NOW,
            stream_started=False,
        )
    with pytest.raises(ModelCallRefusedError):
        prepare_model_retry(original, failure, context, facts, now=NOW, stream_started=True)
    with pytest.raises(ValidationError):
        changed(failure, outcome_unknown=True)
    unknown = ModelFailure(code=ModelErrorCode.OUTCOME_UNKNOWN, retryable=False, outcome_unknown=True)
    with pytest.raises(ModelCallRefusedError):
        prepare_model_retry(original, unknown, context, facts, now=NOW, stream_started=False)


def test_stream_event_order_terminal_payload_and_accumulated_text_are_checked() -> None:
    request, _, _ = scenario()
    assert isinstance(request, ChatRequest)
    streaming = changed(request, stream=True)
    identity = {name: getattr(request, name) for name in ("request_id", "trace_id", "model_id", "config_version")}
    delta = ModelStreamEvent(**identity, sequence_no=1, event_type="delta", delta="answer")
    terminal = ModelStreamEvent(**identity, sequence_no=2, event_type="completed", response=response(streaming))
    validate_model_stream(streaming, (delta, terminal), require_terminal=True)
    validate_model_stream(streaming, (delta,), require_terminal=False)
    for events in (
        (delta,),
        (delta, changed(terminal, sequence_no=3)),
        (delta, terminal, changed(delta, sequence_no=3)),
    ):
        with pytest.raises(ModelCallRefusedError):
            validate_model_stream(streaming, events, require_terminal=True)
    with pytest.raises(ModelCallRefusedError):
        validate_model_stream(streaming, (changed(delta, delta="wrong"), terminal), require_terminal=True)
    with pytest.raises(ValidationError):
        changed(delta, failure=ModelFailure(code=ModelErrorCode.UNAVAILABLE, retryable=True, outcome_unknown=False))
    failed = ModelStreamEvent(
        **identity,
        sequence_no=2,
        event_type="failed",
        failure=ModelFailure(code=ModelErrorCode.UNAVAILABLE, retryable=False, outcome_unknown=False),
    )
    validate_model_stream(streaming, (delta, failed), require_terminal=True)


def test_delivery_rechecks_revocation_without_acquiring_another_admission_slot() -> None:
    request, context, facts = scenario()
    call = prepare_model_call(request, context, facts, now=NOW)
    assert (
        validate_model_result(
            call, response(request), context, changed(facts, admission_allowed=False), now=NOW
        ).request_id
        == REQUEST
    )
    for revoked in (
        changed(facts, allowed_model_ids=frozenset[UUID]()),
        changed(facts, model=changed(facts.model, status=RegistryStatus.DISABLED)),
        changed(
            facts,
            authorization=changed(
                facts.authorization, user=changed(facts.authorization.user, status=UserStatus.DISABLED)
            ),
        ),
    ):
        with pytest.raises(ModelCallRefusedError):
            validate_model_result(call, response(request), context, revoked, now=NOW)
    with pytest.raises(ValidationError):
        ChatOutput(content="", finish_reason="stop")
    assert ChatOutput(content="", finish_reason="content_filter").content == ""


@pytest.mark.parametrize("content", ['{"n":NaN}', '{"n":Infinity}', "not json"])
def test_json_mode_rejects_invalid_or_nonfinite_json(content: str) -> None:
    request, _, _ = scenario()
    assert isinstance(request, ChatRequest)
    request = changed(request, response_format="json_object")
    with pytest.raises(ModelCallRefusedError, match="INVALID_RESPONSE"):
        validate_model_response(
            request, changed(response(request), output=ChatOutput(content=content, finish_reason="stop"))
        )
    valid = changed(response(request), output=ChatOutput(content='{"ok":true}', finish_reason="stop"))
    assert validate_model_response(request, valid).request_id == REQUEST
