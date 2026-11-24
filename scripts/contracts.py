"""Generate and check HTTP contract artifacts from the real app and common DTOs."""

import argparse
import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.api.schemas.common import ApiErrorEnvelope, PageResponse, PaginationQuery
from app.core.config import Settings
from app.main import create_app
from app.modules.audit.domain.contracts import AuditEvent, StoredAuditEvent
from app.modules.chunking.domain.contracts import Chunk, ChunkMetadata, ChunkSource, ChunkSourceSpan
from app.modules.conversations.domain.contracts import (
    Citation,
    Conversation,
    Message,
    StoredConversation,
    StoredMessage,
)
from app.modules.documents.domain.contracts import (
    Document,
    DocumentAccessPolicy,
    DocumentVersion,
    DocumentVersionRef,
    StoredDocumentVersion,
    StoredObjectRef,
)
from app.modules.iam.domain.contracts import (
    ExternalIdentity,
    IdentityKey,
    LegacyPrincipalKey,
    Permission,
    Role,
    RolePermission,
    SubjectBinding,
    SystemRoleCode,
    User,
    UserRole,
)
from app.modules.ingestion.domain.contracts import IngestionEvent, IngestionFailure, IngestionJob, IngestionProgress
from app.modules.knowledge_base.domain.contracts import EmbeddingBinding, KnowledgeBase
from app.modules.model_gateway.domain.contracts import (
    ModelCallFacts,
    ModelConfig,
    ModelCost,
    ModelFailure,
    ModelRequest,
    ModelResponse,
    ModelStreamEvent,
    ModelUsage,
    PreparedModelCall,
    Provider,
    SecretReference,
    StoredModelConfig,
    StoredProvider,
    TokenMeasurement,
)
from app.modules.parsing.domain.contracts import (
    ParsedBlock,
    ParsedDocument,
    ParsedPage,
    ParsedTable,
    ParserInput,
    ParsingWarning,
)
from app.modules.policy.domain.contracts import (
    AccessContext,
    AuthorizationRequest,
    AuthorizationSnapshot,
    PolicyDecision,
    ResourceGrant,
)
from app.modules.rag.domain.contracts import (
    AuthorizedRetrievalScope,
    RetrievalDiagnostics,
    RetrievalDocumentFacts,
    RetrievalFacts,
    RetrievalFilters,
    RetrievalIndexBinding,
    RetrievalRequest,
    RetrievalResult,
    RetrievalSelection,
    RetrievedChunk,
    ScoreComponents,
)
from app.modules.search.domain.contracts import (
    IndexAlias,
    IndexManifest,
    IndexPublication,
    IndexValidationReport,
    IndexVersion,
    PublicationPlan,
    PublicationRequest,
    PublicationSnapshot,
    PublishedDocumentSnapshot,
    StoredIndexVersion,
)
from app.modules.traces.domain.contracts import Trace, TraceIdentityLink, TraceSpan
from pydantic import JsonValue, RootModel, TypeAdapter

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class SchemaSource:
    """One authoritative schema registration, including visibility and frontend consumer."""

    name: str
    path: str
    frontend_group: Literal["common", "iam", "knowledge", "retrieval", "models", "chat", "observability"] | None
    generate: Callable[[], object]


