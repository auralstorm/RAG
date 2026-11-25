"""Purpose-bound cookie sessions, exact browser origins and CSRF-protected mutations."""

from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime
from typing import Literal, TypeVar

from fastapi import APIRouter, HTTPException, Request, Response

from app.api.audit_context import audit_context
from app.modules.iam.api.schemas import AuthConfiguration, AuthSessionResponse, CsrfResponse, LoginCredentials
from app.modules.iam.api.security import guard_origin as enforce_origin
from app.modules.iam.application.login import LoginService
from app.modules.iam.application.sessions import SessionService
from app.modules.iam.domain.identity_providers import PasswordCredentials
from app.modules.iam.domain.sessions import (
    Application,
    AuthenticationDenied,
    AuthenticationThrottled,
    AuthenticationUnavailable,
    SessionIssue,
)

ResultT = TypeVar("ResultT")


def create_auth_router(
    service: SessionService | None,
    origins: Mapping[Application, list[str]],
    *,
    secure_cookies: bool,
    password_login: LoginService[PasswordCredentials] | None = None,
    password_login_mode: Literal["local", "platform"] | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])

    def current_service() -> SessionService:
        if service is None:
            raise HTTPException(503)
        return service

    def current_login() -> LoginService[PasswordCredentials]:
        if password_login is None:
            raise AuthenticationUnavailable()
        return password_login

    def guard_origin(request: Request, application: Application, *, mutation: bool = False) -> None:
        enforce_origin(request, application, origins, mutation=mutation)

    async def invoke(operation: Callable[[], Awaitable[ResultT]]) -> ResultT:
        try:
            return await operation()
        except AuthenticationThrottled as error:
            raise HTTPException(429, headers={"Retry-After": "60"}) from error
        except AuthenticationDenied as error:
            raise HTTPException(401) from error
        except AuthenticationUnavailable as error:
            raise HTTPException(503) from error

    def public_session(issue: SessionIssue, response: Response, *, set_credentials: bool) -> AuthSessionResponse:
        response.headers["Cache-Control"] = "no-store"
        if set_credentials:
            now = datetime.now(UTC)
            for kind, token, expires in (
                ("access", issue.access_token, issue.access_expires_at),
                ("refresh", issue.refresh_token, issue.session.expires_at),
            ):
                response.set_cookie(
                    f"er_{issue.session.application}_{kind}",
                    token,
                    max_age=max(0, int((expires - now).total_seconds())),
                    httponly=True,
                    secure=secure_cookies,
                    samesite="strict",
                    path="/",
                )
        return AuthSessionResponse(
            user=issue.user,
            application=issue.session.application,
            expires_at=issue.access_expires_at,
            csrf_token=issue.csrf_token,
        )

    @router.get("/{application}/config")
    async def configuration(application: Application, request: Request, response: Response) -> AuthConfiguration:
        guard_origin(request, application)
        response.headers["Cache-Control"] = "no-store"
        return AuthConfiguration(mode=password_login_mode or "unavailable")

    @router.post("/{application}/login")
    async def login(
        application: Application, payload: LoginCredentials, request: Request, response: Response
    ) -> AuthSessionResponse:
        context = audit_context(request)
        try:
            guard_origin(request, application, mutation=True)
        except HTTPException:
            if service is not None:
                await invoke(lambda: current_service().denied_login(context))
            raise
        issue = await invoke(
            lambda: current_login().login(
                application,
                PasswordCredentials(payload.username, payload.password.get_secret_value()),
                client_key=request.client.host if request.client else "unknown",
                request_id=context.request_id,
                trace_id=context.trace_id,
                ip_address=context.ip_address,
            )
        )
        return public_session(issue, response, set_credentials=True)

    @router.get("/{application}/me")
    async def me(application: Application, request: Request, response: Response) -> AuthSessionResponse:
        guard_origin(request, application)
        issue = await invoke(
            lambda: current_service().current(application, request.cookies.get(f"er_{application}_access", ""))
        )
        return public_session(issue, response, set_credentials=False)

    @router.get("/{application}/csrf")
    async def csrf(application: Application, request: Request, response: Response) -> CsrfResponse:
        guard_origin(request, application)
        response.headers["Cache-Control"] = "no-store"
        token = await invoke(
            lambda: current_service().refresh_csrf(application, request.cookies.get(f"er_{application}_refresh", ""))
        )
        return CsrfResponse(csrf_token=token)

    @router.post("/{application}/refresh")
    async def refresh(application: Application, request: Request, response: Response) -> AuthSessionResponse:
        guard_origin(request, application, mutation=True)
        issue = await invoke(
            lambda: current_service().refresh(
                application,
                request.cookies.get(f"er_{application}_refresh", ""),
                request.headers.get("X-CSRF-Token", ""),
            )
        )
        if issue is None:
            raise HTTPException(401)
        return public_session(issue, response, set_credentials=True)

    @router.post("/{application}/logout", status_code=204)
    async def logout(application: Application, request: Request) -> Response:
        guard_origin(request, application, mutation=True)
        await invoke(
            lambda: current_service().refresh(
                application,
                request.cookies.get(f"er_{application}_refresh", ""),
                request.headers.get("X-CSRF-Token", ""),
                logout=True,
            )
        )
        response = Response(status_code=204, headers={"Cache-Control": "no-store"})
        for kind in ("access", "refresh"):
            response.delete_cookie(
                f"er_{application}_{kind}", path="/", httponly=True, secure=secure_cookies, samesite="strict"
            )
        return response

    return router
