"""Real PostgreSQL audit reads, trusted provenance, append-only constraints and rollback."""

import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from app.adapters.postgres import postgres_conninfo
from app.core.config import Settings
from app.main import create_app
from app.modules.iam.domain.sessions import PlatformSession
from app.modules.iam.infrastructure.local_identity import read_private_config
from app.modules.iam.infrastructure.tokens import JwtSessionTokens
from fastapi.testclient import TestClient
from httpx2 import Response
from psycopg import Connection
from psycopg.errors import CheckViolation
from tests.test_auth_postgres import ORIGINS, PASSWORD, AuthFixture
from tests.test_auth_postgres import auth as auth
from tests.test_auth_postgres import postgres_settings as postgres_settings
from tests.test_rbac_postgres import RbacFixture
from tests.test_rbac_postgres import rbac as rbac

pytestmark = pytest.mark.infrastructure
PATH = "/api/v1/admin/audit-logs"


def assert_anonymous_denial(
    settings: Settings, response: Response, action: str, object_id: UUID | None, peer: str
) -> None:
    with Connection.connect(postgres_conninfo(settings)) as connection:
        rows = connection.execute(
            "SELECT to_jsonb(e) || jsonb_build_object('ip_address',host(e.ip_address)) "
            "FROM audit_events e WHERE request_id=%s",
            (UUID(response.headers["X-Request-ID"]),),
        ).fetchall()
    assert len(rows) == 1
    event = rows[0][0]
    assert event["action"] == action and event["result"] == "DENIED"
    assert event["actor_user_id"] is None and event["actor_role_ids"] == [] and event["actor_system_roles"] == []
    assert event["object_id"] == (str(object_id) if object_id is not None else None)
    assert event["ip_address"] == peer and event["trace_id"] == response.headers["X-Trace-ID"]
    assert event["before_snapshot"] is None and event["after_snapshot"] is None
    assert event["target_trace_id"] is None and event["protected_reason_ref"] is None
    for secret in (PASSWORD, "exact-subject", "untrusted-forged-access", "private-unknown-account"):
        assert secret not in json.dumps(event)


def test_audit_reads_enforce_current_permission_and_admin_purpose(rbac: RbacFixture) -> None:
    with TestClient(create_app(rbac.auth.settings)) as anonymous:
        assert anonymous.get(PATH).status_code == 401
    for actor, status in (("SUPER_ADMIN", 200), ("AUDIT_READONLY", 200), ("KB_ADMIN", 403), ("EMPLOYEE", 403)):
        response = rbac.clients[actor].get(PATH)
        assert response.status_code == status, response.text
        if status == 403:
            assert "actor_user_id" not in response.text
    assert rbac.auth.login("chat").status_code == 200
    with TestClient(create_app(rbac.auth.settings)) as chat_only:
        chat_only.cookies.set("er_chat_access", rbac.admin.cookies["er_chat_access"])
        assert chat_only.get(PATH).status_code == 401
        chat_only.cookies.set("er_admin_access", rbac.admin.cookies["er_chat_access"])
        assert chat_only.get(PATH).status_code == 401
    assert (
        rbac.mutate("PUT", f"/api/v1/admin/users/{rbac.users['AUDIT_READONLY']}/roles", {"role_ids": []}).status_code
        == 204
    )
    assert rbac.clients["AUDIT_READONLY"].get(PATH).status_code == 403


