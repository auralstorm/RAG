"""Resolve verified identity associations without guessing from names, email or UUID equality."""

from collections.abc import Iterable
from enum import StrEnum
from uuid import UUID

from app.modules.iam.domain.contracts import (
    ExternalIdentity,
    IdentityKey,
    IdentityStatus,
    LegacyPrincipalKey,
    SubjectBinding,
    User,
)


class IdentityResolutionCode(StrEnum):
    IDENTITY_NOT_FOUND = "IDENTITY_NOT_FOUND"
    IDENTITY_AMBIGUOUS = "IDENTITY_AMBIGUOUS"
    IDENTITY_DISABLED = "IDENTITY_DISABLED"
    SUBJECT_NOT_FOUND = "SUBJECT_NOT_FOUND"
    SUBJECT_AMBIGUOUS = "SUBJECT_AMBIGUOUS"
    SUBJECT_INACTIVE = "SUBJECT_INACTIVE"


class IdentityResolutionError(PermissionError):
    """A stable refusal code without external identifiers or personal data."""

    def __init__(self, code: IdentityResolutionCode) -> None:
        super().__init__(code.value)
        self.code = code


def _active_user(user_id: UUID, users: Iterable[User]) -> User:
    matches = [user for user in users if user.id == user_id]
    if not matches:
        raise IdentityResolutionError(IdentityResolutionCode.SUBJECT_NOT_FOUND)
    if len(matches) != 1:
        raise IdentityResolutionError(IdentityResolutionCode.SUBJECT_AMBIGUOUS)
    if not matches[0].active:
        raise IdentityResolutionError(IdentityResolutionCode.SUBJECT_INACTIVE)
    return matches[0]


def resolve_external_identity(key: IdentityKey, identities: Iterable[ExternalIdentity], users: Iterable[User]) -> User:
    """Resolve after provider verification; the caller owns current records and authentication.

    Match the provider, exact issuer and exact subject. Missing, duplicate, disabled or
    inactive associations fail closed. This function creates neither users nor sessions.
    """
    matches = [identity for identity in identities if identity.key == key]
    if not matches:
        raise IdentityResolutionError(IdentityResolutionCode.IDENTITY_NOT_FOUND)
    if len(matches) != 1:
        raise IdentityResolutionError(IdentityResolutionCode.IDENTITY_AMBIGUOUS)
    if matches[0].status is not IdentityStatus.ACTIVE:
        raise IdentityResolutionError(IdentityResolutionCode.IDENTITY_DISABLED)
    return _active_user(matches[0].user_id, users)


def resolve_legacy_subject(key: LegacyPrincipalKey, bindings: Iterable[SubjectBinding], users: Iterable[User]) -> User:
    """Resolve only an explicit type-and-ID association; no same-UUID fallback exists."""
    matches = [
        binding
        for binding in bindings
        if (binding.principal_type, binding.principal_id) == (key.principal_type, key.principal_id)
    ]
    if not matches:
        raise IdentityResolutionError(IdentityResolutionCode.IDENTITY_NOT_FOUND)
    if len(matches) != 1:
        raise IdentityResolutionError(IdentityResolutionCode.IDENTITY_AMBIGUOUS)
    return _active_user(matches[0].user_id, users)
