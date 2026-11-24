"""Process liveness; infrastructure readiness is implemented in P0-02."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health/live", tags=["health"])
async def liveness() -> dict[str, str]:
    """Report that the API process can serve HTTP requests."""
    return {"status": "ok"}
