"""Provider Secret encryption and safe management DTO boundaries."""

import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
from app.modules.model_gateway.api.schemas import CreateProvider, ProviderAdminView
from app.modules.model_gateway.domain.contracts import SecretReference
from app.modules.model_gateway.domain.registry import EncryptedSecretValue, ProviderUnavailable
from app.modules.model_gateway.infrastructure.provider_secrets import (
    AesGcmProviderSecretCipher,
    ProviderSecretsConfig,
    generate_provider_secrets_config,
    read_provider_secrets_config,
)
from pydantic import SecretStr, ValidationError


def test_provider_secrets_encrypt_and_bind_ciphertext_to_reference() -> None:
    cipher = AesGcmProviderSecretCipher(generate_provider_secrets_config())
    reference = SecretReference(secret_id=uuid4(), version=1, environment="test")
    plaintext = "synthetic-provider-api-key-do-not-log"
    encrypted = cipher.encrypt(reference, SecretStr(plaintext))

    assert plaintext.encode() not in encrypted.ciphertext
    assert plaintext not in repr(encrypted)
    assert cipher.decrypt(reference, encrypted).get_secret_value() == plaintext
    with pytest.raises(ProviderUnavailable):
        cipher.decrypt(reference.model_copy(update={"version": 2}), encrypted)
    tampered = EncryptedSecretValue(
        encrypted.key_version, encrypted.ciphertext[:-1] + bytes([encrypted.ciphertext[-1] ^ 1])
    )
    with pytest.raises(ProviderUnavailable):
        cipher.decrypt(reference, tampered)


def test_provider_secrets_config_requires_private_valid_256_bit_keys(tmp_path: Path) -> None:
    path = tmp_path / "provider-secrets.json"
    payload = generate_provider_secrets_config().private_payload()
    path.write_text(json.dumps(payload))
    os.chmod(path, 0o600)

    assert read_provider_secrets_config(path).active_key_version == "v1"
    os.chmod(path, 0o644)
    with pytest.raises(ValueError, match="unavailable"):
        read_provider_secrets_config(path)
    with pytest.raises(ValidationError):
        ProviderSecretsConfig(active_key_version="missing", keys={"v1": SecretStr("bad")})


def test_provider_management_contract_never_contains_secret_values_or_private_refs() -> None:
    credential = SecretStr("synthetic-provider-api-key")
    payload = CreateProvider.model_validate(
        {
            "expected_policy_version": "rbac-v1:1",
            "confirm": True,
            "name": "测试供应商",
            "provider_type": "openai_compatible",
            "base_url": "https://api.example.com/v1",
            "timeout_seconds": 30,
            "credential": credential,
        }
    )
    assert credential.get_secret_value() not in repr(payload)
    with pytest.raises(ValidationError):
        CreateProvider.model_validate(
            {
                "expected_policy_version": "rbac-v1:1",
                "confirm": True,
                "name": "不安全地址",
                "provider_type": "openai_compatible",
                "base_url": "https://user:password@api.example.com/v1",
                "timeout_seconds": 30,
            }
        )
    with pytest.raises(ValidationError):
        ProviderAdminView.model_validate(
            {
                "schema_version": "1.0",
                "id": str(uuid4()),
                "name": "fake",
                "provider_type": "openai_compatible",
                "config_version": str(uuid4()),
                "status": "ACTIVE",
                "has_credential": True,
                "created_at": "2026-11-26T00:00:00Z",
                "updated_at": "2026-11-26T00:00:00Z",
                "base_url": "https://api.example.com/v1",
                "timeout_seconds": 30,
                "proxy_configured": False,
                "credential_ref": {"secret_id": str(uuid4()), "version": 1, "environment": "test"},
            }
        )


def test_provider_key_rotation_preserves_old_decryption_and_fails_without_old_key() -> None:
    old = generate_provider_secrets_config()
    new = generate_provider_secrets_config()
    reference = SecretReference(secret_id=uuid4(), version=1, environment="test")
    encrypted = AesGcmProviderSecretCipher(old).encrypt(reference, SecretStr("synthetic-key"))
    rotated = ProviderSecretsConfig(active_key_version="v2", keys={"v1": old.keys["v1"], "v2": new.keys["v1"]})
    cipher = AesGcmProviderSecretCipher(rotated)
    assert cipher.decrypt(reference, encrypted).get_secret_value() == "synthetic-key"
    assert cipher.encrypt(reference, SecretStr("synthetic-next-key")).key_version == "v2"
    with pytest.raises(ProviderUnavailable):
        AesGcmProviderSecretCipher(ProviderSecretsConfig(active_key_version="v2", keys={"v2": new.keys["v1"]})).decrypt(
            reference, encrypted
        )
