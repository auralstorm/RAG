"""FastAPI application factory and ASGI entry point."""

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.adapters.infrastructure import InfrastructureMonitor
from app.adapters.telemetry import OpenTelemetry
from app.api.errors import common_error_responses, install_error_handlers
from app.api.health import create_health_router
from app.api.middleware.failures import SafeFailureMiddleware
from app.api.middleware.request_context import RequestContextMiddleware
from app.api.v1.router import router as api_router
from app.core.auditing import create_audit_service
from app.core.authentication import create_iam_services
from app.core.config import Settings, load_settings
from app.modules.audit.api.routes import create_audit_router
from app.modules.iam.api.rbac_routes import create_rbac_router
from app.modules.iam.api.routes import create_auth_router


def create_app(settings: Settings | None = None, *, telemetry: OpenTelemetry | None = None) -> FastAPI:
    """Assemble the HTTP application from validated configuration."""
    configuration = settings if settings is not None else load_settings()
    observer = telemetry if telemetry is not None else OpenTelemetry(configuration)
    monitor = InfrastructureMonitor(configuration, observer)
    iam = create_iam_services(configuration)
    sessions, rbac = iam.sessions, iam.rbac

    async def sample_metrics() -> None:
        while True:
            try:
                await monitor.sample_metrics()
            except Exception:
                logging.getLogger(__name__).warning("telemetry_sampler_failed")
            await asyncio.sleep(configuration.telemetry_interval_seconds)

    @asynccontextmanager
    async def lifespan(_application: FastAPI) -> AsyncGenerator[None, None]:
        task: asyncio.Task[None] | None = None
        try:
            observer.start()
            await monitor.start()
            if configuration.telemetry_enabled:
                task = asyncio.create_task(sample_metrics())
            yield
        finally:
            if task is not None:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            try:
                await monitor.close()
            finally:
                await observer.close()

    application = FastAPI(
        title=configuration.app_name, version="0.1.0", lifespan=lifespan, responses=common_error_responses()
    )
    install_error_handlers(application)
    application.add_middleware(SafeFailureMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=configuration.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "Idempotency-Key", "traceparent", "X-CSRF-Token"],
        expose_headers=["X-Request-ID", "X-Trace-ID", "traceparent"],
    )
    application.add_middleware(RequestContextMiddleware, telemetry=observer)
    application.include_router(create_health_router(monitor.check))
    application.include_router(api_router)
    application.include_router(
        create_auth_router(
            sessions,
            {"chat": configuration.auth_chat_origins, "admin": configuration.auth_admin_origins},
            secure_cookies=configuration.environment == "production",
            password_login=iam.password_login,
            password_login_mode=iam.password_login_mode,
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
