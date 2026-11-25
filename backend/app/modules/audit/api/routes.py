"""Only authorized read access is public; audit append/update/delete have no HTTP route."""

from collections.abc import Mapping
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, Response

from app.api.schemas.common import PageResponse
from app.modules.audit.api.schemas import AuditLogView, AuditQuery
from app.modules.audit.application.queries import AuditService
from app.modules.audit.domain.queries import AuditCriteria, AuditUnavailable
from app.modules.iam.api.security import guard_origin
from app.modules.iam.domain.rbac import AuthorizationDenied
from app.modules.iam.domain.sessions import Application, AuthenticationDenied, AuthenticationUnavailable


def create_audit_router(service: AuditService | None, origins: Mapping[Application, list[str]]) -> APIRouter:
    router = APIRouter(prefix="/api/v1/admin", tags=["audit"])

    @router.get("/audit-logs")
    async def search(
        request: Request, response: Response, query: Annotated[AuditQuery, Query()]
    ) -> PageResponse[AuditLogView]:
        guard_origin(request, "admin", origins)
        if service is None:
            raise HTTPException(503)
        criteria = AuditCriteria.model_validate(query.model_dump(exclude={"page", "page_size"}))
        try:
            result = await service.search(
                request.cookies.get("er_admin_access", ""), criteria, page=query.page, page_size=query.page_size
            )
        except AuthenticationDenied as error:
            raise HTTPException(401) from error
        except AuthorizationDenied as error:
            raise HTTPException(403) from error
        except (AuditUnavailable, AuthenticationUnavailable) as error:
            raise HTTPException(503) from error
        response.headers["Cache-Control"] = "no-store"
        return PageResponse(
            items=[
                AuditLogView.model_validate(event.model_dump() | {"module": event.action.value.split(".")[0]})
                for event in result.events
            ],
            total=result.total,
            page=query.page,
            page_size=query.page_size,
        )

    return router
