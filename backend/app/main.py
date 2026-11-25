"""FastAPI application factory and ASGI entry point."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.adapters.infrastructure import InfrastructureMonitor
from app.api.errors import common_error_responses, install_error_handlers
from app.api.health import create_health_router
from app.api.middleware.request_context import RequestContextMiddleware
from app.api.v1.router import router as api_router
from app.core.auditing import create_audit_service
from app.core.authentication import create_iam_services
from app.core.config import Settings, load_settings
from app.modules.audit.api.routes import create_audit_router
from app.modules.iam.api.rbac_routes import create_rbac_router
from app.modules.iam.api.routes import create_auth_router


def create_app(settings: Settings | None = None) -> FastAPI:
    """Assemble the HTTP application from validated configuration."""
    configuration = settings if settings is not None else load_settings()
    monitor = InfrastructureMonitor(configuration)
    sessions, rbac = create_iam_services(configuration)

    @asynccontextmanager
    async def lifespan(_application: FastAPI) -> AsyncGenerator[None, None]:
        try:
            await monitor.start()
            yield
        finally:
            await monitor.close()

    application = FastAPI(
        title=configuration.app_name, version="0.1.0", lifespan=lifespan, responses=common_error_responses()
    )
    install_error_handlers(application)
    application.add_middleware(RequestContextMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=configuration.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "Idempotency-Key", "traceparent", "X-CSRF-Token"],
        expose_headers=["X-Request-ID", "X-Trace-ID", "traceparent"],
    )
    application.include_router(create_health_router(monitor.check))
    application.include_router(api_router)
    application.include_router(
        create_auth_router(
            sessions,
            {"chat": configuration.auth_chat_origins, "admin": configuration.auth_admin_origins},
            secure_cookies=configuration.environment == "production",
        )
    )
    application.include_router(
        create_rbac_router(rbac, {"chat": configuration.auth_chat_origins, "admin": configuration.auth_admin_origins})
    )
    application.include_router(
        create_audit_router(
            create_audit_service(configuration, rbac),
            {"chat": configuration.auth_chat_origins, "admin": configuration.auth_admin_origins},
        )
    )
    return application


app = create_app()
