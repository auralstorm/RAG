"""Closed contracts for the V1.0 synthetic status lookup."""

from enum import StrEnum
from typing import Literal, Self
from uuid import UUID

from pydantic import model_validator

from app.core.contracts import TraceId, UtcTimestamp, VersionedContract

type MockToolId = Literal["mock.request_status"]
type MockToolVersion = Literal["v1"]
MOCK_PERMISSION = "tool.invoke_mock"


class ToolDefinition(VersionedContract):
    tool_id: MockToolId = "mock.request_status"
    tool_version: MockToolVersion = "v1"
    enabled: bool = False
    permission_code: Literal["tool.invoke_mock"] = MOCK_PERMISSION
    risk_level: Literal["LOW"] = "LOW"
    idempotent: Literal[True] = True
    max_attempts: Literal[1] = 1


class MockRequestId(StrEnum):
    PENDING = "sample-001"
    COMPLETED = "sample-002"
    ABSENT = "sample-003"


class MockStatus(StrEnum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"


class MockToolInput(VersionedContract):
    sample_id: MockRequestId


class ToolInvocation(VersionedContract):
    request_id: UUID
    trace_id: TraceId
    tool_id: MockToolId
    tool_version: MockToolVersion
    arguments: MockToolInput
    deadline_at: UtcTimestamp


class ToolOutcome(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    REJECTED = "REJECTED"


class ToolError(StrEnum):
    ACCESS_DENIED = "ACCESS_DENIED"
    TOOL_UNAVAILABLE = "TOOL_UNAVAILABLE"
    DEADLINE_EXCEEDED = "DEADLINE_EXCEEDED"
    SAMPLE_NOT_FOUND = "SAMPLE_NOT_FOUND"


class MockToolOutput(VersionedContract):
    sample_id: MockRequestId
    status: MockStatus


class ToolResult(VersionedContract):
    request_id: UUID
    trace_id: TraceId
    tool_id: MockToolId
    tool_version: MockToolVersion
    outcome: ToolOutcome
    output: MockToolOutput | None = None
    error_code: ToolError | None = None

    @model_validator(mode="after")
    def require_matching_outcome(self) -> Self:
        succeeded = self.outcome is ToolOutcome.SUCCEEDED
        if succeeded != (self.output is not None) or succeeded == (self.error_code is not None):
            raise ValueError("Tool result requires exactly the payload matching its outcome")
        return self
