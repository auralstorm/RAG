"""Resolve a private collector token without exposing file contents in failures."""

import os
import stat
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


class CollectorCredentials(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True, frozen=True)
    bearer_token: SecretStr = Field(min_length=1, max_length=4096)

    @field_validator("bearer_token")
    @classmethod
    def reject_header_controls(cls, token: SecretStr) -> SecretStr:
        value = token.get_secret_value()
        if not value.isascii() or any(char.isspace() or ord(char) < 33 or ord(char) == 127 for char in value):
            raise ValueError("Collector token must be a single safe header value")
        return token


def read_collector_credentials(path: Path) -> CollectorCredentials:
    """Require a regular, owner-only file; resolve only at provider startup."""
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.geteuid()
                or stat.S_IMODE(metadata.st_mode) & 0o077
                or metadata.st_size > 16384
            ):
                raise ValueError("Collector credential file is not private")
            contents = os.read(descriptor, 16385)
            if len(contents) > 16384:
                raise ValueError("Collector credential file is too large")
            return CollectorCredentials.model_validate_json(contents)
        finally:
            os.close(descriptor)
    except (OSError, ValueError):
        raise ValueError("Collector credentials are unavailable") from None
