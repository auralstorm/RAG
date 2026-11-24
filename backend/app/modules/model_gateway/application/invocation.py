"""Prepare authorized exact-version model calls without resolving credentials or executing IO."""

import json
from datetime import datetime

from app.modules.model_gateway.domain.contracts import (
    ChatOutput,
    ChatRequest,
    EmbeddingOutput,
    EmbeddingRequest,
    ModelCallFacts,
    ModelCapability,
    ModelErrorCode,
    ModelFailure,
    ModelRequest,
    ModelResponse,
    ModelStreamEvent,
    PreparedModelCall,
    RegistryStatus,
    RerankOutput,
    model_request_hash,
)
from app.modules.policy.application.authorization import validate_access_context
from app.modules.policy.domain.contracts import AccessContext


class ModelCallRefusedError(ValueError):
    def __init__(self, code: ModelErrorCode) -> None:
        self.code = code
        super().__init__(code.value)


def _reject_json_constant(value: str) -> None:
    raise ValueError("JSON output cannot contain nonfinite numeric constants")


def _require_model_access(
    request: ModelRequest, context: AccessContext | None, facts: ModelCallFacts, *, now: datetime
) -> AccessContext:
    if validate_access_context(context, facts.authorization, now=now) is not None or context is None:
        raise ModelCallRefusedError(ModelErrorCode.ACCESS_DENIED)
    provider, model = facts.provider, facts.model
    if request.model_id not in facts.allowed_model_ids or request.operation not in facts.allowed_operations:
        raise ModelCallRefusedError(ModelErrorCode.ACCESS_DENIED)
    if provider.status is not RegistryStatus.ACTIVE:
        raise ModelCallRefusedError(ModelErrorCode.PROVIDER_DISABLED)
    if model.status is not RegistryStatus.ACTIVE:
        raise ModelCallRefusedError(ModelErrorCode.MODEL_DISABLED)
    if (
        model.id != request.model_id
        or model.provider_id != provider.id
        or model.config_version != request.config_version
        or now < provider.updated_at
    ):
        raise ModelCallRefusedError(ModelErrorCode.CONFIG_MISMATCH)
    if (
        provider.credential_ref is None
        or provider.credential_ref.environment != context.environment
        or not facts.endpoint_approved
    ):
        raise ModelCallRefusedError(ModelErrorCode.ACCESS_DENIED)
    capability = {
        "chat": ModelCapability.CHAT,
        "embedding": ModelCapability.EMBEDDING,
        "rerank": ModelCapability.RERANKER,
    }[request.operation]
    if not facts.capabilities_verified or capability not in model.capabilities:
        raise ModelCallRefusedError(ModelErrorCode.CAPABILITY_UNSUPPORTED)
    if now >= request.deadline_at:
        raise ModelCallRefusedError(ModelErrorCode.DEADLINE_EXCEEDED)
    return context


def prepare_model_call(
    request: ModelRequest, context: AccessContext | None, facts: ModelCallFacts, *, now: datetime
) -> PreparedModelCall:
    """Require independently current allowlists, registry/credential facts, token evidence and admission."""
    context = _require_model_access(request, context, facts, now=now)
    provider, model = facts.provider, facts.model
    if not facts.admission_allowed:
        raise ModelCallRefusedError(ModelErrorCode.RATE_LIMITED)
    measurement = facts.measurement
    digest = model_request_hash(request)
    if measurement.request_sha256 != digest or measurement.tokenizer_version != model.tokenizer_version:
        raise ModelCallRefusedError(ModelErrorCode.INVALID_REQUEST)
    count = len(request.texts) if isinstance(request, EmbeddingRequest) else 1
    if len(measurement.input_tokens) != count or any(
        tokens > model.max_input_tokens for tokens in measurement.input_tokens
    ):
        raise ModelCallRefusedError(ModelErrorCode.INVALID_REQUEST)
    if isinstance(request, ChatRequest):
        if (
            request.stream
            and ModelCapability.STREAMING not in model.capabilities
            or request.response_format == "json_object"
            and ModelCapability.JSON_MODE not in model.capabilities
        ):
            raise ModelCallRefusedError(ModelErrorCode.CAPABILITY_UNSUPPORTED)
        if (
            model.max_output_tokens is None
            or model.context_window is None
            or request.max_output_tokens > model.max_output_tokens
            or measurement.input_tokens[0] + request.max_output_tokens > model.context_window
        ):
            raise ModelCallRefusedError(ModelErrorCode.INVALID_REQUEST)
    elif isinstance(request, EmbeddingRequest):
        if (
            request.binding.dimensions != model.embedding_dimension
            or model.max_batch_size is None
            or len(request.texts) > model.max_batch_size
        ):
            raise ModelCallRefusedError(ModelErrorCode.CONFIG_MISMATCH)
    elif model.max_batch_size is None or len(request.documents) > model.max_batch_size:
        raise ModelCallRefusedError(ModelErrorCode.INVALID_REQUEST)
    return PreparedModelCall(
        request=request,
        context=context,
        provider=provider,
        model=model,
        request_sha256=digest,
        attempt=1,
        max_attempts=facts.max_attempts,
        timeout_seconds=min(
            provider.timeout_seconds,
            (min(request.deadline_at, context.expires_at, facts.authorization.expires_at) - now).total_seconds(),
        ),
        prepared_at=now,
    )