def test_login_records_direct_ip_current_roles_and_response_correlation(rbac: RbacFixture) -> None:
    with TestClient(create_app(rbac.auth.settings), client=("192.0.2.41", 50000)) as client:
        response = client.post(
            "/api/v1/auth/admin/login",
            headers={
                "Origin": ORIGINS["admin"],
                "X-Forwarded-For": "203.0.113.77",
                "X-Real-IP": "203.0.113.88",
                "X-Request-ID": str(uuid4()),
                "traceparent": "00-" + "a" * 32 + "-" + "b" * 16 + "-01",
            },
            json={"username": "fixture", "password": PASSWORD},
        )
        assert response.status_code == 200, response.text
        result = client.get(PATH, params={"request_id": response.headers["X-Request-ID"]})
        assert result.status_code == 200, result.text
        assert result.headers["Cache-Control"] == "no-store"
        event = result.json()["items"][0]
        assert event["module"] == "iam" and event["action"] == "iam.login"
        assert event["actor_user_id"] == str(rbac.users["SUPER_ADMIN"])
        assert event["actor_system_roles"] == ["SUPER_ADMIN"]
        assert event["actor_role_ids"] == [str(rbac.roles["SUPER_ADMIN"])]
        assert event["ip_address"] == "192.0.2.41" and event["risk"] == "MEDIUM"
        assert event["trace_id"] == response.headers["X-Trace-ID"] == "a" * 32
        for secret in (
            PASSWORD,
            "exact-subject",
            client.cookies["er_admin_access"],
            client.cookies["er_admin_refresh"],
        ):
            assert secret not in result.text


def test_failed_login_and_throttling_are_anonymous_audited_without_credentials(auth: AuthFixture) -> None:
    with TestClient(create_app(auth.settings), client=("2001:db8::41", 50000)) as client:
        for number in range(6):
            response = client.post(
                "/api/v1/auth/admin/login",
                headers={"Origin": ORIGINS["admin"]},
                json={"username": "private-unknown-account", "password": "sensitive-password"},
            )
            assert response.status_code == (401 if number < 5 else 429)
            with Connection.connect(postgres_conninfo(auth.settings)) as connection:
                row = connection.execute(
                    "SELECT to_jsonb(e) FROM audit_events e WHERE request_id=%s",
                    (UUID(response.headers["X-Request-ID"]),),
                ).fetchone()
            assert row is not None
            event = row[0]
            assert event["result"] == "DENIED" and event["actor_user_id"] is None
            assert event["actor_role_ids"] == [] and event["actor_system_roles"] == []
            assert event["trace_id"] == response.headers["X-Trace-ID"]
            assert str(event["ip_address"]).startswith("2001:db8::41")
            assert "sensitive-password" not in json.dumps(event) and "private-unknown-account" not in json.dumps(event)


def test_role_permission_success_denied_and_conflict_audits_have_provenance_and_target(rbac: RbacFixture) -> None:
    role = rbac.roles["KB_ADMIN"]
    response = rbac.mutate("DELETE", f"/api/v1/admin/roles/{role}", {}, actor="KB_ADMIN")
    assert response.status_code == 403
    conflict = rbac.mutate("DELETE", f"/api/v1/admin/roles/{role}", {})
    assert conflict.status_code == 409
    for attempted, result, actor in ((response, "DENIED", "KB_ADMIN"), (conflict, "FAILED", "SUPER_ADMIN")):
        fetched = rbac.admin.get(PATH, params={"request_id": attempted.headers["X-Request-ID"]})
        event = fetched.json()["items"][0]
        assert event["result"] == result and event["risk"] == "HIGH"
        assert event["object_id"] == str(role) and event["actor_user_id"] == str(rbac.users[actor])
        assert event["actor_role_ids"] == [str(rbac.roles[actor])]
        assert event["after"] is None
    with TestClient(create_app(rbac.auth.settings), client=("192.0.2.81", 50000)) as client:
        client.cookies.update(dict(rbac.admin.cookies))
        response = client.post(
            "/api/v1/admin/roles",
            headers={
                "Origin": ORIGINS["admin"],
                "X-CSRF-Token": rbac.csrf["SUPER_ADMIN"],
                "X-Forwarded-For": "203.0.113.11",
            },
            json={
                "confirm": True,
                "expected_policy_version": rbac.version(),
                "code": "AUDIT_PROBE",
                "name": "private role name is not a snapshot",
                "permission_codes": ["audit.read"],
            },
        )
        assert response.status_code == 201, response.text
        event = client.get(PATH, params={"request_id": response.headers["X-Request-ID"]}).json()["items"][0]
        assert event["ip_address"] == "192.0.2.81" and event["result"] == "SUCCEEDED"
        assert event["object_id"] == response.json()["role"]["id"]
        assert event["after"]["permission_ids"]
        assert "private role name" not in json.dumps(event)


