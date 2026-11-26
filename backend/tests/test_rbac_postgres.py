"""Exercise live role/ACL enforcement through HTTP and the unified authorization service."""

import asyncio
import json
import secrets
from collections.abc import Iterator, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from app.adapters.postgres import postgres_conninfo
from app.core.authentication import create_iam_services
from app.main import create_app
from app.modules.iam.domain.rbac import PERMISSION_CODES, SYSTEM_ROLE_PERMISSIONS, AuthorizationDenied, RbacConflict
from app.modules.iam.infrastructure.local_identity import LOCAL_ISSUER, password_hash, read_private_config
from fastapi.testclient import TestClient
from psycopg import Connection
from psycopg.errors import CheckViolation, ForeignKeyViolation
from tests.test_auth_postgres import AuthFixture
from tests.test_auth_postgres import auth as auth
from tests.test_auth_postgres import postgres_settings as postgres_settings

from scripts.bootstrap_rbac import appoint_first_admin

pytestmark = pytest.mark.infrastructure
ORIGIN = "http://127.0.0.1:5174"
PASSWORD = "synthetic-rbac-password-1234"


@dataclass
class RbacFixture:
    auth: AuthFixture
    clients: dict[str, TestClient]
    users: dict[str, UUID]
    roles: dict[str, UUID]
    csrf: dict[str, str]
    kb_a: UUID
    kb_b: UUID

    @property
    def admin(self) -> TestClient:
        return self.clients["SUPER_ADMIN"]

    def version(self) -> str:
        return self.admin.get("/api/v1/authorization/admin/me").json()["policy_version"]

    def mutate(
        self,
        method: str,
        path: str,
        payload: Mapping[str, object],
        *,
        actor: str = "SUPER_ADMIN",
        version: str | None = None,
    ):
        return self.clients[actor].request(
            method,
            path,
            headers={"Origin": ORIGIN, "X-CSRF-Token": self.csrf[actor]},
            json={"expected_policy_version": version or self.version(), "confirm": True, **payload},
        )


@pytest.fixture
def rbac(auth: AuthFixture) -> Iterator[RbacFixture]:
    path = auth.settings.local_identity_config_ref
    assert path is not None
    configuration = read_private_config(path)
    assert configuration.signing_key is not None
    accounts = [item.model_dump() for item in configuration.accounts]
    users = {"SUPER_ADMIN": auth.user_id}
    identities: dict[str, UUID] = {}
    kb_a, kb_b = uuid4(), uuid4()
    with Connection.connect(postgres_conninfo(auth.settings)) as connection:
        roles = {
            str(code): UUID(str(role_id))
            for code, role_id in connection.execute("SELECT code,id FROM roles").fetchall()
        }
        connection.execute(
            "INSERT INTO user_roles(user_id,role_id) VALUES(%s,%s)", (auth.user_id, roles["SUPER_ADMIN"])
        )
        for code in ("KB_ADMIN", "AUDIT_READONLY", "EMPLOYEE"):
            user_id, identity_id = uuid4(), uuid4()
            users[code] = user_id
            identities[code] = identity_id
            salt = secrets.token_hex(16)
            accounts.append(
                {
                    "username": code,
                    "subject": str(identity_id),
                    "salt": salt,
                    "password_hash": password_hash(PASSWORD, salt),
                }
            )
            connection.execute("INSERT INTO users(id,display_name,status) VALUES(%s,%s,'ACTIVE')", (user_id, code))
            connection.execute(
                "INSERT INTO identities(id,user_id,provider_key,issuer,subject,status) VALUES(%s,%s,'local',%s,%s,'ACTIVE')",
                (identity_id, user_id, LOCAL_ISSUER, str(identity_id)),
            )
            for purpose in ("chat", "admin"):
                connection.execute(
                    "INSERT INTO identity_applications(identity_id,application) VALUES(%s,%s)", (identity_id, purpose)
                )
            if code != "EMPLOYEE":
                connection.execute("INSERT INTO user_roles(user_id,role_id) VALUES(%s,%s)", (user_id, roles[code]))
        for kb in (kb_a, kb_b):
            for role, permission in (("SUPER_ADMIN", "MANAGE"), ("AUDIT_READONLY", "READ")):
                connection.execute(
                    "INSERT INTO kb_resource_grants(id,kb_id,purpose,principal_type,principal_id,permission) VALUES(%s,%s,'admin','ROLE',%s,%s)",
                    (uuid4(), kb, roles[role], permission),
                )
        for purpose, user_id in (("admin", users["KB_ADMIN"]), ("chat", users["EMPLOYEE"])):
            connection.execute(
                "INSERT INTO kb_resource_grants(id,kb_id,purpose,principal_type,principal_id,permission) VALUES(%s,%s,%s,'USER',%s,'READ')",
                (uuid4(), kb_a, purpose, user_id),
            )
    path.write_text(
        json.dumps(
            {
                "signing_key": configuration.signing_key.get_secret_value(),
                "pseudonymization_key": configuration.pseudonymization_key.get_secret_value()
                if configuration.pseudonymization_key
                else secrets.token_hex(48),
                "accounts": accounts,
            }
        )
    )
    clients = {"SUPER_ADMIN": auth.client}
    csrf: dict[str, str] = {}
    try:
        result = auth.login("admin")
        assert result.status_code == 200, result.text
        csrf["SUPER_ADMIN"] = result.json()["csrf_token"]
        for code in ("KB_ADMIN", "AUDIT_READONLY", "EMPLOYEE"):
            client = TestClient(create_app(auth.settings), client=(code, 50000))
            client.__enter__()
            clients[code] = client
            result = client.post(
                "/api/v1/auth/admin/login", headers={"Origin": ORIGIN}, json={"username": code, "password": PASSWORD}
            )
            assert result.status_code == 200, result.text
            csrf[code] = result.json()["csrf_token"]
        yield RbacFixture(auth, clients, users, roles, csrf, kb_a, kb_b)
    finally:
        for code, client in clients.items():
            if code != "SUPER_ADMIN":
                client.__exit__(None, None, None)


