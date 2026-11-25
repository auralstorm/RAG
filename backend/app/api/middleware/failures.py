"""Sanitize unexpected failures inside CORS while outer request observation remains active."""

import logging

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.errors import error_response
from app.core.observability import current_request

logger = logging.getLogger(__name__)


class SafeFailureMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        response_started = False

        async def tracked_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, tracked_send)
        except Exception:
            if response_started:
                raise RuntimeError("HTTP response stream aborted") from None
            context = current_request.get()
            if context is None:
                raise RuntimeError("HTTP request context is missing") from None
            logger.error("unhandled_http_error", extra={"response_started": False})
            await error_response(context, 500)(scope, receive, tracked_send)
