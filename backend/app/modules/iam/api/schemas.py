"""Public authentication DTOs never contain provider identities or platform bearer tokens."""

from typing import Literal

from pydantic import Field, SecretStr

from app.api.schemas.common import HttpContract
from app.core.contracts import UtcTimestamp
from app.modules.iam.domain.contracts import User
from app.modules.iam.domain.sessions import Application


class LoginCredentials(HttpContract):
    username: str = Field(min_length=1, max_length=128, pattern=r"\S", repr=False)
    password: SecretStr = Field(min_length=1, max_length=1024)


class AuthConfiguration(HttpContract):
    mode: Literal["local", "unavailable"]


class CsrfResponse(HttpContract):
    csrf_token: str


class AuthSessionResponse(CsrfResponse):
    user: User
    application: Application
    expires_at: UtcTimestamp