def test_current_fixed_matrix_and_negative_management_api(rbac: RbacFixture) -> None:
    for code in SYSTEM_ROLE_PERMISSIONS:
        client = rbac.clients[code]
        response = client.get("/api/v1/authorization/admin/me")
        assert response.status_code == 200, response.text
        assert response.json()["subject_id"] == str(rbac.users[code])
        assert frozenset(response.json()["permission_codes"]) == SYSTEM_ROLE_PERMISSIONS[code]
        assert "issuer" not in response.text and "actor_" not in response.text
        assert client.get("/api/v1/admin/roles").status_code == (403 if code == "KB_ADMIN" else 200)
    for code in ("KB_ADMIN", "AUDIT_READONLY", "EMPLOYEE"):
        denied = rbac.mutate(
            "POST",
            "/api/v1/admin/roles",
            {"code": "FORGED", "name": "secret-role-name", "permission_codes": ["role.manage"]},
            actor=code,
        )
        assert denied.status_code == 403, denied.text
        assert "secret-role-name" not in denied.text


def test_unified_enforcer_covers_every_fixed_operation(rbac: RbacFixture) -> None:
    service = create_iam_services(rbac.auth.settings).rbac
    assert service is not None
    for role in SYSTEM_ROLE_PERMISSIONS:
        token = rbac.clients[role].cookies["er_admin_access"]
        for permission in PERMISSION_CODES:
            kb_id = rbac.kb_a if permission in {"kb.read", "kb.manage"} else None
            if permission in SYSTEM_ROLE_PERMISSIONS[role]:
                asyncio.run(service.require("admin", token, permission, kb_id))
            else:
                with pytest.raises(AuthorizationDenied):
                    asyncio.run(service.require("admin", token, permission, kb_id))


def test_kb_scope_is_filtered_and_admin_roles_do_not_grant_chat_access(rbac: RbacFixture) -> None:
    for role, expected in (
        ("SUPER_ADMIN", {str(rbac.kb_a), str(rbac.kb_b)}),
        ("AUDIT_READONLY", {str(rbac.kb_a), str(rbac.kb_b)}),
        ("KB_ADMIN", {str(rbac.kb_a)}),
        ("EMPLOYEE", set[str]()),
    ):
        response = rbac.clients[role].get("/api/v1/authorization/admin/knowledge-bases")
        assert {item["kb_id"] for item in response.json()["items"]} == expected
    client = rbac.clients["KB_ADMIN"]
    assert client.get(f"/api/v1/authorization/admin/knowledge-bases/{rbac.kb_b}").status_code == 403
    assert client.get(f"/api/v1/authorization/admin/knowledge-bases/{rbac.kb_a}").json()["can_manage"] is False
    result = rbac.auth.login("chat")
    assert result.status_code == 200
    assert rbac.admin.get("/api/v1/authorization/chat/knowledge-bases").json()["items"] == []