SCHEMAS = (
    SchemaSource("ApiErrorEnvelope", "api-error.json", None, ApiErrorEnvelope.model_json_schema),
    SchemaSource("PaginationQuery", "pagination-query.json", "common", PaginationQuery.model_json_schema),
    SchemaSource("PageResponse", "page-response.json", "common", PageResponse[JsonValue].model_json_schema),
    SchemaSource("User", "iam/user.json", "iam", User.model_json_schema),
    SchemaSource("Role", "iam/role.json", "iam", Role.model_json_schema),
    SchemaSource("Permission", "iam/permission.json", "iam", Permission.model_json_schema),
    SchemaSource("UserRole", "iam/user-role.json", "iam", UserRole.model_json_schema),
    SchemaSource("RolePermission", "iam/role-permission.json", "iam", RolePermission.model_json_schema),
    SchemaSource("SystemRoleCode", "iam/system-role-code.json", "iam", TypeAdapter(SystemRoleCode).json_schema),
    SchemaSource("ResourceGrant", "iam/resource-grant.json", "iam", ResourceGrant.model_json_schema),
    SchemaSource("IdentityKey", "internal/identity-key.json", None, IdentityKey.model_json_schema),
    SchemaSource("ExternalIdentity", "internal/external-identity.json", None, ExternalIdentity.model_json_schema),
    SchemaSource(
        "LegacyPrincipalKey", "internal/legacy-principal-key.json", None, LegacyPrincipalKey.model_json_schema
    ),
    SchemaSource("SubjectBinding", "internal/subject-binding.json", None, SubjectBinding.model_json_schema),
    SchemaSource("AccessContext", "internal/access-context.json", None, AccessContext.model_json_schema),
    SchemaSource(
        "AuthorizationRequest", "internal/authorization-request.json", None, AuthorizationRequest.model_json_schema
    ),
    SchemaSource(
        "AuthorizationSnapshot", "internal/authorization-snapshot.json", None, AuthorizationSnapshot.model_json_schema
    ),
    SchemaSource("PolicyDecision", "internal/policy-decision.json", None, PolicyDecision.model_json_schema),
    SchemaSource("KnowledgeBase", "knowledge/knowledge-base.json", "knowledge", KnowledgeBase.model_json_schema),
    SchemaSource(
        "EmbeddingBinding", "knowledge/embedding-binding.json", "knowledge", EmbeddingBinding.model_json_schema
    ),
    SchemaSource("Document", "knowledge/document.json", "knowledge", Document.model_json_schema),
    SchemaSource("DocumentVersion", "knowledge/document-version.json", "knowledge", DocumentVersion.model_json_schema),
    SchemaSource(
        "DocumentVersionRef", "knowledge/document-version-ref.json", "knowledge", DocumentVersionRef.model_json_schema
    ),
    SchemaSource("IngestionJob", "knowledge/ingestion-job.json", "knowledge", IngestionJob.model_json_schema),
    SchemaSource("IngestionEvent", "knowledge/ingestion-event.json", "knowledge", IngestionEvent.model_json_schema),
    SchemaSource(
        "IngestionFailure", "knowledge/ingestion-failure.json", "knowledge", IngestionFailure.model_json_schema
    ),
    SchemaSource(
        "IngestionProgress", "knowledge/ingestion-progress.json", "knowledge", IngestionProgress.model_json_schema
    ),
    SchemaSource("IndexVersion", "knowledge/index-version.json", "knowledge", IndexVersion.model_json_schema),
    SchemaSource(
        "IndexPublication", "knowledge/index-publication.json", "knowledge", IndexPublication.model_json_schema
    ),
    SchemaSource("StoredObjectRef", "internal/stored-object-ref.json", None, StoredObjectRef.model_json_schema),
    SchemaSource(
        "StoredDocumentVersion", "internal/stored-document-version.json", None, StoredDocumentVersion.model_json_schema
    ),
    SchemaSource(
        "DocumentAccessPolicy", "internal/document-access-policy.json", None, DocumentAccessPolicy.model_json_schema
    ),
    SchemaSource("IndexManifest", "internal/index-manifest.json", None, IndexManifest.model_json_schema),
    SchemaSource(
        "IndexValidationReport", "internal/index-validation-report.json", None, IndexValidationReport.model_json_schema
    ),
    SchemaSource(
        "StoredIndexVersion", "internal/stored-index-version.json", None, StoredIndexVersion.model_json_schema
    ),
    SchemaSource("IndexAlias", "internal/index-alias.json", None, IndexAlias.model_json_schema),
    SchemaSource("PublicationRequest", "internal/publication-request.json", None, PublicationRequest.model_json_schema),
    SchemaSource(
        "PublicationSnapshot", "internal/publication-snapshot.json", None, PublicationSnapshot.model_json_schema
    ),
    SchemaSource("PublicationPlan", "internal/publication-plan.json", None, PublicationPlan.model_json_schema),
    SchemaSource(
        "PublishedDocumentSnapshot",
        "internal/published-document-snapshot.json",
        None,
        PublishedDocumentSnapshot.model_json_schema,
    ),
    SchemaSource("ParsedDocument", "internal/parsed-document.json", None, ParsedDocument.model_json_schema),
    SchemaSource("ParsedPage", "internal/parsed-page.json", None, ParsedPage.model_json_schema),
    SchemaSource("ParsedBlock", "internal/parsed-block.json", None, ParsedBlock.model_json_schema),
    SchemaSource("ParsedTable", "internal/parsed-table.json", None, ParsedTable.model_json_schema),
    SchemaSource("ParsingWarning", "internal/parsing-warning.json", None, ParsingWarning.model_json_schema),
    SchemaSource("ParserInput", "internal/parser-input.json", None, ParserInput.model_json_schema),
    SchemaSource("Chunk", "internal/chunk.json", None, Chunk.model_json_schema),
    SchemaSource("RetrievalRequest", "internal/retrieval-request.json", None, RetrievalRequest.model_json_schema),
    SchemaSource("RetrievalFacts", "internal/retrieval-facts.json", None, RetrievalFacts.model_json_schema),
    SchemaSource(
        "RetrievalDocumentFacts",
        "internal/retrieval-document-facts.json",
        None,
        RetrievalDocumentFacts.model_json_schema,
    ),
    SchemaSource(
        "RetrievalIndexBinding", "internal/retrieval-index-binding.json", None, RetrievalIndexBinding.model_json_schema
    ),
    SchemaSource(
        "AuthorizedRetrievalScope",
        "internal/authorized-retrieval-scope.json",
        None,
        AuthorizedRetrievalScope.model_json_schema,
    ),
    SchemaSource(
        "RetrievalSelection", "retrieval/retrieval-selection.json", "retrieval", RetrievalSelection.model_json_schema
    ),
    SchemaSource(
        "RetrievalFilters", "retrieval/retrieval-filters.json", "retrieval", RetrievalFilters.model_json_schema
    ),
    SchemaSource("RetrievedChunk", "retrieval/retrieved-chunk.json", "retrieval", RetrievedChunk.model_json_schema),
    SchemaSource(
        "RetrievalDiagnostics",
        "retrieval/retrieval-diagnostics.json",
        "retrieval",
        RetrievalDiagnostics.model_json_schema,
    ),
    SchemaSource("RetrievalResult", "retrieval/retrieval-result.json", "retrieval", RetrievalResult.model_json_schema),
    SchemaSource("ScoreComponents", "retrieval/score-components.json", "retrieval", ScoreComponents.model_json_schema),
    SchemaSource("ChunkSource", "retrieval/chunk-source.json", "retrieval", ChunkSource.model_json_schema),
    SchemaSource("ChunkSourceSpan", "retrieval/chunk-source-span.json", "retrieval", ChunkSourceSpan.model_json_schema),
    SchemaSource("ChunkMetadata", "retrieval/chunk-metadata.json", "retrieval", ChunkMetadata.model_json_schema),
    SchemaSource("Provider", "models/provider.json", "models", Provider.model_json_schema),
    SchemaSource("ModelConfig", "models/model-config.json", "models", ModelConfig.model_json_schema),
    SchemaSource("ModelCost", "models/model-cost.json", "models", ModelCost.model_json_schema),
    SchemaSource("ModelUsage", "models/model-usage.json", "models", ModelUsage.model_json_schema),
    SchemaSource("ModelFailure", "models/model-failure.json", "models", ModelFailure.model_json_schema),
    SchemaSource("SecretReference", "internal/secret-reference.json", None, SecretReference.model_json_schema),
    SchemaSource("StoredProvider", "internal/stored-provider.json", None, StoredProvider.model_json_schema),
    SchemaSource("StoredModelConfig", "internal/stored-model-config.json", None, StoredModelConfig.model_json_schema),
    SchemaSource("ModelRequest", "internal/model-request.json", None, TypeAdapter(ModelRequest).json_schema),
    SchemaSource("ModelResponse", "internal/model-response.json", None, ModelResponse.model_json_schema),
    SchemaSource("ModelStreamEvent", "internal/model-stream-event.json", None, ModelStreamEvent.model_json_schema),
    SchemaSource("TokenMeasurement", "internal/token-measurement.json", None, TokenMeasurement.model_json_schema),
    SchemaSource("ModelCallFacts", "internal/model-call-facts.json", None, ModelCallFacts.model_json_schema),
    SchemaSource("PreparedModelCall", "internal/prepared-model-call.json", None, PreparedModelCall.model_json_schema),
    SchemaSource("Conversation", "chat/conversation.json", "chat", Conversation.model_json_schema),
    SchemaSource("Message", "chat/message.json", "chat", Message.model_json_schema),
    SchemaSource("Citation", "chat/citation.json", "chat", Citation.model_json_schema),
    SchemaSource("StoredConversation", "internal/stored-conversation.json", None, StoredConversation.model_json_schema),
    SchemaSource("StoredMessage", "internal/stored-message.json", None, StoredMessage.model_json_schema),
    SchemaSource("Trace", "observability/trace.json", "observability", Trace.model_json_schema),
    SchemaSource("TraceSpan", "observability/trace-span.json", "observability", TraceSpan.model_json_schema),
    SchemaSource("AuditEvent", "observability/audit-event.json", "observability", AuditEvent.model_json_schema),
    SchemaSource("TraceIdentityLink", "internal/trace-identity-link.json", None, TraceIdentityLink.model_json_schema),
    SchemaSource("StoredAuditEvent", "internal/stored-audit-event.json", None, StoredAuditEvent.model_json_schema),
)


