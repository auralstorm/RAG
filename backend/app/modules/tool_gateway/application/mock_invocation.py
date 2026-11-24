"""Run the local fixture lookup using current, server-supplied authorization."""

from datetime import datetime

from app.modules.policy.application.authorization import authorize
from app.modules.policy.domain.contracts import (
    AccessContext,
    AccessPurpose,
    AuthorizationRequest,
    AuthorizationSnapshot,
)
from app.modules.tool_gateway.domain.contracts import (
    MOCK_PERMISSION,
    MockRequestId,
    MockStatus,
    MockToolOutput,
    ToolDefinition,
    ToolError,
    ToolInvocation,
    ToolOutcome,
    ToolResult,
)

SAMPLE_STATUSES = {MockRequestId.PENDING: MockStatus.PENDING, MockRequestId.COMPLETED: MockStatus.COMPLETED}


def invoke_mock_tool(
    invocation: ToolInvocation,
    context: AccessContext | None,
    authorization: AuthorizationSnapshot,
    definition: ToolDefinition | None,
    *,
    now: datetime,
) -> ToolResult:
    decision = authorize(
        AuthorizationRequest(permission_code=MOCK_PERMISSION, purpose=AccessPurpose.ADMIN),
        context,
        authorization,
        now=now,
    )
    output = None
    if not decision.allowed or authorization.environment == "production":
        error = ToolError.ACCESS_DENIED
    elif (
        definition is None
        or not definition.enabled
        or (definition.tool_id, definition.tool_version) != (invocation.tool_id, invocation.tool_version)
    ):
        error = ToolError.TOOL_UNAVAILABLE
    elif now >= invocation.deadline_at:
        error = ToolError.DEADLINE_EXCEEDED
    else:
        sample_id = invocation.arguments.sample_id
        sample_status = SAMPLE_STATUSES.get(sample_id)
        if sample_status is None:
            error = ToolError.SAMPLE_NOT_FOUND
        else:
            error = None
            output = MockToolOutput(sample_id=sample_id, status=sample_status)

    return ToolResult(
        request_id=invocation.request_id,
        trace_id=invocation.trace_id,
        tool_id=invocation.tool_id,
        tool_version=invocation.tool_version,
        outcome=ToolOutcome.SUCCEEDED if error is None else ToolOutcome.REJECTED,
        output=output,
        error_code=error,
    )
