"""Pure ASGI correlation and safe failures, without buffering request or stream bodies."""

import logging

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.errors import error_response
from app.core.request_context import create_request_context

logger = logging.getLogger(__name__)


class RequestContextMiddleware:
    """Correlate HTTP responses; a stream already started cannot become a JSON error."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        parents = [value.decode("latin-1") for key, value in scope.get("headers", []) if key.lower() == b"traceparent"]
        context = create_request_context(parents[0] if len(parents) == 1 else None)
        scope.setdefault("state", {})["request_context"] = context
        response_started = False

        async def contextual_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
                headers = MutableHeaders(scope=message)
                for name, value in context.response_headers().items():
                    headers[name] = value
            await send(message)

        try:
            await self.app(scope, receive, contextual_send)
        except Exception as exception:
            logger.error(
                "unhandled_http_error",
                extra={
                    "request_id": str(context.request_id),
                    "trace_id": context.trace_id,
                    "exception_type": type(exception).__name__,
                    "response_started": response_started,
                },
            )
            if response_started:
                # ASGI servers log escaping exceptions; keep the raw diagnostic out of that log.
                raise RuntimeError("HTTP response stream aborted") from None
            await error_response(context, 500)(scope, receive, contextual_send)