def test_custom_role_cannot_escalate_and_permission_edits_take_effect_immediately(rbac: RbacFixture) -> None:
    for code in ("role.manage", "user.manage", "acl.manage", "provider.manage", "trace.reveal_identity"):
        assert (
            rbac.mutate(
                "POST", "/api/v1/admin/roles", {"code": "ESCALATE", "name": "forbidden", "permission_codes": [code]}
            ).status_code
            == 403
        )
    created = rbac.mutate(
        "POST",
        "/api/v1/admin/roles",
        {"code": "CUSTOM_READER", "name": "自定义只读", "permission_codes": ["role.read"]},
    )
    assert created.status_code == 201, created.text
    role_id = created.json()["role"]["id"]
    assert (
        rbac.mutate("PUT", f"/api/v1/admin/users/{rbac.users['EMPLOYEE']}/roles", {"role_ids": [role_id]}).status_code
        == 204
    )
    employee = rbac.clients["EMPLOYEE"]
    assert employee.get("/api/v1/admin/roles").status_code == 200
    assert (
        rbac.mutate("PATCH", f"/api/v1/admin/roles/{role_id}", {"name": "撤销读取", "permission_codes": []}).status_code
        == 200
    )
    assert employee.get("/api/v1/admin/roles").status_code == 403
    assert rbac.mutate("DELETE", f"/api/v1/admin/roles/{role_id}", {}).status_code == 204
    with Connection.connect(postgres_conninfo(rbac.auth.settings)) as connection:
        permission_row = connection.execute("SELECT id FROM permissions WHERE code='role.read'").fetchone()
        assert permission_row is not None
        permission_id = str(permission_row[0])
        summaries = connection.execute(
            "SELECT before_snapshot,after_snapshot FROM audit_events WHERE object_id=%s AND action='iam.permission_change' AND result='SUCCEEDED'",
            (role_id,),
        ).fetchall()
        assert len(summaries) == 1
        assert summaries[0][0]["permission_ids"] == [permission_id]
        assert summaries[0][1]["permission_ids"] == []


def test_fixed_roles_and_last_active_administrator_are_protected(rbac: RbacFixture) -> None:
    for role_id in rbac.roles.values():
        assert (
            rbac.mutate(
                "PATCH", f"/api/v1/admin/roles/{role_id}", {"name": "tampered", "permission_codes": []}
            ).status_code
            == 409
        )
        assert rbac.mutate("DELETE", f"/api/v1/admin/roles/{role_id}", {}).status_code == 409
    response = rbac.mutate("PUT", f"/api/v1/admin/users/{rbac.users['SUPER_ADMIN']}/roles", {"role_ids": []})
    assert response.status_code == 409
    assert rbac.admin.get("/api/v1/admin/roles").status_code == 200


def test_stale_version_csrf_confirmation_and_principal_forgery_are_rejected(rbac: RbacFixture) -> None:
    version = rbac.version()
    payload = {"code": "READER", "name": "reader", "permission_codes": ["role.read"]}
    assert rbac.mutate("POST", "/api/v1/admin/roles", payload).status_code == 201
    assert rbac.mutate("POST", "/api/v1/admin/roles", {**payload, "code": "STALE"}, version=version).status_code == 409
    response = rbac.admin.post(
        "/api/v1/admin/roles",
        headers={"Origin": ORIGIN},
        json={"expected_policy_version": rbac.version(), "confirm": True, **payload},
    )
    assert response.status_code == 403
    assert rbac.mutate("POST", "/api/v1/admin/roles", {**payload, "confirm": False}).status_code == 422
    assert (
        rbac.mutate(
            "POST", "/api/v1/admin/roles", {**payload, "subject_id": str(rbac.users["SUPER_ADMIN"])}
        ).status_code
        == 422
    )


