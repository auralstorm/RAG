"""FastAPI application factory and ASGI entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.v1.router import router as api_router
from app.core.config import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Assemble the HTTP application from validated configuration."""
    configuration = settings if settings is not None else Settings()
    application = FastAPI(title=configuration.app_name, version="0.1.0")
    application.add_middleware(
        CORSMiddleware,
        allow_origins=configuration.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "Idempotency-Key"],
    )
    application.include_router(health_router)
    application.include_router(api_router)
    return application


app = create_app()
