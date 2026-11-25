"""Real PostgreSQL authentication lifecycle and cross-application refusal scenarios."""

import json
import os
import secrets
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from uuid import UUID, uuid4

import pytest
from app.adapters.postgres import postgres_conninfo
from app.core.config import Settings, load_settings
from app.main import create_app
from app.modules.iam.infrastructure.local_identity import LOCAL_ISSUER, password_hash, read_private_config
from fastapi.testclient import TestClient
from psycopg import Connection, sql

from scripts.infrastructure import compose, initialize_config
from scripts.local_identity import provision
from scripts.migrate_database import run_migration

pytestmark = pytest.mark.infrastructure
PASSWORD = "synthetic-private-password-1234"
ORIGINS = {"chat": "http://127.0.0.1:5173", "admin": "http://127.0.0.1:5174"}


@pytest.fixture(scope="module")
def postgres_settings() -> Iterator[Settings]:
    initialize_config("test")
    compose("test", "up", "--detach", "--wait", "postgres")
    try:
        yield load_settings("test")
    finally:
        compose("test", "down", "--volumes")


@dataclass
class AuthFixture:
    client: TestClient
    settings: Settings
    user_id: UUID
    identity_id: UUID

    def login(self, application: str = "chat"):
        return self.client.post(
            f"/api/v1/auth/{application}/login",
            headers={"Origin": ORIGINS[application]},
            json={"username": "fixture", "password": PASSWORD},
        )


@pytest.fixture
def auth(postgres_settings: Settings, tmp_path: Path) -> Iterator[AuthFixture]:
    name = "auth_verify_" + uuid4().hex
    with Connection.connect(postgres_conninfo(postgres_settings), autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(sql.Identifier(name)))
        try:
            path = tmp_path / "local.json"
            salt = secrets.token_hex(16)
            path.write_text(
                json.dumps(
                    {
                        "signing_key": secrets.token_hex(48),
                        "accounts": [
                            {
                                "username": "fixture",
                                "subject": "exact-subject",
                                "salt": salt,
                                "password_hash": password_hash(PASSWORD, salt),
                            }
                        ],
                    }
                )
            )
            os.chmod(path, 0o600)
            settings = postgres_settings.model_copy(
                update={"postgres_database": name, "local_identity_config_ref": path}
            )
            run_migration(settings, "upgrade")
            user_id, identity_id = uuid4(), uuid4()
            with Connection.connect(postgres_conninfo(settings)) as connection:
                connection.execute(
                    "INSERT INTO users(id,display_name,status) VALUES (%s,'测试员工','ACTIVE')", (user_id,)
                )
                connection.execute(
                    "INSERT INTO identities(id,user_id,provider_key,issuer,subject,status) "
                    "VALUES (%s,%s,'local',%s,'exact-subject','ACTIVE')",
                    (identity_id, user_id, LOCAL_ISSUER),
                )
                connection.execute(
                    "INSERT INTO identity_applications(identity_id,application) VALUES (%s,'chat'),(%s,'admin')",
                    (identity_id, identity_id),
                )
            with TestClient(create_app(settings), client=(uuid4().hex, 50000)) as client:
                yield AuthFixture(client, settings, user_id, identity_id)
        finally:
            admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))


def test_login_stable_mapping_rotation_replay_revocation_and_no_plaintext_storage(auth: AuthFixture) -> None:
    response = auth.login()
    assert response.status_code == 200, response.text
    assert response.json()["user"]["id"] == str(auth.user_id)
    assert "access_token" not in response.text and "exact-subject" not in response.text
    assert all("HttpOnly" in value and "SameSite=strict" in value for value in response.headers.get_list("set-cookie"))
    csrf = response.json()["csrf_token"]
    old_refresh = auth.client.cookies["er_chat_refresh"]
    old_access = auth.client.cookies["er_chat_access"]
    assert auth.client.get("/api/v1/auth/chat/me").status_code == 200
    rotated = auth.client.post("/api/v1/auth/chat/refresh", headers={"Origin": ORIGINS["chat"], "X-CSRF-Token": csrf})
    assert rotated.status_code == 200
    assert auth.client.cookies["er_chat_refresh"] != old_refresh
    with Connection.connect(postgres_conninfo(auth.settings)) as connection:
        rows = connection.execute("SELECT token_hash FROM auth_refresh_tokens").fetchall()
        assert all(len(row[0]) == 64 and old_refresh not in row[0] for row in rows)
        assert connection.execute("SELECT count(*) FROM users").fetchone() == (1,)
    auth.client.cookies.set("er_chat_refresh", old_refresh, domain="testserver.local", path="/")
    replay = auth.client.post("/api/v1/auth/chat/refresh", headers={"Origin": ORIGINS["chat"], "X-CSRF-Token": csrf})
    assert replay.status_code == 401
    auth.client.cookies.set("er_chat_access", old_access, domain="testserver.local", path="/")
    assert auth.client.get("/api/v1/auth/chat/me").status_code == 401
    assert auth.login().json()["user"]["id"] == str(auth.user_id)


