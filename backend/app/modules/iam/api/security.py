"""Shared browser-origin boundary for cookie-authenticated IAM operations."""

from collections.abc import Mapping

from fastapi import HTTPException, Request

from app.modules.iam.domain.sessions import Application


def guard_origin(
    request: Request, application: Application, origins: Mapping[Application, list[str]], *, mutation: bool = False
) -> None:
    origin = request.headers.get("origin")
    if (mutation or origin is not None) and origin not in origins[application]:
        raise HTTPException(403)
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(403)