def prepare_model_retry(
    previous: PreparedModelCall,
    failure: ModelFailure,
    context: AccessContext | None,
    current_facts: ModelCallFacts,
    *,
    now: datetime,
    stream_started: bool,
) -> PreparedModelCall:
    """Reauthorize a bounded new attempt with the original request/configuration; unknown or exposed output cannot replay."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ModelCallRefusedError(ModelErrorCode.INVALID_REQUEST)
    if (
        not failure.retryable
        or failure.outcome_unknown
        or stream_started
        or previous.attempt >= min(previous.max_attempts, current_facts.max_attempts)
    ):
        raise ModelCallRefusedError(ModelErrorCode.INVALID_REQUEST)
    if now < previous.prepared_at:
        raise ModelCallRefusedError(ModelErrorCode.INVALID_REQUEST)
    if (
        context is None
        or context.subject_id != previous.context.subject_id
        or context.purpose != previous.context.purpose
        or context.environment != previous.context.environment
    ):
        raise ModelCallRefusedError(ModelErrorCode.ACCESS_DENIED)
    prepared = prepare_model_call(previous.request, context, current_facts, now=now)
    if (
        prepared.request_sha256 != previous.request_sha256
        or prepared.provider.config_version != previous.provider.config_version
        or prepared.model.vendor_model_key != previous.model.vendor_model_key
    ):
        raise ModelCallRefusedError(ModelErrorCode.CONFIG_MISMATCH)
    return PreparedModelCall.model_validate(
        {
            **prepared.model_dump(),
            "attempt": previous.attempt + 1,
            "max_attempts": min(previous.max_attempts, current_facts.max_attempts),
        }
    )


def validate_model_response(request: ModelRequest, response: ModelResponse) -> ModelResponse:
    """Require request identity/configuration and complete typed output; missing usage is kept explicitly unknown."""
    if (
        any(
            getattr(request, name) != getattr(response, name)
            for name in ("request_id", "trace_id", "model_id", "config_version")
        )
        or request.operation != response.output.operation
    ):
        raise ModelCallRefusedError(ModelErrorCode.INVALID_RESPONSE)
    output = response.output
    if isinstance(request, ChatRequest):
        if (
            not isinstance(output, ChatOutput)
            or response.usage.output_tokens is not None
            and response.usage.output_tokens > request.max_output_tokens
        ):
            raise ModelCallRefusedError(ModelErrorCode.INVALID_RESPONSE)
        if request.response_format == "json_object" and output.finish_reason == "stop":
            try:
                parsed_json: object = json.loads(output.content, parse_constant=_reject_json_constant)
            except ValueError as error:
                raise ModelCallRefusedError(ModelErrorCode.INVALID_RESPONSE) from error
            if not isinstance(parsed_json, dict):
                raise ModelCallRefusedError(ModelErrorCode.INVALID_RESPONSE)
    elif isinstance(request, EmbeddingRequest):
        if (
            not isinstance(output, EmbeddingOutput)
            or sorted(vector.index for vector in output.vectors) != list(range(len(request.texts)))
            or any(len(vector.values) != request.binding.dimensions for vector in output.vectors)
        ):
            raise ModelCallRefusedError(ModelErrorCode.INVALID_RESPONSE)
    else:
        if (
            not isinstance(output, RerankOutput)
            or len(output.scores) != request.top_n
            or len({item.index for item in output.scores}) != len(output.scores)
            or any(item.index >= len(request.documents) for item in output.scores)
            or list(output.scores) != sorted(output.scores, key=lambda item: (-item.score, item.index))
        ):
            raise ModelCallRefusedError(ModelErrorCode.INVALID_RESPONSE)
    return response


def validate_model_result(
    call: PreparedModelCall,
    response: ModelResponse,
    context: AccessContext | None,
    current_facts: ModelCallFacts,
    *,
    now: datetime,
) -> ModelResponse:
    """Recheck current identity/model permission before delivery; this does not acquire another rate-limit slot."""
    current = _require_model_access(call.request, context, current_facts, now=now)
    if now < call.prepared_at:
        raise ModelCallRefusedError(ModelErrorCode.INVALID_RESPONSE)
    if (current.subject_id, current.purpose, current.environment) != (
        call.context.subject_id,
        call.context.purpose,
        call.context.environment,
    ):
        raise ModelCallRefusedError(ModelErrorCode.ACCESS_DENIED)
    if (
        current_facts.provider.config_version != call.provider.config_version
        or current_facts.model.vendor_model_key != call.model.vendor_model_key
    ):
        raise ModelCallRefusedError(ModelErrorCode.CONFIG_MISMATCH)
    return validate_model_response(call.request, response)


def validate_model_stream(
    request: ChatRequest, events: tuple[ModelStreamEvent, ...], *, require_terminal: bool
) -> None:
    """Validate one attempt's ordered prefix or completed stream; no durable replay/resume is inferred."""
    if not request.stream:
        raise ModelCallRefusedError(ModelErrorCode.INVALID_REQUEST)
    text: list[str] = []
    terminal = False
    for sequence, event in enumerate(events, 1):
        if (
            terminal
            or event.sequence_no != sequence
            or any(
                getattr(event, name) != getattr(request, name)
                for name in ("request_id", "trace_id", "model_id", "config_version")
            )
        ):
            raise ModelCallRefusedError(ModelErrorCode.INVALID_RESPONSE)
        if event.delta is not None:
            text.append(event.delta)
        else:
            terminal = True
            if event.response is not None:
                response = validate_model_response(request, event.response)
                if not isinstance(response.output, ChatOutput) or response.output.content != "".join(text):
                    raise ModelCallRefusedError(ModelErrorCode.INVALID_RESPONSE)
    if require_terminal and not terminal:
        raise ModelCallRefusedError(ModelErrorCode.INVALID_RESPONSE)