@pytest.mark.parametrize("status", ["DISABLED", "LOCKED", "PENDING_DEPARTURE", "DEPARTED"])
def test_inactive_users_cannot_login_or_restore_existing_sessions(auth: AuthFixture, status: str) -> None:
    assert auth.login().status_code == 200
    with Connection.connect(postgres_conninfo(auth.settings)) as connection:
        connection.execute("UPDATE users SET status=%s WHERE id=%s", (status, auth.user_id))
    assert auth.client.get("/api/v1/auth/chat/me").status_code == 401
    assert auth.login().status_code == 401


def test_unknown_and_wrong_passwords_are_denied_audited_and_rate_limited(auth: AuthFixture) -> None:
    for _ in range(5):
        response = auth.client.post(
            "/api/v1/auth/chat/login",
            headers={"Origin": ORIGINS["chat"]},
            json={"username": "fixture", "password": "wrong-private-password"},
        )
        assert response.status_code == 401
        assert "wrong-private-password" not in response.text
    assert auth.login().status_code == 429
    with Connection.connect(postgres_conninfo(auth.settings)) as connection:
        assert connection.execute("SELECT count(*) FROM auth_sessions").fetchone() == (0,)
        assert connection.execute("SELECT count(*) FROM audit_events WHERE result='DENIED'").fetchone() == (6,)


def test_origin_csrf_and_application_boundaries_and_logout(auth: AuthFixture) -> None:
    response = auth.login()
    csrf = response.json()["csrf_token"]
    refresh = "/api/v1/auth/chat/refresh"
    assert auth.client.post(refresh, headers={"Origin": ORIGINS["chat"]}).status_code == 401
    assert (
        auth.client.post(refresh, headers={"Origin": "https://untrusted.example", "X-CSRF-Token": csrf}).status_code
        == 403
    )
    assert auth.client.post(refresh, headers={"X-CSRF-Token": csrf}).status_code == 403
    assert auth.client.get("/api/v1/auth/admin/me").status_code == 401
    assert auth.client.get("/api/v1/auth/chat/me", headers={"Origin": ORIGINS["admin"]}).status_code == 403
    assert auth.login("admin").status_code == 200
    logout = auth.client.post("/api/v1/auth/chat/logout", headers={"Origin": ORIGINS["chat"], "X-CSRF-Token": csrf})
    assert logout.status_code == 204
    assert auth.client.get("/api/v1/auth/chat/me").status_code == 401
    assert auth.client.get("/api/v1/auth/admin/me").status_code == 200


def test_identity_and_application_revocation_are_loaded_currently(auth: AuthFixture) -> None:
    response = auth.login()
    with Connection.connect(postgres_conninfo(auth.settings)) as connection:
        connection.execute(
            "DELETE FROM identity_applications WHERE identity_id=%s AND application='chat'", (auth.identity_id,)
        )
    assert auth.client.get("/api/v1/auth/chat/me").status_code == 401
    assert auth.login().status_code == 401
    assert (
        auth.client.post(
            "/api/v1/auth/chat/refresh",
            headers={"Origin": ORIGINS["chat"], "X-CSRF-Token": response.json()["csrf_token"]},
        ).status_code
        == 401
    )


def test_page_reload_can_recover_csrf_but_not_expired_or_revoked_refresh(auth: AuthFixture) -> None:
    response = auth.login()
    auth.client.cookies.delete("er_chat_access", domain="testserver.local", path="/")
    assert auth.client.get("/api/v1/auth/chat/me").status_code == 401
    assert auth.client.get("/api/v1/auth/chat/csrf").json()["csrf_token"] == response.json()["csrf_token"]
    with Connection.connect(postgres_conninfo(auth.settings)) as connection:
        connection.execute("UPDATE auth_sessions SET revoked_at=CURRENT_TIMESTAMP")
    assert auth.client.get("/api/v1/auth/chat/csrf").status_code == 401