def test_audit_filters_bounded_pagination_and_private_reveal_reason(rbac: RbacFixture) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    ids = [UUID(int=100 + n) for n in range(3)]
    request_id, reason = uuid4(), uuid4()
    with Connection.connect(postgres_conninfo(rbac.auth.settings)) as connection:
        for index, event_id in enumerate(ids):
            connection.execute(
                "INSERT INTO audit_events(id,occurred_at,action,result,risk,request_id,trace_id,object_id) "
                "VALUES(%s,%s,'kb.change',%s,'HIGH',%s,%s,%s)",
                (event_id, now, "FAILED" if index == 0 else "SUCCEEDED", request_id, "c" * 32, rbac.kb_a),
            )
        connection.execute(
            "INSERT INTO audit_events(id,occurred_at,action,result,risk,request_id,actor_user_id,target_trace_id,protected_reason_ref) "
            "VALUES(%s,%s,'trace.reveal_identity','SUCCEEDED','HIGH',%s,%s,%s,%s)",
            (uuid4(), now, uuid4(), rbac.users["SUPER_ADMIN"], "d" * 32, reason),
        )
    filters = {
        "module": "kb",
        "action": "kb.change",
        "risk": "HIGH",
        "request_id": str(request_id),
        "object_id": str(rbac.kb_a),
        "trace_id": "c" * 32,
        "occurred_from": now.isoformat(),
        "occurred_until": (now + timedelta(seconds=1)).isoformat(),
        "page_size": "2",
    }
    response = rbac.admin.get(PATH, params=filters)
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 3
    assert [item["id"] for item in response.json()["items"]] == [str(ids[2]), str(ids[1])]
    second = rbac.admin.get(PATH, params=filters | {"page": "2"}).json()
    assert [item["id"] for item in second["items"]] == [str(ids[0])]
    assert rbac.admin.get(PATH, params=filters | {"page": "3"}).json()["items"] == []
    assert rbac.admin.get(PATH, params=filters | {"result": "FAILED"}).json()["total"] == 1
    assert rbac.admin.get(PATH, params=filters | {"actor_user_id": str(rbac.users["SUPER_ADMIN"])}).json()["total"] == 0
    assert (
        rbac.admin.get(
            PATH,
            params=filters
            | {"occurred_until": now.isoformat(), "occurred_from": (now - timedelta(seconds=1)).isoformat()},
        ).json()["total"]
        == 0
    )
    reveal = rbac.admin.get(PATH, params={"action": "trace.reveal_identity"})
    assert reveal.status_code == 200, reveal.text
    assert reveal.json()["items"][0]["target_trace_id"] == "d" * 32
    assert str(reason) not in reveal.text and "protected_reason_ref" not in reveal.text


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_no_business_api_can_append_update_or_delete_audit(rbac: RbacFixture, method: str) -> None:
    count = rbac.admin.get(PATH).json()["total"]
    for path in (PATH, f"{PATH}/{uuid4()}"):
        response = rbac.admin.request(
            method,
            path,
            headers={"Origin": ORIGINS["admin"], "X-CSRF-Token": rbac.csrf["SUPER_ADMIN"]},
            json={"confirm": True, "action": "iam.login", "result": "SUCCEEDED"},
        )
        assert response.status_code in {404, 405}
    assert rbac.admin.get(PATH).json()["total"] == count
    with Connection.connect(postgres_conninfo(rbac.auth.settings)) as connection:
        for statement in (
            "UPDATE audit_events SET result='SUCCEEDED'",
            "DELETE FROM audit_events",
            "TRUNCATE audit_events",
        ):
            with pytest.raises(CheckViolation), connection.transaction():
                connection.execute(statement)


