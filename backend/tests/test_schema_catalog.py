"""Check that authentication facts stay outside the generated frontend contract surface."""

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
    assert set(paths) == {"/health/live", "/health/ready"}