def test_expired_session_and_disabled_identity_are_rejected(auth: AuthFixture) -> None:
    response = auth.login()
    with Connection.connect(postgres_conninfo(auth.settings)) as connection:
        connection.execute("UPDATE identities SET status='DISABLED' WHERE id=%s", (auth.identity_id,))
    assert auth.login().status_code == 401
    assert auth.client.get("/api/v1/auth/chat/me").status_code == 401
    with Connection.connect(postgres_conninfo(auth.settings)) as connection:
        connection.execute("UPDATE identities SET status='ACTIVE' WHERE id=%s", (auth.identity_id,))
        connection.execute(
            "UPDATE auth_sessions SET created_at=CURRENT_TIMESTAMP-interval '2 days', expires_at=CURRENT_TIMESTAMP-interval '1 second'"
        )
    assert auth.client.get("/api/v1/auth/chat/me").status_code == 401
    assert (
        auth.client.post(
            "/api/v1/auth/chat/refresh",
            headers={"Origin": ORIGINS["chat"], "X-CSRF-Token": response.json()["csrf_token"]},
        ).status_code
        == 401
    )


def test_concurrent_refresh_has_one_winner_and_replay_revokes_the_family(auth: AuthFixture) -> None:
    response = auth.login()
    cookies = dict(auth.client.cookies)

    def renew() -> int:
        with TestClient(create_app(auth.settings)) as other:
            other.cookies.update(cookies)
            return other.post(
                "/api/v1/auth/chat/refresh",
                headers={"Origin": ORIGINS["chat"], "X-CSRF-Token": response.json()["csrf_token"]},
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        attempts = [executor.submit(renew) for _ in range(2)]
        assert sorted(attempt.result() for attempt in attempts) == [200, 401]
    assert auth.client.get("/api/v1/auth/chat/me").status_code == 401


def test_audit_failure_rolls_back_successful_login_and_identity_keys_are_exact(auth: AuthFixture) -> None:
    with Connection.connect(postgres_conninfo(auth.settings)) as connection:
        connection.execute("UPDATE identities SET issuer='urn:enterprise-rag:LOCAL' WHERE id=%s", (auth.identity_id,))
    assert auth.login().status_code == 401
    with Connection.connect(postgres_conninfo(auth.settings)) as connection:
        connection.execute("UPDATE identities SET issuer=%s WHERE id=%s", (LOCAL_ISSUER, auth.identity_id))
        connection.execute(
            "CREATE FUNCTION reject_auth_audit() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'audit unavailable'; END $$"
        )
        connection.execute(
            "CREATE TRIGGER reject_auth_audit BEFORE INSERT ON audit_events FOR EACH ROW EXECUTE FUNCTION reject_auth_audit()"
        )
    assert auth.login().status_code == 503
    with Connection.connect(postgres_conninfo(auth.settings)) as connection:
        assert connection.execute("SELECT count(*) FROM auth_sessions").fetchone() == (0,)
        assert connection.execute("SELECT count(*) FROM users").fetchone() == (1,)


def test_concurrent_provisioning_preserves_accounts_and_refuses_duplicate_names(
    auth: AuthFixture,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("scripts.local_identity.load_settings", lambda: auth.settings)
    path = tmp_path / "provision.json"

    def add(username: str) -> bool:
        try:
            provision(username, PASSWORD, ["chat"], path, "本地测试")
            return True
        except ValueError:
            return False

    with ThreadPoolExecutor(max_workers=2) as executor:
        attempts = [executor.submit(add, name) for name in ("first", "second")]
        assert [attempt.result() for attempt in attempts] == [True, True]
    assert {account.username for account in read_private_config(path).accounts} == {"first", "second"}
    with ThreadPoolExecutor(max_workers=2) as executor:
        attempts = [executor.submit(add, "same") for _ in range(2)]
        assert sorted(attempt.result() for attempt in attempts) == [False, True]
    assert len(read_private_config(path).accounts) == 3
    with Connection.connect(postgres_conninfo(auth.settings)) as connection:
        assert connection.execute("SELECT count(*) FROM users").fetchone() == (4,)


@pytest.mark.parametrize("locked_table", ["auth_sessions", "users"])
def test_refresh_waiting_for_a_row_lock_cannot_extend_an_expired_session(auth: AuthFixture, locked_table: str) -> None:
    response = auth.login()
    entered = Event()

    def renew() -> int:
        entered.set()
        return auth.client.post(
            "/api/v1/auth/chat/refresh",
            headers={"Origin": ORIGINS["chat"], "X-CSRF-Token": response.json()["csrf_token"]},
        ).status_code

    with Connection.connect(postgres_conninfo(auth.settings)) as connection:
        connection.execute(
            "UPDATE auth_sessions SET created_at=CURRENT_TIMESTAMP-interval '2 days', expires_at=CURRENT_TIMESTAMP+interval '1 second'"
        )
    with ThreadPoolExecutor(max_workers=1) as executor:
        with Connection.connect(postgres_conninfo(auth.settings)) as connection:
            connection.execute(sql.SQL("SELECT * FROM {} FOR UPDATE").format(sql.Identifier(locked_table)))
            attempt = executor.submit(renew)
            assert entered.wait(2)
            time.sleep(1.3)
        assert attempt.result(timeout=5) == 401