def test_resource_revocation_and_transactional_audit(rbac: RbacFixture) -> None:
    client = rbac.clients["KB_ADMIN"]
    assert client.get(f"/api/v1/authorization/admin/knowledge-bases/{rbac.kb_b}").status_code == 403
    grant = {
        "application": "admin",
        "principal_type": "USER",
        "principal_id": str(rbac.users["KB_ADMIN"]),
        "permission": "READ",
    }
    assert rbac.mutate("PUT", f"/api/v1/admin/kb-access/{rbac.kb_b}", grant).status_code == 204
    assert client.get(f"/api/v1/authorization/admin/knowledge-bases/{rbac.kb_b}").status_code == 200
    listed = rbac.admin.get(f"/api/v1/admin/kb-access/{rbac.kb_b}").json()["items"]
    grant_id = next(
        item["grant"]["id"] for item in listed if item["grant"]["principal_id"] == str(rbac.users["KB_ADMIN"])
    )
    assert rbac.mutate("DELETE", f"/api/v1/admin/kb-access/{rbac.kb_b}/{grant_id}", {}).status_code == 204
    assert client.get(f"/api/v1/authorization/admin/knowledge-bases/{rbac.kb_b}").status_code == 403
    with Connection.connect(postgres_conninfo(rbac.auth.settings)) as connection:
        assert connection.execute(
            "SELECT count(*) FROM audit_events WHERE action='iam.permission_change' AND result='SUCCEEDED'"
        ).fetchone() == (2,)
        audit_row = connection.execute(
            "SELECT after_snapshot FROM audit_events WHERE action='iam.permission_change' AND result='SUCCEEDED' AND after_snapshot->>'enabled'='true'"
        ).fetchone()
        assert audit_row is not None
        after = audit_row[0]
        assert after["resource_purpose"] == "admin"
        assert after["resource_grant"]["principal_id"] == str(rbac.users["KB_ADMIN"])
        assert after["resource_grant"]["permission"] == "READ"


def test_audit_failure_rolls_back_role_creation(rbac: RbacFixture) -> None:
    with Connection.connect(postgres_conninfo(rbac.auth.settings)) as connection:
        connection.execute(
            "CREATE FUNCTION refuse_rbac_audit() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.action<>'iam.login' THEN RAISE EXCEPTION 'audit unavailable'; END IF; RETURN NEW; END $$"
        )
        connection.execute(
            "CREATE TRIGGER refuse_rbac_audit BEFORE INSERT ON audit_events FOR EACH ROW EXECUTE FUNCTION refuse_rbac_audit()"
        )
    response = rbac.mutate(
        "POST", "/api/v1/admin/roles", {"code": "ROLLBACK_PROBE", "name": "rollback", "permission_codes": []}
    )
    assert response.status_code == 503, response.text
    with Connection.connect(postgres_conninfo(rbac.auth.settings)) as connection:
        assert connection.execute("SELECT count(*) FROM roles WHERE code='ROLLBACK_PROBE'").fetchone() == (0,)


def test_bootstrap_requires_an_explicit_active_user_and_is_single_use(auth: AuthFixture) -> None:
    asyncio.run(appoint_first_admin(auth.settings, auth.user_id))
    with pytest.raises(RbacConflict):
        asyncio.run(appoint_first_admin(auth.settings, auth.user_id))


def test_concurrent_stale_mutations_cannot_both_commit(rbac: RbacFixture) -> None:
    version = rbac.version()

    def create(number: int) -> int:
        with TestClient(create_app(rbac.auth.settings)) as client:
            client.cookies.update(dict(rbac.admin.cookies))
            response = client.post(
                "/api/v1/admin/roles",
                headers={"Origin": ORIGIN, "X-CSRF-Token": rbac.csrf["SUPER_ADMIN"]},
                json={
                    "expected_policy_version": version,
                    "confirm": True,
                    "code": f"CONCURRENT_{number}",
                    "name": "concurrent",
                    "permission_codes": [],
                },
            )
            return response.status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(create, range(2))) == [201, 409]


def test_direct_database_constraints_protect_fixed_matrix_and_acl_references(rbac: RbacFixture) -> None:
    with Connection.connect(postgres_conninfo(rbac.auth.settings)) as connection:
        for statement in (
            "DELETE FROM role_permissions WHERE role_id=(SELECT id FROM roles WHERE code='SUPER_ADMIN')",
            "UPDATE permissions SET code='forged.manage',resource='forged',action='manage' WHERE code='role.read'",
            "TRUNCATE role_permissions",
        ):
            with pytest.raises(CheckViolation), connection.transaction():
                connection.execute(statement)
        with pytest.raises(ForeignKeyViolation), connection.transaction():
            connection.execute(
                "INSERT INTO kb_resource_grants(id,kb_id,purpose,principal_type,principal_id,permission) VALUES(%s,%s,'admin','USER',%s,'READ')",
                (uuid4(), rbac.kb_a, uuid4()),
            )


