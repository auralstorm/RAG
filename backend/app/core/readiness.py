"""Aggregate bounded dependency probes without returning sensitive diagnostics."""

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from typing import Literal

from pydantic import BaseModel

type DependencyCheck = Callable[[], Awaitable[None]]


class ReadinessReport(BaseModel):
    status: Literal["ready", "not_ready"]
    dependencies: dict[str, bool]


async def check_dependencies(checks: Mapping[str, DependencyCheck], timeout: float) -> ReadinessReport:
    """Run independent probes concurrently; cancellation still propagates to the caller."""
    if not checks:
        return ReadinessReport(status="not_ready", dependencies={"configuration": False})

    async def check_one(name: str, check: DependencyCheck) -> tuple[str, bool]:
        try:
            await asyncio.wait_for(check(), timeout=timeout)
            return name, True
        except Exception:
            return name, False

    results = await asyncio.gather(*(check_one(name, check) for name, check in checks.items()))
    dependencies = dict(results)
    return ReadinessReport(status="ready" if all(dependencies.values()) else "not_ready", dependencies=dependencies)
