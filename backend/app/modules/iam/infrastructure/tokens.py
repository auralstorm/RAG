"""Strict platform access JWT codec; provider tokens never become platform authority."""

import hashlib
import hmac
from datetime import UTC, datetime
from uuid import UUID, uuid4

import jwt
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.modules.iam.domain.sessions import AccessClaims, Application, AuthenticationDenied, PlatformSession

PLATFORM_ISSUER = "urn:enterprise-rag:platform"


class JwtPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)
    sub: str
    sid: str
    iid: str
    iss: str
    aud: str
    iat: int
    nbf: int
    exp: int
    jti: str
    version: int = Field(ge=1, le=1)


class JwtSessionTokens:
    def __init__(self, key: str) -> None:
        if len(key.encode()) < 64:
            raise ValueError("A dedicated platform signing key is required")
        self.key = key

    def issue(self, session: PlatformSession, now: datetime, expires_at: datetime) -> str:
        # PyJWT's optional asymmetric-key types are unresolved in the HS256-only install.
        return jwt.encode(  # pyright: ignore[reportUnknownMemberType]
            {
                "sub": str(session.user_id),
                "sid": str(session.id),
                "iid": str(session.identity_id),
                "iss": PLATFORM_ISSUER,
                "aud": f"enterprise-rag:{session.application}",
                "iat": int(now.timestamp()),
                "nbf": int(now.timestamp()),
                "exp": int(expires_at.timestamp()),
                "jti": str(uuid4()),
                "version": 1,
            },
            self.key,
            algorithm="HS256",
            headers={"typ": "at+jwt"},
        )

    def verify(self, token: str, application: Application) -> AccessClaims:
        if not token or len(token) > 4096:
            raise AuthenticationDenied()
        try:
            if jwt.get_unverified_header(token).get("typ") != "at+jwt":
                raise AuthenticationDenied()
            payload = JwtPayload.model_validate(
                jwt.decode(  # pyright: ignore[reportUnknownMemberType]
                    token,
                    self.key,
                    algorithms=["HS256"],
                    issuer=PLATFORM_ISSUER,
                    audience=f"enterprise-rag:{application}",
                    options={"require": list(JwtPayload.model_fields), "strict_aud": True},
                )
            )
            if payload.exp <= payload.iat or payload.nbf != payload.iat:
                raise AuthenticationDenied()
            return AccessClaims(
                UUID(payload.sid),
                UUID(payload.sub),
                UUID(payload.iid),
                application,
                datetime.fromtimestamp(payload.exp, tz=UTC),
            )
        except (jwt.InvalidTokenError, ValidationError, ValueError) as error:
            raise AuthenticationDenied() from error

    def csrf(self, session_id: UUID) -> str:
        return hmac.new(self.key.encode(), b"csrf-v1:" + session_id.bytes, hashlib.sha256).hexdigest()
