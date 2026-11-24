"""Vendor keys and secrets stay in private registry references, outside business requests."""

import hashlib
import json
from collections.abc import AsyncIterator
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal, Protocol, Self
from uuid import UUID

from pydantic import Field, HttpUrl, model_validator

from app.core.contracts import UtcTimestamp, VersionedContract
from app.modules.knowledge_base.domain.contracts import ConfigurationVersion, ContentHash, EmbeddingBinding
from app.modules.policy.domain.contracts import AccessContext, AuthorizationSnapshot, Environment


class RegistryStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class ModelCapability(StrEnum):
    CHAT = "chat"
    STREAMING = "streaming"
    EMBEDDING = "embedding"
    RERANKER = "reranker"
    TOOL_CALL = "tool_call"
    JSON_MODE = "json_mode"


class SecretReference(VersionedContract):
    """Opaque versioned reference; validation neither resolves nor grants secret access."""

    secret_id: UUID
    version: int = Field(ge=1, strict=True)
    environment: Environment


class Provider(VersionedContract):
    id: UUID
    name: str = Field(min_length=1, max_length=128, pattern=r"\S")
    provider_type: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    config_version: ConfigurationVersion
    status: RegistryStatus
    has_credential: bool = Field(strict=True)
    created_at: UtcTimestamp
    updated_at: UtcTimestamp

    @model_validator(mode="after")
    def require_times(self) -> Self:
        if self.updated_at < self.created_at:
            raise ValueError("Provider update precedes creation")
        return self


class StoredProvider(Provider):
    base_url: HttpUrl = Field(repr=False)
    credential_ref: SecretReference | None = Field(repr=False)
    proxy_ref: UUID | None = Field(default=None, repr=False)
    timeout_seconds: int = Field(gt=0, strict=True)

    @model_validator(mode="after")
    def require_safe_references(self) -> Self:
        if (
            self.base_url.username is not None
            or self.base_url.password is not None
            or self.base_url.query is not None
            or self.base_url.fragment is not None
        ):
            raise ValueError("Provider endpoint cannot contain credentials, query parameters or fragments")
        if self.has_credential != (self.credential_ref is not None):
            raise ValueError("Provider credential indicator and reference must agree")
        return self


class ModelConfig(VersionedContract):
    """Stable model ID and immutable config version; vendor routing names remain private."""

    id: UUID
    provider_id: UUID
    config_version: ConfigurationVersion
    display_name: str = Field(min_length=1, max_length=128, pattern=r"\S")
    status: RegistryStatus
    capabilities: frozenset[ModelCapability] = Field(min_length=1)
    tokenizer_version: ConfigurationVersion
    max_input_tokens: int = Field(gt=0, strict=True)
    context_window: int | None = Field(default=None, gt=0, strict=True)
    max_output_tokens: int | None = Field(default=None, gt=0, strict=True)
    embedding_dimension: int | None = Field(default=None, gt=0, strict=True)
    max_batch_size: int | None = Field(default=None, gt=0, strict=True)
    rpm_limit: int | None = Field(default=None, gt=0, strict=True)
    tpm_limit: int | None = Field(default=None, gt=0, strict=True)
    max_concurrency: int | None = Field(default=None, gt=0, strict=True)
    is_default: bool = False
    weight: Decimal = Field(default=Decimal("1"), gt=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def require_capability_bindings(self) -> Self:
        chat = ModelCapability.CHAT in self.capabilities
        if (self.context_window is not None) != chat or (self.max_output_tokens is not None) != chat:
            raise ValueError("Chat models require context and output limits; other models cannot claim them")
        if not chat and self.capabilities & {
            ModelCapability.STREAMING,
            ModelCapability.TOOL_CALL,
            ModelCapability.JSON_MODE,
        }:
            raise ValueError("Streaming/tool/JSON capabilities require Chat capability")
        if (self.embedding_dimension is not None) != (ModelCapability.EMBEDDING in self.capabilities):
            raise ValueError("Embedding capability and explicit vector dimension must agree")
        if (self.max_batch_size is not None) != bool(
            self.capabilities & {ModelCapability.EMBEDDING, ModelCapability.RERANKER}
        ):
            raise ValueError("Embedding/reranker models require a batch limit")
        if self.context_window is not None and (
            self.max_input_tokens > self.context_window
            or self.max_output_tokens is not None
            and self.max_output_tokens > self.context_window
        ):
            raise ValueError("Configured token limits exceed the Chat context window")
        return self


class StoredModelConfig(ModelConfig):
    vendor_model_key: str = Field(min_length=1, max_length=256, pattern=r"\S", repr=False)


class ModelOperation(StrEnum):
    CHAT = "chat"
    EMBEDDING = "embedding"
    RERANK = "rerank"


class ModelCallRequest(VersionedContract):
    request_id: UUID
    trace_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    model_id: UUID
    config_version: ConfigurationVersion
    deadline_at: UtcTimestamp

    @model_validator(mode="after")
    def require_trace(self) -> Self:
        if self.trace_id == "0" * 32:
            raise ValueError("Model calls require a nonzero server trace ID")
        return self


class ChatMessage(VersionedContract):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1, pattern=r"\S", repr=False)


