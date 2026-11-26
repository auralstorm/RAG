"""Private configuration separation preserves keys and fails closed on unsafe input."""

import json
import os
from pathlib import Path

import pytest
from app.core.authentication import create_iam_services
from app.core.config import Settings
from app.modules.iam.domain.identity_providers import AuthorizationCodeCredentials, PasswordCredentials
from app.modules.iam.infrastructure.local_identity import read_private_config
from app.modules.iam.infrastructure.platform_config import read_platform_config
from pydantic import ValidationError

from scripts.separate_auth_config import separate


def local_file(path: Path, *, include_keys: bool = True) -> Path:
    payload = {
        **(
            {"signing_key": "synthetic-signing-" * 6, "pseudonymization_key": "synthetic-policy-" * 6}
            if include_keys
            else {}
        ),
        "accounts": [{"username": "fixture", "subject": "fixture", "salt": "0" * 32, "password_hash": "0" * 64}],
    }
    path.write_text(json.dumps(payload))
    path.chmod(0o600)
    return path


def test_separation_preserves_both_keys_and_source_and_refuses_overwrite(tmp_path: Path) -> None:
    source = local_file(tmp_path / "local.json")
    original = source.read_bytes()
    destination = tmp_path / "platform.json"
    separate(source, destination)
    legacy, platform = read_private_config(source), read_platform_config(destination)
    assert platform.signing_key == legacy.signing_key
    assert platform.pseudonymization_key == legacy.pseudonymization_key
    assert source.read_bytes() == original
    assert destination.stat().st_mode & 0o777 == 0o600
    assert "accounts" not in destination.read_text()
    with pytest.raises(FileExistsError):
        separate(source, destination)
    assert read_platform_config(destination) == platform


def test_explicit_platform_reference_is_authoritative_and_never_falls_back(tmp_path: Path) -> None:
    source = local_file(tmp_path / "local.json")
    destination = tmp_path / "platform.json"
    destination.write_text('{"signing_key":"too-short"}')
    destination.chmod(0o600)
    with pytest.raises(ValidationError):
        create_iam_services(Settings(local_identity_config_ref=source, auth_platform_config_ref=destination))
    destination.unlink()
    with pytest.raises(FileNotFoundError):
        create_iam_services(Settings(local_identity_config_ref=source, auth_platform_config_ref=destination))


def test_accounts_only_source_requires_explicit_platform_keys(tmp_path: Path) -> None:
    source = local_file(tmp_path / "local.json", include_keys=False)
    assert read_private_config(source).signing_key is None
    with pytest.raises(ValueError, match="private platform"):
        create_iam_services(Settings(local_identity_config_ref=source))


@pytest.mark.parametrize("kind", ["shared", "symlink", "fifo", "directory", "oversized"])
def test_both_config_readers_refuse_unsafe_files_without_blocking(tmp_path: Path, kind: str) -> None:
    source = local_file(tmp_path / "source.json")
    unsafe = tmp_path / "unsafe"
    match kind:
        case "shared":
            unsafe.write_bytes(source.read_bytes())
            unsafe.chmod(0o644)
        case "symlink":
            unsafe.symlink_to(source)
        case "fifo":
            os.mkfifo(unsafe, 0o600)
        case "directory":
            unsafe.mkdir(mode=0o700)
        case "oversized":
            unsafe.write_bytes(b" " * 100_001)
            unsafe.chmod(0o600)
        case _:
            raise AssertionError("Unknown unsafe-file fixture")
    for reader in (read_platform_config, read_private_config):
        with pytest.raises((ValueError, OSError)):
            reader(unsafe)


def test_credential_objects_do_not_repr_passwords_or_authorization_values() -> None:
    password = PasswordCredentials("private-user", "private-password")
    code = AuthorizationCodeCredentials(
        "private-code", "https://app.example/callback", "private-nonce", "private-proof"
    )
    assert "private-" not in repr(password) + repr(code)