def test_audit_failure_blocks_login_and_high_risk_mutation_without_secret_logs(
    rbac: RbacFixture, caplog: pytest.LogCaptureFixture
) -> None:
    with Connection.connect(postgres_conninfo(rbac.auth.settings)) as connection:
        baseline = connection.execute("SELECT count(*) FROM auth_sessions").fetchone()
        connection.execute(
            "CREATE FUNCTION reject_audit_test() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN "
            "RAISE EXCEPTION 'synthetic-secret-that-must-not-escape'; END $$"
        )
        connection.execute(
            "CREATE TRIGGER reject_audit_test BEFORE INSERT ON audit_events FOR EACH ROW EXECUTE FUNCTION reject_audit_test()"
        )
    assert rbac.auth.login("admin").status_code == 503
    response = rbac.mutate("POST", "/api/v1/admin/roles", {"code": "ATOMIC", "name": "atomic", "permission_codes": []})
    assert response.status_code == 503
    with TestClient(create_app(rbac.auth.settings)) as anonymous:
        for headers in ({}, {"Origin": ORIGINS["admin"]}):
            denied = anonymous.request(
                "DELETE",
                f"/api/v1/admin/roles/{rbac.roles['KB_ADMIN']}",
                headers=headers,
                json={"confirm": True, "expected_policy_version": rbac.version()},
            )
            assert denied.status_code == 503
            assert "synthetic-secret" not in denied.text
        denied_login = anonymous.post("/api/v1/auth/admin/login", json={"username": "fixture", "password": PASSWORD})
        assert denied_login.status_code == 503
        assert "synthetic-secret" not in denied_login.text
    assert "synthetic-secret" not in response.text and "synthetic-secret" not in caplog.text
    assert PASSWORD not in caplog.text
    with Connection.connect(postgres_conninfo(rbac.auth.settings)) as connection:
        assert connection.execute("SELECT count(*) FROM auth_sessions").fetchone() == baseline
        assert connection.execute("SELECT count(*) FROM roles WHERE code='ATOMIC'").fetchone() == (0,)
        assert connection.execute("SELECT deleted_at FROM roles WHERE id=%s", (rbac.roles["KB_ADMIN"],)).fetchone() == (
            None,
        )


def test_invalid_audit_filters_are_rejected_without_echoing_input(rbac: RbacFixture) -> None:
    for params in (
        {"module": "iam' OR true --"},
        {"page_size": "101"},
        {"page": "0"},
        {"occurred_from": "2026-11-25T12:00:00"},
        {"trace_id": "0" * 32},
        {"occurred_from": "2026-11-25T12:00:00Z", "occurred_until": "2026-11-25T11:00:00Z"},
        {"password": "do-not-echo-me"},
    ):
        response = rbac.admin.get(PATH, params=params)
        assert response.status_code == 422, response.text
        assert "do-not-echo-me" not in response.text and "OR true" not in response.text


def test_malformed_stored_summary_fails_closed_instead_of_returning_private_json(rbac: RbacFixture) -> None:
    request_id = uuid4()
    with Connection.connect(postgres_conninfo(rbac.auth.settings)) as connection:
        # An offline/legacy writer can bypass DTO validation; reads must still enforce it.
        connection.execute(
            "INSERT INTO audit_events(id,occurred_at,action,result,risk,request_id,before_snapshot) "
            "VALUES(%s,CURRENT_TIMESTAMP,'iam.permission_change','FAILED','HIGH',%s,'{\"password\":\"synthetic-private-payload\"}'::jsonb)",
            (uuid4(), request_id),
        )
    response = rbac.admin.get(PATH, params={"request_id": str(request_id)})
    assert response.status_code == 503
    assert "synthetic-private-payload" not in response.text and "before_snapshot" not in response.text


