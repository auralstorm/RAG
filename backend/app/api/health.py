"""Process liveness and dependency readiness HTTP adapters."""

from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Response

from app.core.readiness import ReadinessReport


async def liveness() -> dict[str, str]:
    """Report that the API process can serve HTTP requests."""
    return {"status": "ok"}


def create_health_router(check: Callable[[], Awaitable[ReadinessReport]]) -> APIRouter:
    router = APIRouter(tags=["health"])
    router.add_api_route("/health/live", liveness, methods=["GET"])

    @router.get("/health/ready", responses={503: {"model": ReadinessReport}})
    async def readiness(response: Response) -> ReadinessReport:
        report = await check()
        response.status_code = 200 if report.status == "ready" else 503
        return report

    return router
