"""FastAPI application factory and ASGI entry point."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.adapters.infrastructure import InfrastructureMonitor
from app.api.health import create_health_router
from app.api.v1.router import router as api_router
from app.core.config import Settings, load_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Assemble the HTTP application from validated configuration."""
    configuration = settings if settings is not None else load_settings()
    monitor = InfrastructureMonitor(configuration)

    @asynccontextmanager
    async def lifespan(_application: FastAPI) -> AsyncGenerator[None, None]:
        try:
            await monitor.start()
            yield
        finally:
            await monitor.close()

    application = FastAPI(title=configuration.app_name, version="0.1.0", lifespan=lifespan)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=configuration.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "Idempotency-Key"],
    )
    application.include_router(create_health_router(monitor.check))
    application.include_router(api_router)
    return application


app = create_app()
