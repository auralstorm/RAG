"""Aggregate bounded dependency probes without returning sensitive diagnostics."""

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from time import perf_counter
from typing import Literal

from pydantic import BaseModel

from app.core.observability import observe_operation

type DependencyCheck = Callable[[], Awaitable[None]]


class ReadinessReport(BaseModel):
    status: Literal["ready", "not_ready"]
    dependencies: dict[str, bool]


async def check_dependencies(
    checks: Mapping[str, DependencyCheck], timeout: float, *, record: Callable[[str, bool, float], None] | None = None
) -> ReadinessReport:
    """Run independent probes concurrently; cancellation still propagates to the caller."""
    if not checks:
        return ReadinessReport(status="not_ready", dependencies={"configuration": False})

    async def check_one(name: str, check: DependencyCheck) -> tuple[str, bool]:
        started = perf_counter()
        try:
            with observe_operation(f"dependency.{name}"):
                await asyncio.wait_for(check(), timeout=timeout)
            available = True
        except Exception:
            available = False
        if record is not None:
            record(name, available, perf_counter() - started)
        return name, available

    results = await asyncio.gather(*(check_one(name, check) for name, check in checks.items()))
    dependencies = dict(results)
    return ReadinessReport(status="ready" if all(dependencies.values()) else "not_ready", dependencies=dependencies)