def test_existing_jwt_loses_authority_after_role_revocation(rbac: RbacFixture) -> None:
    client = rbac.clients["AUDIT_READONLY"]
    assert client.get("/api/v1/admin/roles").status_code == 200
    assert (
        rbac.mutate("PUT", f"/api/v1/admin/users/{rbac.users['AUDIT_READONLY']}/roles", {"role_ids": []}).status_code
        == 204
    )
    assert (
        client.get(
            "/api/v1/admin/roles", headers={"X-Roles": "SUPER_ADMIN", "X-User-ID": str(rbac.users["SUPER_ADMIN"])}
        ).status_code
        == 403
    )
    response = client.get("/api/v1/authorization/admin/me")
    assert response.status_code == 200 and response.json()["permission_codes"] == []


def test_acl_read_requires_resource_access_and_global_provisioning_is_explicit(rbac: RbacFixture) -> None:
    unknown = uuid4()
    for actor in ("SUPER_ADMIN", "AUDIT_READONLY"):
        assert rbac.clients[actor].get(f"/api/v1/admin/kb-access/{unknown}").status_code == 403
    # Only the nondelegable security-management capability can establish a first ACL.
    assert rbac.admin.get(f"/api/v1/authorization/admin/knowledge-bases/{unknown}").status_code == 403
    assert (
        rbac.mutate(
            "PUT",
            f"/api/v1/admin/kb-access/{unknown}",
            {
                "application": "admin",
                "principal_type": "USER",
                "principal_id": str(rbac.users["SUPER_ADMIN"]),
                "permission": "MANAGE",
            },
        ).status_code
        == 204
    )
    assert rbac.admin.get(f"/api/v1/admin/kb-access/{unknown}").status_code == 200
    assert rbac.clients["AUDIT_READONLY"].get(f"/api/v1/admin/kb-access/{unknown}").status_code == 403


def test_legacy_principal_type_isolation_and_chat_grant_revocation(rbac: RbacFixture) -> None:
    source_id = uuid4()
    with Connection.connect(postgres_conninfo(rbac.auth.settings)) as connection:
        for kind, actor in (("EMPLOYEE", "KB_ADMIN"), ("ADMIN_USER", "AUDIT_READONLY")):
            connection.execute(
                "INSERT INTO subject_bindings(principal_type,principal_id,user_id) VALUES(%s,%s,%s)",
                (kind, source_id, rbac.users[actor]),
            )
    assert (
        rbac.mutate(
            "PUT",
            f"/api/v1/admin/kb-access/{rbac.kb_b}",
            {
                "application": "chat",
                "principal_type": "EMPLOYEE",
                "principal_id": str(source_id),
                "permission": "READ",
            },
        ).status_code
        == 204
    )
    for actor, status in (("KB_ADMIN", 200), ("AUDIT_READONLY", 403)):
        client = rbac.clients[actor]
        assert (
            client.post(
                "/api/v1/auth/chat/login",
                headers={"Origin": "http://127.0.0.1:5173"},
                json={"username": actor, "password": PASSWORD},
            ).status_code
            == 200
        )
        assert client.get(f"/api/v1/authorization/chat/knowledge-bases/{rbac.kb_b}").status_code == status
    grants = rbac.admin.get(f"/api/v1/admin/kb-access/{rbac.kb_b}").json()["items"]
    grant_id = next(item["grant"]["id"] for item in grants if item["application"] == "chat")
    assert rbac.mutate("DELETE", f"/api/v1/admin/kb-access/{rbac.kb_b}/{grant_id}", {}).status_code == 204
    assert rbac.clients["KB_ADMIN"].get(f"/api/v1/authorization/chat/knowledge-bases/{rbac.kb_b}").status_code == 403


def test_missing_or_revoked_session_cannot_access_rbac(rbac: RbacFixture) -> None:
    with TestClient(create_app(rbac.auth.settings)) as anonymous:
        assert anonymous.get("/api/v1/admin/roles").status_code == 401
    with Connection.connect(postgres_conninfo(rbac.auth.settings)) as connection:
        connection.execute(
            "UPDATE auth_sessions SET revoked_at=CURRENT_TIMESTAMP WHERE user_id=%s", (rbac.users["SUPER_ADMIN"],)
        )
    assert rbac.admin.get("/api/v1/admin/roles").status_code == 401
    assert (
        rbac.admin.post(
            "/api/v1/admin/roles",
            headers={"Origin": ORIGIN, "X-CSRF-Token": rbac.csrf["SUPER_ADMIN"]},
            json={
                "confirm": True,
                "expected_policy_version": "rbac-v1:1",
                "code": "DENIED",
                "name": "denied",
                "permission_codes": [],
            },
        ).status_code
        == 401
    )
