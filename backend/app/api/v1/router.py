"""Business routes are registered by their owning modules."""

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1")