def test_pre_authentication_and_origin_denials_are_committed_as_anonymous_events(rbac: RbacFixture) -> None:
    target = rbac.roles["KB_ADMIN"]
    payload = {"confirm": True, "expected_policy_version": rbac.version()}

    def check_event(response: Response, action: str, object_id: UUID | None = None) -> None:
        assert_anonymous_denial(rbac.auth.settings, response, action, object_id, "192.0.2.19")

    with TestClient(create_app(rbac.auth.settings), client=("192.0.2.19", 50000)) as client:
        now = datetime.now(UTC)
        forged = JwtSessionTokens("untrusted-signing-key" * 4).issue(
            PlatformSession(
                uuid4(), rbac.users["SUPER_ADMIN"], rbac.auth.identity_id, "admin", now + timedelta(hours=1)
            ),
            now,
            now + timedelta(minutes=5),
        )
        config_ref = rbac.auth.settings.local_identity_config_ref
        assert config_ref is not None
        tokens = JwtSessionTokens(read_private_config(config_ref).signing_key.get_secret_value())
        unknown_session = tokens.issue(
            PlatformSession(
                uuid4(), rbac.users["SUPER_ADMIN"], rbac.auth.identity_id, "admin", now + timedelta(hours=1)
            ),
            now,
            now + timedelta(minutes=5),
        )
        claims = tokens.verify(rbac.admin.cookies["er_admin_access"], "admin")
        expired_access = tokens.issue(
            PlatformSession(claims.session_id, claims.user_id, claims.identity_id, "admin", now + timedelta(hours=1)),
            now - timedelta(minutes=10),
            now - timedelta(seconds=1),
        )
        assert rbac.auth.login("chat").status_code == 200
        for credential in (
            None,
            "untrusted-forged-access",
            forged,
            unknown_session,
            expired_access,
            rbac.admin.cookies["er_chat_access"],
        ):
            if credential:
                client.cookies.set("er_admin_access", credential)
            response = client.request(
                "DELETE", f"/api/v1/admin/roles/{target}", headers={"Origin": ORIGINS["admin"]}, json=payload
            )
            assert response.status_code == 401
            check_event(response, "iam.role_change", target)
        client.cookies.clear()
        client.cookies.update(dict(rbac.admin.cookies))
        response = client.request(
            "DELETE", f"/api/v1/admin/roles/{target}", headers={"Origin": "https://foreign.example"}, json=payload
        )
        assert response.status_code == 403
        check_event(response, "iam.role_change", target)
        for headers in (
            {},
            {"Origin": "https://foreign.example"},
            {"Origin": ORIGINS["admin"], "Sec-Fetch-Site": "cross-site"},
        ):
            response = client.post(
                "/api/v1/auth/admin/login", headers=headers, json={"username": "fixture", "password": PASSWORD}
            )
            assert response.status_code == 403
            check_event(response, "iam.login")
        with Connection.connect(postgres_conninfo(rbac.auth.settings)) as connection:
            connection.execute(
                "UPDATE auth_sessions SET revoked_at=CURRENT_TIMESTAMP WHERE user_id=%s", (rbac.users["SUPER_ADMIN"],)
            )
        response = client.request(
            "DELETE", f"/api/v1/admin/roles/{target}", headers={"Origin": ORIGINS["admin"]}, json=payload
        )
        assert response.status_code == 401
        check_event(response, "iam.role_change", target)
        with Connection.connect(postgres_conninfo(rbac.auth.settings)) as connection:
            connection.execute(
                "UPDATE auth_sessions SET revoked_at=NULL,created_at=CURRENT_TIMESTAMP-interval '2 days',expires_at=CURRENT_TIMESTAMP-interval '1 second' WHERE user_id=%s",
                (rbac.users["SUPER_ADMIN"],),
            )
        response = client.request(
            "DELETE", f"/api/v1/admin/roles/{target}", headers={"Origin": ORIGINS["admin"]}, json=payload
        )
        assert response.status_code == 401
        check_event(response, "iam.role_change", target)
    with Connection.connect(postgres_conninfo(rbac.auth.settings)) as connection:
        assert connection.execute("SELECT deleted_at FROM roles WHERE id=%s", (target,)).fetchone() == (None,)


