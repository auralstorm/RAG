"""Negative JWT cases are rejected before any database or authorization facts are consulted."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import jwt
import pytest
from app.core.config import Settings
from app.modules.iam.domain.sessions import Application, AuthenticationDenied, PlatformSession
from app.modules.iam.infrastructure.local_identity import read_private_config
from app.modules.iam.infrastructure.tokens import JwtSessionTokens
from pydantic import ValidationError

KEY = "synthetic-test-signing-key-" * 4
NOW = datetime.now(UTC)
SESSION = PlatformSession(uuid4(), uuid4(), uuid4(), "chat", NOW + timedelta(hours=1))


def test_access_token_is_purpose_bound_and_requires_valid_signature() -> None:
    codec = JwtSessionTokens(KEY)
    token = codec.issue(SESSION, NOW, NOW + timedelta(minutes=10))
    assert codec.verify(token, "chat").session_id == SESSION.id
    attempts: tuple[tuple[JwtSessionTokens, Application], ...] = (
        (codec, "admin"),
        (JwtSessionTokens("other-test-key-" * 8), "chat"),
    )
    for verifier, audience in attempts:
        with pytest.raises(AuthenticationDenied):
            verifier.verify(token, audience)


@pytest.mark.parametrize(
    "change",
    [
        {"exp": int(NOW.timestamp()) - 10},
        {"iss": "untrusted-issuer"},
        {"aud": "untrusted-audience"},
        {"nbf": int(NOW.timestamp()) + 3600},
        {"iat": int(NOW.timestamp()) + 3600},
        {"sub": "not-a-uuid"},
        {"sid": "not-a-uuid"},
        {"version": 2},
        {"exp": True},
        {"role": "SUPER_ADMIN"},
    ],
)
def test_invalid_claims_never_create_a_platform_session(change: dict[str, object]) -> None:
    codec = JwtSessionTokens(KEY)
    original = codec.issue(SESSION, NOW, NOW + timedelta(minutes=10))
    payload = jwt.decode(  # pyright: ignore[reportUnknownMemberType]
        original, KEY, algorithms=["HS256"], audience="enterprise-rag:chat", options={"verify_signature": False}
    )
    payload.update(change)
    token = jwt.encode(payload, KEY, algorithm="HS256", headers={"typ": "at+jwt"})  # pyright: ignore[reportUnknownMemberType]
    with pytest.raises(AuthenticationDenied):
        codec.verify(token, "chat")


def test_missing_claims_wrong_type_and_unsigned_tokens_are_denied() -> None:
    codec = JwtSessionTokens(KEY)
    for token in (
        jwt.encode({"sub": str(SESSION.user_id)}, KEY, algorithm="HS256", headers={"typ": "at+jwt"}),  # pyright: ignore[reportUnknownMemberType]
        jwt.encode({"sub": str(SESSION.user_id)}, "", algorithm="none", headers={"typ": "at+jwt"}),  # pyright: ignore[reportUnknownMemberType]
        "malformed",
        "x" * 4097,
    ):
        with pytest.raises(AuthenticationDenied):
            codec.verify(token, "chat")


def test_local_source_is_disabled_in_production_and_refuses_shared_secret_files(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="not available in production"):
        Settings(environment="production", local_identity_config_ref=tmp_path / "local.json")
    path = tmp_path / "shared.json"
    path.write_text("{}")
    path.chmod(0o644)
    with pytest.raises(ValueError, match="private regular file"):
        read_private_config(path)
