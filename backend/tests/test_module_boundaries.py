"""Enforce the backend's dependency direction for static Python imports."""

import ast
from collections.abc import Iterator
from importlib.util import resolve_name
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
INFRASTRUCTURE_PACKAGES = frozenset(
    {
        "aio_pika",
        "alembic",
        "celery",
        "docling",
        "elasticsearch",
        "httpx",
        "httpx2",
        "langgraph",
        "litellm",
        "llama_index",
        "minio",
        "opentelemetry",
        "psycopg",
        "psycopg_pool",
        "redis",
        "sqlalchemy",
        "urllib3",
    }
)


def module_layer(parts: tuple[str, ...]) -> tuple[str, str] | None:
    if len(parts) >= 4 and parts[:2] == ("app", "modules"):
        return parts[2], parts[3]
    return None


def respects_boundary(module: str, dependency: str) -> bool:
    source = tuple(module.split("."))
    target = tuple(dependency.split("."))
    source_layer = module_layer(source)
    target_layer = module_layer(target)
    layer = source_layer[1] if source_layer else source[1]

    if target_layer and target_layer[1] == "infrastructure" and source_layer and source_layer[0] != target_layer[0]:
        return False
    if layer not in {"api", "application", "domain"}:
        return True
    if target[0] in INFRASTRUCTURE_PACKAGES or target[:2] in {("app", "adapters"), ("app", "main")}:
        return False
    if target_layer and target_layer[1] == "infrastructure":
        return False
    if layer in {"application", "domain"}:
        if target[0] in {"fastapi", "starlette"} or target[:2] == ("app", "api"):
            return False
        if target_layer and target_layer[1] == "api":
            return False
    return layer != "domain" or target_layer is None or target_layer[1] == "domain"


def dependencies(tree: ast.AST, package: str) -> Iterator[tuple[int, str]]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from ((node.lineno, name.name) for name in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = resolve_name("." * node.level + (node.module or ""), package)
            yield node.lineno, base
            yield from ((node.lineno, f"{base}.{name.name}") for name in node.names)


def test_backend_module_dependencies_follow_layer_boundaries() -> None:
    violations: list[str] = []
    for path in sorted((BACKEND / "app").rglob("*.py")):
        relative = path.relative_to(BACKEND)
        module = ".".join(relative.with_suffix("").parts)
        package = module.rpartition(".")[0]
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(relative))
        for line, dependency in dependencies(tree, package):
            if not respects_boundary(module, dependency):
                violations.append(f"{relative}:{line} must not import {dependency}")
    assert not violations, "\n".join(violations)


@pytest.mark.parametrize(
    ("module", "statement", "expected"),
    [
        ("app.modules.iam.domain.user", "from fastapi import Request", False),
        ("app.modules.iam.domain.user", "from ..application import service", False),
        ("app.modules.iam.application.user", "from app import adapters", False),
        ("app.modules.iam.infrastructure.repo", "from app.modules.policy import infrastructure", False),
        ("app.api.v1.router", "from sqlalchemy import select", False),
        ("app.api.v1.router", "from app.modules.iam.application import service", True),
        ("app.modules.policy.domain.contracts", "from app.modules.iam.domain import contracts", True),
    ],
)
def test_dependency_checker_handles_direct_and_from_imports(module: str, statement: str, expected: bool) -> None:
    imported = dependencies(ast.parse(statement), module.rpartition(".")[0])
    assert all(respects_boundary(module, dependency) for _, dependency in imported) is expected
