"""Owner-only encryption keys and authenticated encryption for provider secrets."""

import base64
import binascii
import os
import re
import secrets
import stat
from pathlib import Path
from typing import Self

from app.modules.model_gateway.domain.contracts import SecretReference
from app.modules.model_gateway.domain.registry import EncryptedSecretValue, ProviderUnavailable
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator


class ProviderSecretsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    active_key_version: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
    keys: dict[str, SecretStr] = Field(min_length=1, max_length=10, repr=False)

    @model_validator(mode="after")
    def require_valid_keys(self) -> Self:
        if self.active_key_version not in self.keys:
            raise ValueError("Active provider secret key is missing")
        for version, value in self.keys.items():
            if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", version) is None:
                raise ValueError("Provider secret key version is invalid")
            try:
                decoded = base64.urlsafe_b64decode(
                    value.get_secret_value() + "=" * (-len(value.get_secret_value()) % 4)
                )
            except (ValueError, binascii.Error):
                raise ValueError("Provider secret key encoding is invalid") from None
            if len(decoded) != 32:
                raise ValueError("Provider secret keys must decode to 256 bits")
        return self

    def private_payload(self) -> dict[str, object]:
        """For owner-only files; never log or return this payload over HTTP."""
        return {
            "active_key_version": self.active_key_version,
            "keys": {version: value.get_secret_value() for version, value in self.keys.items()},
        }


def read_provider_secrets_config(path: Path) -> ProviderSecretsConfig:
    """Read a bounded, regular, owner-only key file without following symlinks."""
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.getuid()
                or stat.S_IMODE(metadata.st_mode) & 0o077
                or metadata.st_size > 100_000
            ):
                raise ValueError("Provider secret key file is not private")
            contents = os.read(descriptor, 100_001)
            if len(contents) > 100_000:
                raise ValueError("Provider secret key file is too large")
            return ProviderSecretsConfig.model_validate_json(contents)
        finally:
            os.close(descriptor)
    except (OSError, ValueError):
        raise ValueError("Provider secret key configuration is unavailable") from None


class AesGcmProviderSecretCipher:
    """Encrypt credentials with versioned AES-256-GCM keys and reference-bound AAD."""

    def __init__(self, configuration: ProviderSecretsConfig) -> None:
        self.active_key_version = configuration.active_key_version
        self._keys = {
            version: base64.urlsafe_b64decode(value.get_secret_value() + "=" * (-len(value.get_secret_value()) % 4))
            for version, value in configuration.keys.items()
        }

    @staticmethod
    def _associated_data(reference: SecretReference) -> bytes:
        return (
            f"enterprise-rag:provider-secret:v1:{reference.secret_id}:{reference.version}:{reference.environment}"
        ).encode()

    def encrypt(self, reference: SecretReference, value: SecretStr) -> EncryptedSecretValue:
        key_version = self.active_key_version
        nonce = secrets.token_bytes(12)
        ciphertext = AESGCM(self._keys[key_version]).encrypt(
            nonce,
            value.get_secret_value().encode(),
            self._associated_data(reference),
        )
        return EncryptedSecretValue(key_version, nonce + ciphertext)

    def decrypt(self, reference: SecretReference, value: EncryptedSecretValue) -> SecretStr:
        key = self._keys.get(value.key_version)
        if key is None or len(value.ciphertext) < 28:
            raise ProviderUnavailable() from None
        try:
            plaintext = AESGCM(key).decrypt(
                value.ciphertext[:12], value.ciphertext[12:], self._associated_data(reference)
            )
            return SecretStr(plaintext.decode("utf-8"))
        except (InvalidTag, UnicodeDecodeError, ValueError):
            raise ProviderUnavailable() from None


def generate_provider_secrets_config() -> ProviderSecretsConfig:
    """Generate fresh key material without persisting or displaying it."""
    encoded = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii").rstrip("=")
    return ProviderSecretsConfig(active_key_version="v1", keys={"v1": SecretStr(encoded)})
