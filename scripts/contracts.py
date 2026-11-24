"""Generate and check HTTP contract artifacts from the real app and common DTOs."""

import argparse
import json
import subprocess
from pathlib import Path

from app.api.schemas.common import ApiErrorEnvelope, PageResponse, PaginationQuery
from app.core.config import Settings
from app.main import create_app
from pydantic import JsonValue, RootModel

ROOT = Path(__file__).resolve().parents[1]


def encoded(value: object) -> str:
    payload = RootModel[JsonValue].model_validate(value).root
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def contract_artifacts() -> dict[Path, str]:
    """Generate without network calls or private profile-dependent API metadata."""
    application = create_app(Settings(app_name="EnterpriseRag", environment="test", infrastructure_enabled=False))
    output = ROOT / "docs/api"
    return {
        output / "openapi.json": encoded(application.openapi()),
        output / "schemas/api-error.json": encoded(ApiErrorEnvelope.model_json_schema()),
        output / "schemas/pagination-query.json": encoded(PaginationQuery.model_json_schema()),
        output / "schemas/page-response.json": encoded(PageResponse[JsonValue].model_json_schema()),
    }


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
