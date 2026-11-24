"""Small shared contract kernel, independent of HTTP, vendors and persistence."""

from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field


def utc_timestamp(value: datetime) -> datetime:
    return value.astimezone(UTC)


type UtcTimestamp = Annotated[AwareDatetime, AfterValidator(utc_timestamp)]


def nonzero_identifier(value: str) -> str:
    if not value.strip("0"):
        raise ValueError("Correlation identifiers must be nonzero")
    return value


type TraceId = Annotated[str, Field(pattern=r"^[0-9a-f]{32}$"), AfterValidator(nonzero_identifier)]
type SpanId = Annotated[str, Field(pattern=r"^[0-9a-f]{16}$"), AfterValidator(nonzero_identifier)]


class VersionedContract(BaseModel):
    """Immutable versioned facts with explicit fields and safe validation summaries."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    schema_version: Literal["1.0"] = "1.0"
