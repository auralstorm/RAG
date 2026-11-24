"""Check identity association and authorization through their module interfaces."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from app.modules.iam.application.identity_resolution import (
    IdentityResolutionCode,
    IdentityResolutionError,
    resolve_external_identity,
    resolve_legacy_subject,
)
from app.modules.iam.domain.contracts import (
    ExternalIdentity,
    IdentityKey,
    IdentityStatus,
    LegacyPrincipalKey,
    LegacyPrincipalType,
    Permission,
    Role,
    SubjectBinding,
    SystemRoleCode,
    User,
    UserStatus,
)
from app.modules.policy.application.authorization import actor_reference, authorize
from app.modules.policy.domain.contracts import (
    AccessContext,
    AccessPurpose,
    AuthorizationRequest,
    AuthorizationSnapshot,
    DecisionEffect,
    DecisionReason,
    KnowledgePermission,
    PolicyDecision,
    ResourceGrant,
    ResourcePrincipalType,
)
from app.modules.tool_gateway.application.mock_invocation import invoke_mock_tool
from app.modules.tool_gateway.domain.contracts import (
    MOCK_PERMISSION,
    MockRequestId,
    MockStatus,
    MockToolInput,
    ToolDefinition,
    ToolError,
    ToolInvocation,
    ToolOutcome,
)
from pydantic import ValidationError

NOW = datetime(2026, 11, 24, 8, tzinfo=UTC)
USER_ID = UUID(int=1)
OTHER_USER_ID = UUID(int=2)
KB_ID = UUID(int=10)
ROLE_ID = UUID(int=20)
GROUP_ID = UUID(int=30)
SOURCE_ID = UUID(int=40)
ACTOR_KEY = b"synthetic-pseudonymization-key-for-contract-tests"


def user(*, user_id: UUID = USER_ID, status: UserStatus = UserStatus.ACTIVE) -> User:
    return User(id=user_id, display_name="Synthetic User", status=status, created_at=NOW, updated_at=NOW)


def identity(*, issuer: str = "https://issuer.example", user_id: UUID = USER_ID) -> ExternalIdentity:
    return ExternalIdentity(
        id=UUID(int=50),
        user_id=user_id,
        provider_key="verified-provider",
        issuer=issuer,
        subject="synthetic-private-subject",
        status=IdentityStatus.ACTIVE,
    )


def context(**updates: object) -> AccessContext:
    payload = {
        "subject_id": USER_ID,
        "identity_id": UUID(int=50),
        "actor_ref": actor_reference(USER_ID, ACTOR_KEY),
        "environment": "test",
        "purpose": AccessPurpose.ADMIN,
        "policy_version": "current-policy-1",
        "issued_at": NOW - timedelta(minutes=1),
        "expires_at": NOW + timedelta(minutes=5),
        **updates,
    }
    return AccessContext.model_validate(payload)


def grant(
    *,
    principal_type: ResourcePrincipalType = ResourcePrincipalType.USER,
    principal_id: UUID = USER_ID,
    permission: KnowledgePermission = KnowledgePermission.READ,
) -> ResourceGrant:
    return ResourceGrant(
        id=UUID(int=60), kb_id=KB_ID, principal_type=principal_type, principal_id=principal_id, permission=permission
    )


def snapshot(**updates: object) -> AuthorizationSnapshot:
    return AuthorizationSnapshot.model_validate(
        {
            "user": user(),
            "identity": identity(),
            "actor_ref": actor_reference(USER_ID, ACTOR_KEY),
            "environment": "test",
            "purpose": AccessPurpose.ADMIN,
            "policy_version": "current-policy-1",
            "role_ids": frozenset({ROLE_ID}),
            "group_ids": frozenset({GROUP_ID}),
            "permission_codes": frozenset({"kb.read", "kb.manage", "user.read"}),
            "resource_grants": (grant(),),
            "subject_bindings": (),
            "observed_at": NOW,
            "expires_at": NOW + timedelta(minutes=1),
            **updates,
        }
    )


def read_request() -> AuthorizationRequest:
    return AuthorizationRequest(permission_code="kb.read", purpose=AccessPurpose.ADMIN, kb_id=KB_ID)


def mock_invocation(sample_id: MockRequestId = MockRequestId.PENDING) -> ToolInvocation:
    return ToolInvocation(
        request_id=UUID(int=70),
        trace_id="a" * 32,
        tool_id="mock.request_status",
        tool_version="v1",
        arguments=MockToolInput(sample_id=sample_id),
        deadline_at=NOW + timedelta(seconds=20),
    )


def test_mock_tool_returns_only_the_selected_fixture_with_request_correlation() -> None:
    invocation = mock_invocation(MockRequestId.COMPLETED)
    current = snapshot(permission_codes={MOCK_PERMISSION})
    result = invoke_mock_tool(invocation, context(), current, ToolDefinition(enabled=True), now=NOW)
    assert result.outcome is ToolOutcome.SUCCEEDED
    assert result.request_id == invocation.request_id and result.trace_id == invocation.trace_id
    assert result.output is not None and result.output.status is MockStatus.COMPLETED
    assert (
        invoke_mock_tool(
            mock_invocation(MockRequestId.ABSENT), context(), current, ToolDefinition(enabled=True), now=NOW
        ).error_code
        is ToolError.SAMPLE_NOT_FOUND
    )


@pytest.mark.parametrize("case", ["missing_context", "revoked", "expired", "chat", "production"])
def test_mock_tool_rejects_invalid_current_identity_and_environment(case: str) -> None:
    current = snapshot(permission_codes={MOCK_PERMISSION})
    actor: AccessContext | None = context()
    if case == "missing_context":
        actor = None
    elif case == "revoked":
        current = snapshot(permission_codes=())
    elif case == "expired":
        actor = context(expires_at=NOW)
    elif case == "chat":
        actor = context(purpose=AccessPurpose.CHAT)
        current = snapshot(permission_codes={MOCK_PERMISSION}, purpose=AccessPurpose.CHAT)
    elif case == "production":
        actor = context(environment="production")
        current = snapshot(permission_codes={MOCK_PERMISSION}, environment="production")
    result = invoke_mock_tool(mock_invocation(), actor, current, ToolDefinition(enabled=True), now=NOW)
    assert result.outcome is ToolOutcome.REJECTED and result.error_code is ToolError.ACCESS_DENIED
    assert result.output is None


def test_mock_tool_defaults_to_disabled_and_enforces_the_original_deadline() -> None:
    invocation = mock_invocation()
    current = snapshot(permission_codes={MOCK_PERMISSION})
    assert invoke_mock_tool(invocation, context(), current, None, now=NOW).error_code is ToolError.TOOL_UNAVAILABLE
    assert (
        invoke_mock_tool(invocation, context(), current, ToolDefinition(), now=NOW).error_code
        is ToolError.TOOL_UNAVAILABLE
    )
    assert (
        invoke_mock_tool(
            invocation, context(), current, ToolDefinition(enabled=True), now=invocation.deadline_at
        ).error_code
        is ToolError.DEADLINE_EXCEEDED
    )


def test_mock_contract_rejects_identity_overrides_and_unsupported_tools() -> None:
    invocation = mock_invocation().model_dump()
    with pytest.raises(ValidationError, match="Extra inputs"):
        ToolInvocation.model_validate(invocation | {"principal_ref": "client-claimed-user"})
    with pytest.raises(ValidationError, match="Extra inputs"):
        ToolInvocation.model_validate(invocation | {"arguments": {"sample_id": "sample-001", "url": "example"}})
    with pytest.raises(ValidationError, match="literal_error"):
        ToolInvocation.model_validate(invocation | {"tool_version": "v2"})


def test_verified_external_identity_uses_exact_provider_issuer_and_subject() -> None:
    first = identity()
    second = identity(issuer="https://another-issuer.example", user_id=OTHER_USER_ID)
    users = (user(), user(user_id=OTHER_USER_ID))
    assert resolve_external_identity(first.key, (first, second), users).id == USER_ID
    assert resolve_external_identity(second.key, (first, second), users).id == OTHER_USER_ID
    for update in (
        {"provider_key": "another-provider"},
        {"issuer": "https://issuer.example/"},
        {"subject": "SYNTHETIC-private-subject"},
    ):
        key = IdentityKey.model_validate({**first.key.model_dump(), **update})
        with pytest.raises(IdentityResolutionError) as rejected:
            resolve_external_identity(key, (first,), users)
        assert rejected.value.code is IdentityResolutionCode.IDENTITY_NOT_FOUND


def test_duplicate_or_disabled_identity_and_missing_user_are_refused_without_private_detail() -> None:
    record = identity()
    with pytest.raises(IdentityResolutionError) as ambiguous:
        resolve_external_identity(record.key, (record, record), (user(),))
    assert ambiguous.value.code is IdentityResolutionCode.IDENTITY_AMBIGUOUS
    assert record.issuer not in str(ambiguous.value) and record.subject not in str(ambiguous.value)
    disabled = ExternalIdentity.model_validate({**record.model_dump(), "status": IdentityStatus.DISABLED})
    with pytest.raises(IdentityResolutionError) as refused:
        resolve_external_identity(record.key, (disabled,), (user(),))
    assert refused.value.code is IdentityResolutionCode.IDENTITY_DISABLED
    with pytest.raises(IdentityResolutionError) as missing:
        resolve_external_identity(record.key, (record,), ())
    assert missing.value.code is IdentityResolutionCode.SUBJECT_NOT_FOUND
    with pytest.raises(IdentityResolutionError) as duplicate:
        resolve_external_identity(record.key, (record,), (user(), user()))
    assert duplicate.value.code is IdentityResolutionCode.SUBJECT_AMBIGUOUS


@pytest.mark.parametrize("status", [value for value in UserStatus if value is not UserStatus.ACTIVE])
def test_inactive_users_cannot_resolve_identity_or_authorize(status: UserStatus) -> None:
    record = identity()
    with pytest.raises(IdentityResolutionError) as rejected:
        resolve_external_identity(record.key, (record,), (user(status=status),))
    assert rejected.value.code is IdentityResolutionCode.SUBJECT_INACTIVE
    decision = authorize(read_request(), context(), snapshot(user=user(status=status)), now=NOW)
    assert decision.reason_code is DecisionReason.INACTIVE_SUBJECT and not decision.allowed


def test_same_legacy_uuid_in_admin_and_employee_sources_maps_to_distinct_users() -> None:
    bindings = (
        SubjectBinding(principal_type=LegacyPrincipalType.ADMIN_USER, principal_id=SOURCE_ID, user_id=USER_ID),
        SubjectBinding(principal_type=LegacyPrincipalType.EMPLOYEE, principal_id=SOURCE_ID, user_id=OTHER_USER_ID),
    )
    users = (user(), user(user_id=OTHER_USER_ID))
    for source_type, expected in (
        (LegacyPrincipalType.ADMIN_USER, USER_ID),
        (LegacyPrincipalType.EMPLOYEE, OTHER_USER_ID),
    ):
        key = LegacyPrincipalKey(principal_type=source_type, principal_id=SOURCE_ID)
        assert resolve_legacy_subject(key, bindings, users).id == expected
    key = LegacyPrincipalKey(principal_type=LegacyPrincipalType.ADMIN_USER, principal_id=USER_ID)
    with pytest.raises(IdentityResolutionError):
        resolve_legacy_subject(key, (), users)
    with pytest.raises(IdentityResolutionError) as duplicate:
        resolve_legacy_subject(
            LegacyPrincipalKey(principal_type=LegacyPrincipalType.ADMIN_USER, principal_id=SOURCE_ID),
            (bindings[0], bindings[0]),
            users,
        )
    assert duplicate.value.code is IdentityResolutionCode.IDENTITY_AMBIGUOUS


@pytest.mark.parametrize("code", list(SystemRoleCode))
def test_system_roles_are_protected_and_cannot_be_relabelled_as_custom(code: SystemRoleCode) -> None:
    role = Role(id=ROLE_ID, code=code.value, name="System Role", is_system=True, protected=True)
    for update in ({"is_system": False}, {"protected": False}, {"code": "CUSTOM_ROLE"}):
        with pytest.raises(ValidationError, match="Reserved system roles"):
            Role.model_validate({**role.model_dump(), **update})


def test_contracts_preserve_permission_semantics_versions_and_private_identity_fields() -> None:
    permission = Permission(id=UUID(int=70), code="kb.read", resource="kb", action="read")
    with pytest.raises(ValidationError, match="resource.action"):
        Permission.model_validate({**permission.model_dump(), "action": "manage"})
    with pytest.raises(ValidationError):
        User.model_validate({**user().model_dump(), "schema_version": "2.0"})
    with pytest.raises(ValidationError):
        User.model_validate({**user().model_dump(), "created_at": "2026-11-24T08:00:00"})
    assert "issuer" not in user().model_dump() and "subject" not in user().model_dump()
    assert identity().issuer not in repr(identity()) and identity().subject not in repr(identity())
    localized = User.model_validate({**user().model_dump(), "created_at": "2026-11-24T16:00:00+08:00"})
    assert localized.created_at == NOW and localized.created_at.tzinfo is UTC


def test_kb_access_binds_current_subject_permission_resource_and_policy_version() -> None:
    decision = authorize(read_request(), context(), snapshot(), now=NOW)
    assert decision.allowed
    assert (decision.subject_id, decision.kb_id, decision.permission_code, decision.policy_version) == (
        USER_ID,
        KB_ID,
        "kb.read",
        "current-policy-1",
    )
    for update, expected in (
        ({"permission_codes": frozenset[str]()}, DecisionReason.PERMISSION_DENIED),
        ({"resource_grants": ()}, DecisionReason.RESOURCE_DENIED),
        ({"resource_grants": (grant(principal_id=OTHER_USER_ID),)}, DecisionReason.RESOURCE_DENIED),
        ({"policy_version": "current-policy-2"}, DecisionReason.POLICY_VERSION_MISMATCH),
    ):
        revoked = authorize(read_request(), context(), snapshot(**update), now=NOW)
        assert not revoked.allowed and revoked.reason_code is expected
    outside = AuthorizationRequest(permission_code="kb.read", purpose=AccessPurpose.ADMIN, kb_id=UUID(int=11))
    assert not authorize(outside, context(), snapshot(), now=NOW).allowed


def test_manage_grant_allows_read_but_read_grant_never_allows_manage() -> None:
    manage = AuthorizationRequest(permission_code="kb.manage", purpose=AccessPurpose.ADMIN, kb_id=KB_ID)
    assert not authorize(manage, context(), snapshot(), now=NOW).allowed
    managed = snapshot(resource_grants=(grant(permission=KnowledgePermission.MANAGE),))
    assert authorize(manage, context(), managed, now=NOW).allowed
    assert authorize(read_request(), context(), managed, now=NOW).allowed


@pytest.mark.parametrize(
    "principal_type,principal_id,membership_field",
    [(ResourcePrincipalType.ROLE, ROLE_ID, "role_ids"), (ResourcePrincipalType.GROUP, GROUP_ID, "group_ids")],
)
def test_role_and_group_grants_follow_current_membership(
    principal_type: ResourcePrincipalType, principal_id: UUID, membership_field: str
) -> None:
    resource = grant(principal_type=principal_type, principal_id=principal_id)
    assert authorize(read_request(), context(), snapshot(resource_grants=(resource,)), now=NOW).allowed
    revoked = snapshot(resource_grants=(resource,), **{membership_field: frozenset[UUID]()})
    assert not authorize(read_request(), context(), revoked, now=NOW).allowed


def test_legacy_acl_needs_the_exact_source_binding_even_when_uuid_equals_user_id() -> None:
    bindings = (
        SubjectBinding(principal_type=LegacyPrincipalType.ADMIN_USER, principal_id=SOURCE_ID, user_id=USER_ID),
        SubjectBinding(principal_type=LegacyPrincipalType.EMPLOYEE, principal_id=SOURCE_ID, user_id=OTHER_USER_ID),
    )
    resource = grant(principal_type=ResourcePrincipalType.ADMIN_USER, principal_id=SOURCE_ID)
    assert authorize(
        read_request(), context(), snapshot(resource_grants=(resource,), subject_bindings=bindings), now=NOW
    ).allowed
    wrong_source = grant(principal_type=ResourcePrincipalType.EMPLOYEE, principal_id=SOURCE_ID)
    assert not authorize(
        read_request(), context(), snapshot(resource_grants=(wrong_source,), subject_bindings=bindings), now=NOW
    ).allowed
    same_uuid = grant(principal_type=ResourcePrincipalType.ADMIN_USER, principal_id=USER_ID)
    assert not authorize(read_request(), context(), snapshot(resource_grants=(same_uuid,)), now=NOW).allowed


@pytest.mark.parametrize(
    "update,reason",
    [
        ({"subject_id": OTHER_USER_ID}, DecisionReason.SUBJECT_MISMATCH),
        ({"identity_id": UUID(int=51)}, DecisionReason.IDENTITY_MISMATCH),
        ({"issued_at": NOW - timedelta(minutes=2), "expires_at": NOW}, DecisionReason.CONTEXT_EXPIRED),
        ({"issued_at": NOW + timedelta(seconds=1)}, DecisionReason.CONTEXT_EXPIRED),
        ({"environment": "production"}, DecisionReason.ENVIRONMENT_MISMATCH),
        ({"purpose": AccessPurpose.CHAT}, DecisionReason.PURPOSE_MISMATCH),
        ({"actor_ref": actor_reference(OTHER_USER_ID, ACTOR_KEY)}, DecisionReason.ACTOR_MISMATCH),
    ],
)
def test_context_failures_cannot_reuse_an_otherwise_authorized_snapshot(
    update: dict[str, object], reason: DecisionReason
) -> None:
    decision = authorize(read_request(), context(**update), snapshot(), now=NOW)
    assert not decision.allowed and decision.reason_code is reason


def test_missing_context_stale_snapshot_and_client_grant_fields_are_rejected() -> None:
    assert authorize(read_request(), None, snapshot(), now=NOW).reason_code is DecisionReason.MISSING_CONTEXT
    assert (
        authorize(read_request(), context(), snapshot(), now=NOW + timedelta(minutes=1)).reason_code
        is DecisionReason.SNAPSHOT_EXPIRED
    )
    for field in ("role_ids", "permission_codes", "kb_ids", "tenant_id"):
        with pytest.raises(ValidationError):
            AccessContext.model_validate({**context().model_dump(), field: "client-claimed-authorization"})
    with pytest.raises(ValueError, match="timezone-aware"):
        authorize(read_request(), context(), snapshot(), now=NOW.replace(tzinfo=None))


def test_chat_and_admin_purpose_do_not_share_management_authority() -> None:
    chat_context = context(purpose=AccessPurpose.CHAT)
    chat_snapshot = snapshot(purpose=AccessPurpose.CHAT)
    read = AuthorizationRequest(permission_code="kb.read", purpose=AccessPurpose.CHAT, kb_id=KB_ID)
    assert authorize(read, chat_context, chat_snapshot, now=NOW).allowed
    administrative = AuthorizationRequest(permission_code="user.read", purpose=AccessPurpose.ADMIN)
    assert (
        authorize(administrative, chat_context, chat_snapshot, now=NOW).reason_code is DecisionReason.PURPOSE_MISMATCH
    )
    assert authorize(administrative, context(), snapshot(), now=NOW).allowed
    for payload in (
        {"permission_code": "kb.manage", "purpose": "chat", "kb_id": KB_ID},
        {"permission_code": "kb.read", "purpose": "admin"},
        {"permission_code": "user.read", "purpose": "admin", "kb_id": KB_ID},
    ):
        with pytest.raises(ValidationError):
            AuthorizationRequest.model_validate(payload)


def test_snapshot_and_decision_invariants_reject_ambiguity_and_false_allow() -> None:
    with pytest.raises(ValidationError, match="different user"):
        snapshot(identity=identity(user_id=OTHER_USER_ID))
    disabled = ExternalIdentity.model_validate({**identity().model_dump(), "status": IdentityStatus.DISABLED})
    revoked = authorize(read_request(), context(), snapshot(identity=disabled), now=NOW)
    assert not revoked.allowed and revoked.reason_code is DecisionReason.INACTIVE_IDENTITY
    binding = SubjectBinding(principal_type=LegacyPrincipalType.ADMIN_USER, principal_id=SOURCE_ID, user_id=USER_ID)
    with pytest.raises(ValidationError, match="ambiguous subject bindings"):
        snapshot(subject_bindings=(binding, binding))
    with pytest.raises(ValidationError, match="duplicate resource grant"):
        snapshot(resource_grants=(grant(), grant()))
    duplicate = ResourceGrant.model_validate({**grant().model_dump(), "id": UUID(int=61)})
    with pytest.raises(ValidationError, match="duplicate resource capabilities"):
        snapshot(resource_grants=(grant(), duplicate))
    decision = authorize(read_request(), context(), snapshot(), now=NOW)
    for update in (
        {"subject_id": None},
        {"reason_code": DecisionReason.RESOURCE_DENIED},
        {"effect": DecisionEffect.DENY},
        {"schema_version": "2.0"},
    ):
        with pytest.raises(ValidationError):
            PolicyDecision.model_validate({**decision.model_dump(), **update})


def test_actor_reference_is_keyed_pseudonymous_and_requires_a_server_key() -> None:
    reference = actor_reference(USER_ID, ACTOR_KEY)
    assert reference == actor_reference(USER_ID, ACTOR_KEY)
    assert reference != actor_reference(OTHER_USER_ID, ACTOR_KEY)
    assert reference != actor_reference(USER_ID, b"another-server-key-for-contract-tests")
    assert len(reference) == 70 and USER_ID.hex not in reference
    with pytest.raises(ValueError, match="server key"):
        actor_reference(USER_ID, b"")
