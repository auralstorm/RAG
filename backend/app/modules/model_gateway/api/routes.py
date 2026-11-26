"""Provider management API; every read and write uses current Admin policy facts."""

from collections.abc import Awaitable, Callable, Mapping
from typing import Annotated, TypeVar
from uuid import UUID

from app.api.audit_context import audit_context
from app.modules.iam.api.security import guard_origin
from app.modules.iam.domain.rbac import AuthorizationDenied, RbacConflict
from app.modules.iam.domain.sessions import Application, AuthenticationDenied, AuthenticationUnavailable
from app.modules.model_gateway.api.schemas import (
    CreateProvider,
    ProviderAdminView,
    ProviderMutation,
    ProviderPageResponse,
    ProviderQuery,
    ProviderVersionMutation,
    UpdateProvider,
)
from app.modules.model_gateway.application.providers import ProviderMutationContext, ProviderRegistryService
from app.modules.model_gateway.domain.registry import (
    ProviderConflict,
    ProviderNotFound,
    ProviderUnavailable,
    RegisteredProvider,
)
from fastapi import APIRouter, HTTPException, Query, Request, Response

ResultT = TypeVar("ResultT")


def provider_view(provider: RegisteredProvider) -> ProviderAdminView:
    public = provider.model_dump(
        include={
            "schema_version",
            "id",
            "name",
            "provider_type",
            "config_version",
            "status",
            "has_credential",
            "created_at",
            "updated_at",
        }
    )
    return ProviderAdminView.model_validate(
        public
        | {
            "base_url": provider.base_url,
            "timeout_seconds": provider.timeout_seconds,
            "proxy_configured": provider.proxy_ref is not None,
            "remarks": provider.remarks,
        }
    )


def create_provider_router(
    service: ProviderRegistryService | None, origins: Mapping[Application, list[str]]
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/admin/providers", tags=["providers"])

    def current_service() -> ProviderRegistryService:
        if service is None:
            raise HTTPException(503)
        return service

    def token(request: Request) -> str:
        guard_origin(request, "admin", origins)
        return request.cookies.get("er_admin_access", "")

    def mutation_context(request: Request, payload: ProviderMutation) -> ProviderMutationContext:
        correlated = audit_context(request)
        return ProviderMutationContext(
            payload.expected_policy_version,
            correlated.request_id,
            correlated.trace_id,
            request.headers.get("X-CSRF-Token", ""),
            correlated.ip_address,
        )

    async def invoke(operation: Callable[[], Awaitable[ResultT]], response: Response) -> ResultT:
        response.headers["Cache-Control"] = "no-store"
        try:
            return await operation()
        except AuthenticationDenied as error:
            raise HTTPException(401) from error
        except AuthorizationDenied as error:
            raise HTTPException(403) from error
        except (RbacConflict, ProviderConflict) as error:
            raise HTTPException(409) from error
        except ProviderNotFound as error:
            raise HTTPException(404) from error
        except (ProviderUnavailable, AuthenticationUnavailable) as error:
            raise HTTPException(503) from error

    async def invoke_mutation(
        operation: Callable[[ProviderRegistryService, str], Awaitable[ResultT]],
        request: Request,
        response: Response,
        payload: CreateProvider | UpdateProvider,
        provider_id: UUID | None = None,
    ) -> ResultT:
        async def execute() -> ResultT:
            registry = current_service()
            try:
                guard_origin(request, "admin", origins, mutation=True)
            except HTTPException:
                await registry.denied_mutation(audit_context(request), provider_id)
                raise
            return await operation(registry, request.cookies.get("er_admin_access", ""))

        return await invoke(execute, response)

    @router.get("")
    async def list_providers(
        request: Request,
        response: Response,
        query: Annotated[ProviderQuery, Query()],
    ) -> ProviderPageResponse:
        result = await invoke(
            lambda: current_service().list_providers(
                token(request),
                page=query.page,
                page_size=query.page_size,
                name=query.name,
                provider_type=query.provider_type,
                status=query.status,
            ),
            response,
        )
        return ProviderPageResponse(
            items=[provider_view(item) for item in result.items],
            total=result.total,
            page=query.page,
            page_size=query.page_size,
        )

    @router.post("", status_code=201)
    async def create(payload: CreateProvider, request: Request, response: Response) -> ProviderAdminView:
        provider = await invoke_mutation(
            lambda registry, access: registry.create_provider(
                access,
                mutation_context(request, payload),
                name=payload.name,
                provider_type=payload.provider_type,
                base_url=payload.base_url,
                timeout_seconds=payload.timeout_seconds,
                credential=payload.credential,
                proxy_url=payload.proxy_url,
                remarks=payload.remarks,
            ),
            request,
            response,
            payload,
        )
        return provider_view(provider)

    @router.get("/{provider_id}")
    async def get(provider_id: UUID, request: Request, response: Response) -> ProviderAdminView:
        provider = await invoke(lambda: current_service().get_provider(token(request), provider_id), response)
        return provider_view(provider)

    @router.patch("/{provider_id}")
    async def update(
        provider_id: UUID, payload: UpdateProvider, request: Request, response: Response
    ) -> ProviderAdminView:
        provider = await invoke_mutation(
            lambda registry, access: registry.update_provider(
                access,
                mutation_context(request, payload),
                provider_id,
                name=payload.name,
                provider_type=payload.provider_type,
                base_url=payload.base_url,
                timeout_seconds=payload.timeout_seconds,
                status=payload.status,
                credential=payload.credential,
                proxy_url=payload.proxy_url,
                remarks=payload.remarks,
                clear_proxy=payload.clear_proxy,
                expected_config_version=payload.expected_config_version,
            ),
            request,
            response,
            payload,
            provider_id,
        )
        return provider_view(provider)

    @router.delete("/{provider_id}", status_code=204)
    async def delete(
        provider_id: UUID,
        request: Request,
        response: Response,
        payload: ProviderVersionMutation,
    ) -> Response:
        async def execute() -> None:
            registry = current_service()
            try:
                guard_origin(request, "admin", origins, mutation=True)
            except HTTPException:
                await registry.denied_mutation(audit_context(request), provider_id)
                raise
            await registry.delete_provider(
                request.cookies.get("er_admin_access", ""),
                mutation_context(request, payload),
                provider_id,
                payload.expected_config_version,
            )

        await invoke(execute, response)
        return Response(status_code=204, headers={"Cache-Control": "no-store"})

    return router