class ChatRequest(ModelCallRequest):
    operation: Literal["chat"] = "chat"
    messages: tuple[ChatMessage, ...] = Field(min_length=1, repr=False)
    max_output_tokens: int = Field(gt=0, strict=True)
    temperature: float = Field(default=0, ge=0, le=2, allow_inf_nan=False)
    stream: bool = Field(default=False, strict=True)
    response_format: Literal["text", "json_object"] = "text"


class EmbeddingRequest(ModelCallRequest):
    operation: Literal["embedding"] = "embedding"
    texts: tuple[str, ...] = Field(min_length=1, repr=False)
    binding: EmbeddingBinding
    input_type: Literal["query", "document"]

    @model_validator(mode="after")
    def require_inputs_and_binding(self) -> Self:
        if any(not text.strip() for text in self.texts):
            raise ValueError("Embedding input texts cannot be blank")
        if self.binding.embedding_model_id != self.model_id or self.binding.config_version != self.config_version:
            raise ValueError("Embedding request must retain its exact model/configuration binding")
        return self


class RerankRequest(ModelCallRequest):
    operation: Literal["rerank"] = "rerank"
    query: str = Field(min_length=1, pattern=r"\S", repr=False)
    documents: tuple[str, ...] = Field(min_length=1, repr=False)
    top_n: int = Field(gt=0, strict=True)

    @model_validator(mode="after")
    def require_candidates(self) -> Self:
        if self.top_n > len(self.documents) or any(not text.strip() for text in self.documents):
            raise ValueError("Rerank selection requires nonblank candidates and a bounded top_n")
        return self


type ModelRequest = Annotated[ChatRequest | EmbeddingRequest | RerankRequest, Field(discriminator="operation")]


class UsageSource(StrEnum):
    REPORTED = "REPORTED"
    ESTIMATED = "ESTIMATED"
    UNAVAILABLE = "UNAVAILABLE"


class ModelCost(VersionedContract):
    amount: Decimal = Field(ge=0, allow_inf_nan=False)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    source: Literal["REPORTED", "ESTIMATED"]


class ModelUsage(VersionedContract):
    input_tokens: int | None = Field(ge=0, strict=True)
    output_tokens: int | None = Field(ge=0, strict=True)
    total_tokens: int | None = Field(ge=0, strict=True)
    source: UsageSource
    cost: ModelCost | None = None

    @model_validator(mode="after")
    def require_usage_consistency(self) -> Self:
        counts = (self.input_tokens, self.output_tokens, self.total_tokens)
        if (self.source is UsageSource.UNAVAILABLE) != all(count is None for count in counts):
            raise ValueError("Unavailable token usage must remain unknown; known usage requires a source")
        if all(count is not None for count in counts):
            if self.total_tokens != (self.input_tokens or 0) + (self.output_tokens or 0):
                raise ValueError("Total token usage must equal input plus output")
        elif self.total_tokens is not None and any(
            count is not None and count > self.total_tokens for count in counts[:2]
        ):
            raise ValueError("Known token components cannot exceed the reported total")
        return self


class ChatOutput(VersionedContract):
    operation: Literal["chat"] = "chat"
    content: str = Field(repr=False)
    finish_reason: Literal["stop", "length", "content_filter"]

    @model_validator(mode="after")
    def require_answer_or_filter(self) -> Self:
        if self.finish_reason != "content_filter" and not self.content.strip():
            raise ValueError("Chat output requires content or an explicit content-filter outcome")
        return self


type VectorValue = Annotated[float, Field(allow_inf_nan=False)]


class EmbeddingVector(VersionedContract):
    index: int = Field(ge=0, strict=True)
    values: tuple[VectorValue, ...] = Field(min_length=1, repr=False)

    @model_validator(mode="after")
    def require_usable_vector(self) -> Self:
        if not any(self.values):
            raise ValueError("Embedding vectors cannot be zero")
        return self


class EmbeddingOutput(VersionedContract):
    operation: Literal["embedding"] = "embedding"
    vectors: tuple[EmbeddingVector, ...] = Field(min_length=1, repr=False)


class RerankScore(VersionedContract):
    index: int = Field(ge=0, strict=True)
    score: float = Field(allow_inf_nan=False)


