"""Convert HTTP boundary failures to public summaries without serializing exceptions."""

from dataclasses import dataclass

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from pydantic import JsonValue
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from app.api.schemas.common import ApiError, ApiErrorEnvelope
from app.core.request_context import RequestContext


@dataclass(frozen=True)
class HttpErrorDefinition:
    code: str
    message: str
    retryable: bool = False


HTTP_ERRORS = {
    400: HttpErrorDefinition("API_BAD_REQUEST", "请求格式不正确"),
    401: HttpErrorDefinition("AUTHENTICATION_REQUIRED", "请先登录"),
    403: HttpErrorDefinition("ACCESS_DENIED", "没有访问此资源的权限"),
    404: HttpErrorDefinition("RESOURCE_NOT_FOUND", "请求的资源不存在"),
    405: HttpErrorDefinition("METHOD_NOT_ALLOWED", "此资源不支持该请求方法"),
    409: HttpErrorDefinition("RESOURCE_CONFLICT", "资源状态冲突，请刷新后重试"),
    413: HttpErrorDefinition("PAYLOAD_TOO_LARGE", "请求内容超过允许大小"),
    415: HttpErrorDefinition("UNSUPPORTED_MEDIA_TYPE", "不支持该内容类型"),
    422: HttpErrorDefinition("API_VALIDATION_ERROR", "请求参数不合法"),
    429: HttpErrorDefinition("RATE_LIMITED", "请求过于频繁，请稍后重试", retryable=True),
    500: HttpErrorDefinition("INTERNAL_ERROR", "服务暂时无法完成请求"),
    502: HttpErrorDefinition("UPSTREAM_UNAVAILABLE", "上游服务暂时不可用"),
    503: HttpErrorDefinition("SERVICE_UNAVAILABLE", "服务暂时不可用"),
    504: HttpErrorDefinition("UPSTREAM_TIMEOUT", "上游服务响应超时"),
}


def error_response(
    context: RequestContext,
    status_code: int,
    *,
    details: dict[str, JsonValue] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Build a safe error; retryability does not authorize automatic replay of writes."""
    definition = HTTP_ERRORS.get(status_code, HttpErrorDefinition("HTTP_ERROR", "请求无法完成"))
    envelope = ApiErrorEnvelope(
        error=ApiError(
            code=definition.code,
            message=definition.message,
            request_id=context.request_id,
            retryable=definition.retryable,
            details=details or {},
        )
    )
    return JSONResponse(
        status_code=status_code,
        content=envelope.model_dump(mode="json"),
        headers={**(headers or {}), **context.response_headers()},
    )


def request_context(request: Request) -> RequestContext:
    context: object = request.state.request_context
    if not isinstance(context, RequestContext):
        raise RuntimeError("HTTP request context is missing")
    return context


async def http_exception_handler(request: Request, exception: Exception) -> JSONResponse:
    if not isinstance(exception, HTTPException):
        raise TypeError("HTTP handler requires an HTTPException")
    # Keep standard protocol headers; raw exception.detail is not a public message.
    headers = {
        key: value
        for key, value in (exception.headers or {}).items()
        if key.lower() in ("www-authenticate", "retry-after", "allow")
    }
    return error_response(request_context(request), exception.status_code, headers=headers)


async def validation_exception_handler(request: Request, exception: Exception) -> JSONResponse:
    if not isinstance(exception, RequestValidationError):
        raise TypeError("Validation handler requires a RequestValidationError")
    # Pydantic errors include rejected values and arbitrary dictionary keys; emit only a count.
    return error_response(request_context(request), 422, details={"error_count": len(exception.errors())})


def install_error_handlers(application: FastAPI) -> None:
    application.add_exception_handler(HTTPException, http_exception_handler)
    application.add_exception_handler(RequestValidationError, validation_exception_handler)


def common_error_responses() -> dict[int | str, dict[str, object]]:
    return {
        status: {"model": ApiErrorEnvelope, "description": definition.message}
        for status, definition in HTTP_ERRORS.items()
    }
