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
from app.modules.policy.domain.contracts import (
    AccessContext,
    AuthorizationRequest,
    AuthorizationSnapshot,
    PolicyDecision,
    ResourceGrant,
)
from pydantic import JsonValue, RootModel, TypeAdapter

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class SchemaSource:
    """One authoritative schema registration, including visibility and frontend consumer."""

    name: str
    path: str
    frontend_group: Literal["common", "iam"] | None
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
