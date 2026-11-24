"""Small shared contract kernel, independent of HTTP, vendors and persistence."""

from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict


def utc_timestamp(value: datetime) -> datetime:
    return value.astimezone(UTC)


type UtcTimestamp = Annotated[AwareDatetime, AfterValidator(utc_timestamp)]


class VersionedContract(BaseModel):
    """Immutable versioned facts with explicit fields and safe validation summaries."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    schema_version: Literal["1.0"] = "1.0"
