"""Protected RBAC administration and self-scoped capability views."""

from collections.abc import Awaitable, Callable, Mapping
from typing import Annotated, TypeVar
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Query, Request, Response

from app.api.audit_context import audit_context
from app.api.schemas.common import PageResponse, PaginationQuery
from app.modules.audit.domain.contracts import AuditAction
from app.modules.iam.api.rbac_schemas import (
    AssignRoles,
    CapabilityView,
    ConfirmedMutation,
    CreateRole,
    GrantView,
    KnowledgeScope,
    PutGrant,
    RoleView,
    UpdateRole,
)
from app.modules.iam.api.security import guard_origin
from app.modules.iam.application.rbac import MutationContext, RbacService
from app.modules.iam.domain.contracts import Permission
from app.modules.iam.domain.rbac import AuthorizationDenied, RbacConflict, RoleDetails
from app.modules.iam.domain.sessions import Application, AuthenticationDenied, AuthenticationUnavailable
from app.modules.policy.domain.contracts import ResourceGrant, ResourcePrincipalType

ResultT = TypeVar("ResultT")


def create_rbac_router(service: RbacService | None, origins: Mapping[Application, list[str]]) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["authorization"])

    def current_service() -> RbacService:
        if service is None:
            raise HTTPException(503)
        return service

    def token(request: Request, application: Application = "admin") -> str:
        guard_origin(request, application, origins)
        return request.cookies.get(f"er_{application}_access", "")

    def context(request: Request, payload: ConfirmedMutation) -> MutationContext:
        correlated = audit_context(request)
        return MutationContext(
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
        except RbacConflict as error:
            raise HTTPException(409) from error
        except AuthenticationUnavailable as error:
            raise HTTPException(503) from error

    async def invoke_mutation(
        operation: Callable[[str], Awaitable[ResultT]],
        response: Response,
        request: Request,
        action: AuditAction,
        object_id: UUID | None = None,
    ) -> ResultT:
        async def execute() -> ResultT:
            try:
                guard_origin(request, "admin", origins, mutation=True)
            except HTTPException:
                if service is not None:
                    await service.denied_mutation(audit_context(request), action, object_id)
                raise
            return await operation(request.cookies.get("er_admin_access", ""))

        return await invoke(execute, response)

    def role_view(details: RoleDetails) -> RoleView:
        return RoleView(role=details.role, permission_codes=tuple(sorted(details.permission_codes)))

    def page[ItemT](items: tuple[ItemT, ...], query: PaginationQuery) -> PageResponse[ItemT]:
        start = (query.page - 1) * query.page_size
        return PageResponse(
            items=list(items[start : start + query.page_size]),
            total=len(items),
            page=query.page,
            page_size=query.page_size,
        )

    @router.get("/authorization/{application}/me")
    async def capabilities(application: Application, request: Request, response: Response) -> CapabilityView:
        authority = await invoke(
            lambda: current_service().capabilities(application, token(request, application)), response
        )
        return CapabilityView(
            subject_id=authority.session.user.id,
            application=application,
            policy_version=authority.context.policy_version,
            roles=tuple(item.role for item in authority.roles),
            permission_codes=tuple(sorted(authority.snapshot.permission_codes)),
        )

    @router.get("/authorization/{application}/knowledge-bases")
    async def scopes(
        application: Application, request: Request, response: Response, query: Annotated[PaginationQuery, Query()]
    ) -> PageResponse[KnowledgeScope]:
        result = await invoke(
            lambda: current_service().knowledge_scope(application, token(request, application)), response
        )
        return page(tuple(KnowledgeScope(kb_id=kb, can_manage=manage) for kb, manage in result), query)

    @router.get("/authorization/{application}/knowledge-bases/{kb_id}")
    async def scope(application: Application, kb_id: UUID, request: Request, response: Response) -> KnowledgeScope:
        can_manage = await invoke(
            lambda: current_service().knowledge_access(application, token(request, application), kb_id), response
        )
        return KnowledgeScope(kb_id=kb_id, can_manage=can_manage)

    @router.get("/admin/roles")
    async def roles(
        request: Request, response: Response, query: Annotated[PaginationQuery, Query()]
    ) -> PageResponse[RoleView]:
        result = await invoke(lambda: current_service().list_roles(token(request)), response)
        return page(tuple(role_view(item) for item in result), query)

    @router.get("/admin/permissions")
    async def permissions(
        request: Request, response: Response, query: Annotated[PaginationQuery, Query()]
    ) -> PageResponse[Permission]:
        result = await invoke(lambda: current_service().list_permissions(token(request)), response)
        return page(result, query)

    @router.post("/admin/roles", status_code=201)
    async def create(payload: CreateRole, request: Request, response: Response) -> RoleView:
        result = await invoke_mutation(
            lambda access: current_service().create_role(
                access,
                context(request, payload),
                payload.code,
                payload.name,
                payload.permission_codes,
            ),
            response,
            request,
            AuditAction.ROLE_CHANGE,
        )
        return role_view(result)

    @router.patch("/admin/roles/{role_id}")
    async def update(role_id: UUID, payload: UpdateRole, request: Request, response: Response) -> RoleView:
        result = await invoke_mutation(
            lambda access: current_service().update_role(
                access,
                context(request, payload),
                role_id,
                payload.name,
                payload.permission_codes,
            ),
            response,
            request,
            AuditAction.PERMISSION_CHANGE,
            role_id,
        )
        return role_view(result)

    @router.delete("/admin/roles/{role_id}", status_code=204)
    async def delete(role_id: UUID, payload: ConfirmedMutation, request: Request, response: Response) -> None:
        await invoke_mutation(
            lambda access: current_service().delete_role(access, context(request, payload), role_id),
            response,
            request,
            AuditAction.ROLE_CHANGE,
            role_id,
        )

    @router.put("/admin/users/{user_id}/roles", status_code=204)
    async def assign(user_id: UUID, payload: AssignRoles, request: Request, response: Response) -> None:
        await invoke_mutation(
            lambda access: current_service().assign_roles(access, context(request, payload), user_id, payload.role_ids),
            response,
            request,
            AuditAction.ROLE_CHANGE,
            user_id,
        )

    @router.get("/admin/kb-access/{kb_id}")
    async def grants(
        kb_id: UUID, request: Request, response: Response, query: Annotated[PaginationQuery, Query()]
    ) -> PageResponse[GrantView]:
        result = await invoke(lambda: current_service().list_grants(token(request), kb_id), response)
        return page(tuple(GrantView(application=app, grant=grant) for app, grant in result), query)

    @router.put("/admin/kb-access/{kb_id}", status_code=204)
    async def put_grant(kb_id: UUID, payload: PutGrant, request: Request, response: Response) -> None:
        grant = ResourceGrant(
            id=uuid4(),
            kb_id=kb_id,
            principal_type=ResourcePrincipalType(payload.principal_type),
            principal_id=payload.principal_id,
            permission=payload.permission,
        )
        await invoke_mutation(
            lambda access: current_service().put_grant(access, context(request, payload), payload.application, grant),
            response,
            request,
            AuditAction.PERMISSION_CHANGE,
            kb_id,
        )

    @router.delete("/admin/kb-access/{kb_id}/{grant_id}", status_code=204)
    async def delete_grant(
        kb_id: UUID, grant_id: UUID, payload: ConfirmedMutation, request: Request, response: Response
    ) -> None:
        await invoke_mutation(
            lambda access: current_service().delete_grant(access, context(request, payload), kb_id, grant_id),
            response,
            request,
            AuditAction.PERMISSION_CHANGE,
            kb_id,
        )

    return router