class RerankOutput(VersionedContract):
    operation: Literal["rerank"] = "rerank"
    scores: tuple[RerankScore, ...] = Field(min_length=1)


type ModelOutput = Annotated[ChatOutput | EmbeddingOutput | RerankOutput, Field(discriminator="operation")]


class ModelResponse(VersionedContract):
    request_id: UUID
    trace_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    model_id: UUID
    config_version: ConfigurationVersion
    output: ModelOutput
    usage: ModelUsage
    elapsed_ms: float = Field(ge=0, allow_inf_nan=False)


class ModelErrorCode(StrEnum):
    ACCESS_DENIED = "ACCESS_DENIED"
    PROVIDER_DISABLED = "PROVIDER_DISABLED"
    MODEL_DISABLED = "MODEL_DISABLED"
    CONFIG_MISMATCH = "CONFIG_MISMATCH"
    CAPABILITY_UNSUPPORTED = "CAPABILITY_UNSUPPORTED"
    INVALID_REQUEST = "INVALID_REQUEST"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    DEADLINE_EXCEEDED = "DEADLINE_EXCEEDED"
    RATE_LIMITED = "RATE_LIMITED"
    UNAVAILABLE = "UNAVAILABLE"
    OUTCOME_UNKNOWN = "OUTCOME_UNKNOWN"


class ModelFailure(VersionedContract):
    """Stable safe classification; raw provider messages and HTTP bodies are absent."""

    code: ModelErrorCode
    retryable: bool = Field(strict=True)
    outcome_unknown: bool = Field(strict=True)
    usage: ModelUsage | None = None

    @model_validator(mode="after")
    def require_safe_retry(self) -> Self:
        if self.retryable and (
            self.outcome_unknown or self.code not in {ModelErrorCode.UNAVAILABLE, ModelErrorCode.RATE_LIMITED}
        ):
            raise ValueError("Only known transient failures may authorize a retry")
        if self.code is ModelErrorCode.OUTCOME_UNKNOWN and not self.outcome_unknown:
            raise ValueError("Unknown-outcome failure must retain its uncertain effect")
        return self


def model_request_hash(request: ModelRequest) -> str:
    payload = request.model_dump(mode="json")
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class TokenMeasurement(VersionedContract):
    """Trusted tokenizer result bound to exactly one request, not client-declared token counts."""

    request_sha256: ContentHash
    tokenizer_version: ConfigurationVersion
    input_tokens: tuple[Annotated[int, Field(gt=0, strict=True)], ...] = Field(min_length=1)


class ModelCallFacts(VersionedContract):
    authorization: AuthorizationSnapshot = Field(repr=False)
    provider: StoredProvider = Field(repr=False)
    model: StoredModelConfig = Field(repr=False)
    allowed_model_ids: frozenset[UUID]
    allowed_operations: frozenset[ModelOperation]
    measurement: TokenMeasurement
    capabilities_verified: bool = Field(strict=True)
    endpoint_approved: bool = Field(strict=True)
    admission_allowed: bool = Field(strict=True)
    max_attempts: int = Field(ge=1, strict=True)


class PreparedModelCall(VersionedContract):
    request: ModelRequest = Field(repr=False)
    context: AccessContext = Field(repr=False)
    provider: StoredProvider = Field(repr=False)
    model: StoredModelConfig = Field(repr=False)
    request_sha256: ContentHash
    attempt: int = Field(ge=1, strict=True)
    max_attempts: int = Field(ge=1, strict=True)
    timeout_seconds: float = Field(gt=0, allow_inf_nan=False)
    prepared_at: UtcTimestamp


class ModelStreamEvent(VersionedContract):
    request_id: UUID
    trace_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    model_id: UUID
    config_version: ConfigurationVersion
    sequence_no: int = Field(ge=1, strict=True)
    event_type: Literal["delta", "completed", "failed"]
    delta: str | None = Field(default=None, min_length=1, repr=False)
    response: ModelResponse | None = Field(default=None, repr=False)
    failure: ModelFailure | None = None

    @model_validator(mode="after")
    def require_one_payload(self) -> Self:
        payloads = (self.delta is not None, self.response is not None, self.failure is not None)
        expected = {"delta": (True, False, False), "completed": (False, True, False), "failed": (False, False, True)}
        if payloads != expected[self.event_type]:
            raise ValueError("Stream event type must match exactly one payload")
        return self


class ModelGateway(Protocol):
    """Business port; implementations own current authorization, bounded SDK execution and safe mapping."""

    async def invoke(self, request: ModelRequest) -> ModelResponse: ...

    def stream(self, request: ChatRequest) -> AsyncIterator[ModelStreamEvent]: ...
