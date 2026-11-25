"""Check that private identity, authorization and storage facts stay outside frontend types."""

import json
from pathlib import Path

from app.core.config import Settings
from app.main import create_app

from scripts.contracts import SCHEMAS

ROOT = Path(__file__).resolve().parents[2]


def test_internal_identity_and_policy_schemas_are_not_exported_to_frontend() -> None:
    internal = [schema for schema in SCHEMAS if schema.path.startswith("internal/")]
    assert internal
    assert all(schema.frontend_group is None for schema in internal)
    generated = (ROOT / "frontend/packages/api-client/src/generated/iam.ts").read_text()
    for name in (
        "ExternalIdentity",
        "IdentityKey",
        "SubjectBinding",
        "AccessContext",
        "AuthorizationSnapshot",
        "PolicyDecision",
    ):
        assert f"readonly {name}:" not in generated
    assert "readonly issuer:" not in generated and "readonly subject:" not in generated
    catalog: dict[str, object] = json.loads((ROOT / "docs/api/schema-catalog.json").read_text())
    assert catalog["schema_version"] == "1.0"
    paths: dict[str, object] = create_app(Settings(infrastructure_enabled=False)).openapi()["paths"]
    assert set(paths) == {
        "/health/live",
        "/health/ready",
        "/api/v1/authorization/{application}/me",
        "/api/v1/authorization/{application}/knowledge-bases",
        "/api/v1/authorization/{application}/knowledge-bases/{kb_id}",
        "/api/v1/admin/roles",
        "/api/v1/admin/audit-logs",
        "/api/v1/admin/roles/{role_id}",
        "/api/v1/admin/permissions",
        "/api/v1/admin/users/{user_id}/roles",
        "/api/v1/admin/kb-access/{kb_id}",
        "/api/v1/admin/kb-access/{kb_id}/{grant_id}",
        *(
            f"/api/v1/auth/{{application}}/{action}"
            for action in ("config", "login", "me", "csrf", "refresh", "logout")
        ),
    }


def test_internal_knowledge_facts_are_not_exported_in_public_types_or_schemas() -> None:
    generated = (ROOT / "frontend/packages/api-client/src/generated/knowledge.ts").read_text()
    public_sources = [source for source in SCHEMAS if source.frontend_group == "knowledge"]
    assert public_sources
    for source in SCHEMAS:
        if source.path.startswith("internal/"):
            assert f"readonly {source.name}:" not in generated
    for field in ("object_key", "bucket", "physical_index_name", "alias_name", "allowed_subject_ids", "validation"):
        assert f"readonly {field}:" not in generated
        for source in public_sources:
            schema = (ROOT / "docs/api/schemas" / source.path).read_text()
            assert f'"{field}"' not in schema
    # This change must keep the application's existing HTTP surface unchanged.
    components = create_app(Settings(infrastructure_enabled=False)).openapi()["components"]["schemas"]
    assert "KnowledgeBase" not in components and "StoredObjectRef" not in components


def test_retrieval_types_exclude_private_parser_inputs_and_authorization_facts() -> None:
    generated = (ROOT / "frontend/packages/api-client/src/generated/retrieval.ts").read_text()
    for source in SCHEMAS:
        if source.path.startswith("internal/"):
            assert f"readonly {source.name}:" not in generated
    for field in ("object_key", "physical_index_name", "alias_name", "access_context", "permission_codes", "actor_ref"):
        assert f"readonly {field}:" not in generated
    assert "readonly RetrievedChunk:" in generated and "readonly RetrievalSelection:" in generated


def test_model_registry_types_exclude_credentials_vendor_routes_and_prompt_protocols() -> None:
    generated = (ROOT / "frontend/packages/api-client/src/generated/models.ts").read_text()
    for source in SCHEMAS:
        if source.path.startswith("internal/"):
            assert f"readonly {source.name}:" not in generated
    for field in (
        "api_key",
        "credential_ref",
        "secret_id",
        "base_url",
        "vendor_model_key",
        "messages",
        "texts",
        "access_context",
        "authorization",
    ):
        assert f"readonly {field}:" not in generated
    assert "readonly Provider:" in generated and "readonly ModelUsage:" in generated


def test_chat_types_exclude_private_owner_and_evidence_dependencies() -> None:
    generated = (ROOT / "frontend/packages/api-client/src/generated/chat.ts").read_text()
    for name in ("Conversation", "Message", "Citation"):
        assert f"readonly {name}:" in generated
    for field in ("StoredConversation", "StoredMessage", "owner_subject_id", "evidence_versions", "deleted_at"):
        assert f"readonly {field}:" not in generated