@pytest.mark.parametrize("denial", ["missing_session", "missing_origin", "foreign_origin", "cross_site"])
def test_all_rbac_mutation_routes_audit_early_denials(rbac: RbacFixture, denial: str) -> None:
    role, user, kb = rbac.roles["KB_ADMIN"], rbac.users["KB_ADMIN"], rbac.kb_a
    intents: tuple[tuple[str, str, dict[str, object], str, UUID | None], ...] = (
        (
            "POST",
            "/api/v1/admin/roles",
            {"code": "EARLY_DENIAL", "name": "private role", "permission_codes": []},
            "iam.role_change",
            None,
        ),
        (
            "PATCH",
            f"/api/v1/admin/roles/{role}",
            {"name": "private role", "permission_codes": []},
            "iam.permission_change",
            role,
        ),
        ("DELETE", f"/api/v1/admin/roles/{role}", {}, "iam.role_change", role),
        ("PUT", f"/api/v1/admin/users/{user}/roles", {"role_ids": []}, "iam.role_change", user),
        (
            "PUT",
            f"/api/v1/admin/kb-access/{kb}",
            {"application": "admin", "principal_type": "USER", "principal_id": str(user), "permission": "MANAGE"},
            "iam.permission_change",
            kb,
        ),
        ("DELETE", f"/api/v1/admin/kb-access/{kb}/{uuid4()}", {}, "iam.permission_change", kb),
    )
    headers = {
        "Origin": ORIGINS["admin"],
        "X-CSRF-Token": rbac.csrf["SUPER_ADMIN"],
        "X-Forwarded-For": "203.0.113.77",
        "X-Real-IP": "203.0.113.88",
    }
    if denial == "missing_origin":
        del headers["Origin"]
    elif denial == "foreign_origin":
        headers["Origin"] = "https://foreign.example"
    elif denial == "cross_site":
        headers["Sec-Fetch-Site"] = "cross-site"
    version = rbac.version()
    with Connection.connect(postgres_conninfo(rbac.auth.settings)) as connection:
        before = connection.execute(
            "SELECT (SELECT count(*) FROM roles), (SELECT count(*) FROM user_roles), "
            "(SELECT count(*) FROM kb_resource_grants), (SELECT version FROM policy_state WHERE singleton)"
        ).fetchone()
    with TestClient(create_app(rbac.auth.settings), client=("2001:db8::19", 50000)) as client:
        if denial != "missing_session":
            client.cookies.update(dict(rbac.admin.cookies))
        for method, path, payload, action, target in intents:
            response = client.request(
                method, path, headers=headers, json={"confirm": True, "expected_policy_version": version, **payload}
            )
            assert response.status_code == (401 if denial == "missing_session" else 403), response.text
            assert_anonymous_denial(rbac.auth.settings, response, action, target, "2001:db8::19")
    with Connection.connect(postgres_conninfo(rbac.auth.settings)) as connection:
        assert (
            connection.execute(
                "SELECT (SELECT count(*) FROM roles), (SELECT count(*) FROM user_roles), "
                "(SELECT count(*) FROM kb_resource_grants), (SELECT version FROM policy_state WHERE singleton)"
            ).fetchone()
            == before
        )


@pytest.mark.parametrize("application", ["chat", "admin"])
def test_login_origin_denials_do_not_create_sessions_or_consume_login_budget(
    auth: AuthFixture, application: str
) -> None:
    with TestClient(create_app(auth.settings), client=("192.0.2.29", 50000)) as client:
        for headers in (
            {},
            {"Origin": "https://foreign.example"},
            {"Origin": ORIGINS[application], "Sec-Fetch-Site": "cross-site"},
        ):
            response = client.post(
                f"/api/v1/auth/{application}/login",
                headers=headers,
                json={"username": "private-unknown-account", "password": PASSWORD},
            )
            assert response.status_code == 403
            assert_anonymous_denial(auth.settings, response, "iam.login", None, "192.0.2.29")
    with Connection.connect(postgres_conninfo(auth.settings)) as connection:
        assert connection.execute("SELECT count(*) FROM auth_sessions").fetchone() == (0,)
        assert connection.execute("SELECT count(*) FROM auth_login_budgets").fetchone() == (0,)
