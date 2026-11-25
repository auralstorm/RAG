"""Pure ASGI correlation and safe failures, without buffering request or stream bodies."""

import asyncio
import logging
from contextlib import nullcontext
from time import perf_counter

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.errors import error_response
from app.core.logging import exception_chain
from app.core.observability import HttpOutcome, Telemetry, current_request, current_telemetry
from app.core.request_context import create_request_context

logger = logging.getLogger(__name__)


class RequestContextMiddleware:
    """Correlate HTTP responses; a stream already started cannot become a JSON error."""

    def __init__(self, app: ASGIApp, telemetry: Telemetry | None = None) -> None:
        self.app = app
        self.telemetry = telemetry

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        parents = [value.decode("latin-1") for key, value in scope.get("headers", []) if key.lower() == b"traceparent"]
        initial = create_request_context(parents[0] if len(parents) == 1 else None)
        observation = self.telemetry.request(initial) if self.telemetry is not None else nullcontext(initial)
        with observation as context:
            scope.setdefault("state", {})["request_context"] = context
            request_token = current_request.set(context)
            telemetry_token = current_telemetry.set(self.telemetry)
            started = perf_counter()
            response_started, complete = False, False
            status = 0
            outcome: HttpOutcome = "completed"

            async def contextual_send(message: Message) -> None:
                nonlocal response_started, complete, status
                if message["type"] == "http.response.start":
                    response_started = True
                    status = message["status"]
                    headers = MutableHeaders(scope=message)
                    for name, value in context.response_headers().items():
                        headers[name] = value
                elif message["type"] == "http.response.body" and not message.get("more_body", False):
                    complete = True
                await send(message)

            try:
                await self.app(scope, receive, contextual_send)
                if not complete:
                    outcome = "aborted"
            except asyncio.CancelledError:
                outcome = "cancelled"
                raise
            except Exception as error:
                outcome = "aborted" if response_started else "error"
                logger.error(
                    "unhandled_http_error",
                    extra={"response_started": response_started, "diagnostic": exception_chain(error)},
                )
                if response_started:
                    raise RuntimeError("HTTP response stream aborted") from None
                await error_response(context, 500)(scope, receive, contextual_send)
            finally:
                try:
                    method = scope.get("method", "OTHER")
                    if method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "TRACE", "CONNECT"}:
                        method = "OTHER"
                    # Matched route templates are server constants; raw paths/queries never become labels.
                    route_object: object = scope.get("route")
                    route: object = getattr(route_object, "path", None)
                    route_name = route if isinstance(route, str) else "<unmatched>"
                    duration = perf_counter() - started
                    logger.info(
                        "http_request_completed",
                        extra={
                            "method": method,
                            "route": route_name,
                            "status": status,
                            "duration_seconds": duration,
                            "outcome": outcome,
                        },
                    )
                    if self.telemetry is not None:
                        self.telemetry.http_completed(method, route_name, status, duration, outcome)
                finally:
                    current_telemetry.reset(telemetry_token)
                    current_request.reset(request_token)
