"""Platform session and policy keys independent of any enterprise identity source."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.modules.iam.infrastructure.private_config import read_private_bytes


class PlatformAuthConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    signing_key: SecretStr = Field(min_length=64)
    pseudonymization_key: SecretStr | None = Field(default=None, min_length=64)

    def private_payload(self) -> dict[str, str]:
        """For owner-only files; never log or return this payload over HTTP."""
        payload = {"signing_key": self.signing_key.get_secret_value()}
        if self.pseudonymization_key is not None:
            payload["pseudonymization_key"] = self.pseudonymization_key.get_secret_value()
        return payload


def read_platform_config(path: Path) -> PlatformAuthConfig:
    return PlatformAuthConfig.model_validate_json(read_private_bytes(path))
