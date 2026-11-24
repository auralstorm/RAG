"""Common HTTP contracts; provider objects and rejected inputs never enter errors."""

from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 20

type PageNumber = Annotated[int, Field(ge=1)]
type PageSize = Annotated[int, Field(ge=1, le=MAX_PAGE_SIZE)]


class HttpContract(BaseModel):
    """Reject unknown fields and keep validation diagnostics free of input values."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class LivenessResponse(HttpContract):
    """Process liveness does not claim that external dependencies are available."""

    status: Literal["ok"] = "ok"


class ApiError(HttpContract):
    """Public error summary; callers supply only explicitly safe details."""

    code: str = Field(min_length=1, max_length=128, pattern=r"^[A-Z][A-Z0-9_]*$")
    message: str = Field(min_length=1, max_length=512)
    request_id: UUID
    retryable: bool
    details: dict[str, JsonValue] = Field(default_factory=dict)


class ApiErrorEnvelope(HttpContract):
    """The V1 API's stable error response, independent of the failing implementation."""

    error: ApiError


class PaginationQuery(HttpContract):
    """Bound page selection at the HTTP boundary; the limit is not a capacity SLO."""

    page: PageNumber = 1
    page_size: PageSize = DEFAULT_PAGE_SIZE


class PageResponse[ItemT](HttpContract):
    """A page of authorized resources; totals and items describe the same query."""

    items: list[ItemT]
    total: int = Field(ge=0)
    page: PageNumber
    page_size: PageSize

    @model_validator(mode="after")
    def require_consistent_counts(self) -> Self:
        if len(self.items) > self.page_size or len(self.items) > self.total:
            raise ValueError("Page item count exceeds page size or total")
        return self