def encoded(value: object) -> str:
    payload = RootModel[JsonValue].model_validate(value).root
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def contract_artifacts() -> dict[Path, str]:
    """Generate without network calls or private profile-dependent API metadata."""
    application = create_app(Settings(app_name="EnterpriseRag", environment="test", infrastructure_enabled=False))
    output = ROOT / "docs/api"
    artifacts = {output / "openapi.json": encoded(application.openapi())}
    entries: list[dict[str, JsonValue]] = []
    for source in SCHEMAS:
        path = f"schemas/{source.path}"
        schema = RootModel[dict[str, JsonValue]].model_validate(source.generate()).root
        artifacts[output / path] = encoded({"$schema": "https://json-schema.org/draft/2020-12/schema", **schema})
        entries.append(
            {
                "name": source.name,
                "path": path,
                "visibility": "internal" if source.path.startswith("internal/") else "public",
                "frontend_group": source.frontend_group,
            }
        )
    artifacts[output / "schema-catalog.json"] = encoded({"schema_version": "1.0", "schemas": entries})
    return artifacts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail when committed artifacts differ from current DTOs")
    arguments = parser.parse_args()
    changed: list[str] = []
    for path, content in contract_artifacts().items():
        if arguments.check:
            if not path.exists() or path.read_text() != content:
                changed.append(str(path.relative_to(ROOT)))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
    if changed:
        raise SystemExit("Contract artifacts are stale; run make contracts:\n" + "\n".join(changed))
    command = ["node", "frontend/packages/api-codegen/src/generate.mjs"]
    if arguments.check:
        command.append("--check")
    subprocess.run(command, cwd=ROOT, check=True)
    print("HTTP contract artifacts checked." if arguments.check else "HTTP contract artifacts generated.")


if __name__ == "__main__":
    main()
