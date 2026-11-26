"""Provider HTTP authorization, encrypted persistence and transactional failure on real PostgreSQL."""

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from app.adapters.postgres import postgres_conninfo
from app.main import create_app
from app.modules.model_gateway.domain.contracts import SecretReference
from app.modules.model_gateway.domain.registry import EncryptedSecretValue
from app.modules.model_gateway.infrastructure.provider_secrets import (
    AesGcmProviderSecretCipher,
    read_provider_secrets_config,
)
from fastapi.testclient import TestClient
from psycopg import Connection
from psycopg.errors import RaiseException
from tests.test_auth_postgres import auth as auth
from tests.test_auth_postgres import postgres_settings as postgres_settings
from tests.test_rbac_postgres import ORIGIN, RbacFixture
from tests.test_rbac_postgres import rbac as rbac

from scripts.initialize_provider_secrets import initialize

pytestmark = pytest.mark.infrastructure
BASE = "/api/v1/admin/providers"
KEY = "synthetic-provider-api-key-001"
PROXY = "https://proxy-user:synthetic-proxy-password@proxy.example:8443"


@dataclass
class ProviderFixture:
    rbac: RbacFixture
    clients: dict[str, TestClient]
    cipher: AesGcmProviderSecretCipher

    @property
    def admin(self) -> TestClient:
        return self.clients["SUPER_ADMIN"]

    def write(self, method: str, path: str = BASE, /, *, actor: str = "SUPER_ADMIN", **fields: object):
        return self.clients[actor].request(
            method,
            path,
            headers={"Origin": ORIGIN, "X-CSRF-Token": self.rbac.csrf[actor]},
            json={"expected_policy_version": self.rbac.version(), "confirm": True, **fields},
        )

    def create(self, *, actor: str = "SUPER_ADMIN", **fields: object):
        return self.write(
            "POST",
            actor=actor,
            **{
                "name": "测试供应商",
                "provider_type": "openai_compatible",
                "base_url": "https://api.example.com/v1",
                "timeout_seconds": 30,
                "credential": KEY,
                "proxy_url": PROXY,
                "remarks": "测试用途",
                **fields,
            },
        )


@pytest.fixture
def providers(rbac: RbacFixture, tmp_path: Path) -> Iterator[ProviderFixture]:
    path = tmp_path / "provider-keys.json"
    initialize(path)
    settings = rbac.auth.settings.model_copy(update={"provider_secrets_config_ref": path})
    clients: dict[str, TestClient] = {}
    try:
        for actor, original in rbac.clients.items():
            client = TestClient(create_app(settings))
            client.__enter__()
            client.cookies.update(original.cookies)
            clients[actor] = client
        yield ProviderFixture(rbac, clients, AesGcmProviderSecretCipher(read_provider_secrets_config(path)))
    finally:
        for client in clients.values():
            client.__exit__(None, None, None)


def assert_private(payload: str) -> None:
    assert all(
        secret not in payload for secret in (KEY, PROXY, "synthetic-proxy-password", "credential_ref", "ciphertext")
    )


def test_provider_crud_retains_immutable_versions_and_encrypted_key_history(providers: ProviderFixture) -> None:
    created = providers.create(name="  主供应商  ")
    assert created.status_code == 201, created.text
    assert_private(created.text)
    item = created.json()
    assert item["name"] == "主供应商" and item["has_credential"] and item["proxy_configured"]
    path = f"{BASE}/{item['id']}"
    updated = providers.write(
        "PATCH",
        path,
        expected_config_version=item["config_version"],
        credential="synthetic-rotated-key",
        clear_proxy=True,
        timeout_seconds=75,
        remarks="更新备注",
    )
    assert updated.status_code == 200, updated.text
    next_item = updated.json()
    assert next_item["config_version"] != item["config_version"]
    assert not next_item["proxy_configured"] and next_item["remarks"] == "更新备注"
    assert (
        providers.write("PATCH", path, expected_config_version=item["config_version"], status="DISABLED").status_code
        == 409
    )
    assert providers.write("DELETE", path, expected_config_version=item["config_version"]).status_code == 409
    assert providers.write("DELETE", path, expected_config_version=next_item["config_version"]).status_code == 204
    assert providers.admin.get(path).status_code == 404
    assert providers.admin.get(BASE).json()["total"] == 0
    with Connection.connect(postgres_conninfo(providers.rbac.auth.settings)) as connection:
        tombstone = connection.execute("SELECT status,deleted_at FROM providers WHERE id=%s", (item["id"],)).fetchone()
        assert tombstone is not None and tombstone[0] == "DISABLED" and tombstone[1] is not None
        versions = connection.execute(
            "SELECT configuration FROM provider_config_versions WHERE provider_id=%s ORDER BY created_at", (item["id"],)
        ).fetchall()
        assert len(versions) == 3
        original = next(row[0] for row in versions if row[0]["config_version"] == item["config_version"])
        reference = SecretReference.model_validate(original["credential_ref"])
        encrypted = connection.execute(
            "SELECT key_version,ciphertext FROM provider_secrets WHERE secret_id=%s AND version=%s",
            (reference.secret_id, reference.version),
        ).fetchone()
        assert encrypted is not None and KEY.encode() not in encrypted[1]
        assert providers.cipher.decrypt(reference, EncryptedSecretValue(*encrypted)).get_secret_value() == KEY
        assert connection.execute("SELECT count(*) FROM provider_secrets").fetchone() == (3,)
        audit = connection.execute(
            "SELECT before_snapshot,after_snapshot FROM audit_events WHERE action='provider.change'"
        ).fetchall()
        assert len(audit) == 5
        assert_private(json.dumps(audit, default=str))
        with pytest.raises(RaiseException), connection.transaction():
            connection.execute("UPDATE provider_config_versions SET configuration='{}'")


def test_provider_current_permissions_origins_csrf_and_revocation(providers: ProviderFixture) -> None:
    created = providers.create()
    assert created.status_code == 201, created.text
    item = created.json()
    for actor, status in (("AUDIT_READONLY", 200), ("KB_ADMIN", 403), ("EMPLOYEE", 403)):
        assert providers.clients[actor].get(BASE).status_code == status
        assert providers.create(actor=actor, name=actor).status_code == 403
    invalid_csrf = providers.admin.patch(
        f"{BASE}/{item['id']}",
        headers={"Origin": ORIGIN, "X-CSRF-Token": "invalid"},
        json={
            "expected_policy_version": providers.rbac.version(),
            "expected_config_version": item["config_version"],
            "confirm": True,
            "status": "DISABLED",
        },
    )
    assert invalid_csrf.status_code == 403
    assert (
        providers.admin.post(
            BASE,
            headers={"Origin": "https://untrusted.example"},
            json={
                "expected_policy_version": providers.rbac.version(),
                "confirm": True,
                "name": "bad-origin",
                "provider_type": "openai_compatible",
                "base_url": "https://api.example",
                "timeout_seconds": 1,
            },
        ).status_code
        == 403
    )
    with TestClient(
        create_app(
            providers.rbac.auth.settings.model_copy(
                update={
                    "provider_secrets_config_ref": None,
                }
            )
        )
    ) as unconfigured:
        assert unconfigured.get(BASE).status_code == 503
    with Connection.connect(postgres_conninfo(providers.rbac.auth.settings)) as connection:
        connection.execute("DELETE FROM user_roles WHERE user_id=%s", (providers.rbac.users["SUPER_ADMIN"],))
    assert providers.admin.get(BASE).status_code == 403
    assert providers.create(name="revoked").status_code == 403


def test_provider_pagination_duplicates_validation_and_atomic_audit_failure(providers: ProviderFixture) -> None:
    for name in ("一号供应商", "二号供应商"):
        assert providers.create(name=name).status_code == 201
    assert providers.create(name="一号供应商").status_code == 409
    page = providers.admin.get(BASE, params={"page": 3, "page_size": 1}).json()
    assert page["total"] == 2 and page["items"] == []
    filtered = providers.admin.get(BASE, params={"name": "一号", "status": "ACTIVE"}).json()
    assert len(filtered["items"]) == 1 and filtered["total"] == 1
    item = filtered["items"][0]
    assert (
        providers.write(
            "PATCH", f"{BASE}/{item['id']}", expected_config_version=item["config_version"], name=None
        ).status_code
        == 422
    )
    for value in ("", "key\r\nInjected: bad", "key value"):
        failure = providers.create(name="invalid", credential=value)
        assert failure.status_code == 422
        if value:
            assert value not in failure.text
    with Connection.connect(postgres_conninfo(providers.rbac.auth.settings)) as connection:
        connection.execute("""CREATE FUNCTION fail_provider_audit() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN IF NEW.action='provider.change' THEN RAISE EXCEPTION 'synthetic audit failure'; END IF; RETURN NEW; END; $$;
            CREATE TRIGGER fail_provider_audit BEFORE INSERT ON audit_events
            FOR EACH ROW EXECUTE FUNCTION fail_provider_audit();""")
    failure = providers.create(name="must-rollback")
    assert failure.status_code == 503, failure.text
    with Connection.connect(postgres_conninfo(providers.rbac.auth.settings)) as connection:
        assert connection.execute("SELECT count(*) FROM providers").fetchone() == (2,)
        assert connection.execute("SELECT count(*) FROM provider_config_versions").fetchone() == (2,)
        assert connection.execute("SELECT count(*) FROM provider_secrets").fetchone() == (4,)


def test_provider_rejects_anonymous_chat_cookies_and_stale_policy(providers: ProviderFixture) -> None:
    stale = providers.create(expected_policy_version="rbac-v1:0")
    assert stale.status_code == 409
    providers.admin.cookies.clear()
    assert providers.admin.get(BASE).status_code == 401
    assert providers.create().status_code == 401
    response = providers.rbac.auth.login("chat")
    assert response.status_code == 200
    providers.admin.cookies.set("er_admin_access", providers.rbac.auth.client.cookies["er_chat_access"])
    assert providers.admin.get(BASE).status_code == 401
    assert providers.create().status_code == 401


def test_provider_concurrent_edits_have_exactly_one_winner(providers: ProviderFixture) -> None:
    from concurrent.futures import ThreadPoolExecutor

    response = providers.create()
    assert response.status_code == 201
    item = response.json()
    version = providers.rbac.version()

    def edit(name: str):
        return providers.admin.patch(
            f"{BASE}/{item['id']}",
            headers={"Origin": ORIGIN, "X-CSRF-Token": providers.rbac.csrf["SUPER_ADMIN"]},
            json={
                "expected_policy_version": version,
                "expected_config_version": item["config_version"],
                "confirm": True,
                "name": name,
            },
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(edit, ("并发一", "并发二")))
    assert sorted(result.status_code for result in results) == [200, 409]
    winner = next(result.json() for result in results if result.status_code == 200)
    assert providers.admin.get(f"{BASE}/{item['id']}").json()["name"] == winner["name"]
    with Connection.connect(postgres_conninfo(providers.rbac.auth.settings)) as connection:
        assert connection.execute("SELECT count(*) FROM provider_config_versions").fetchone() == (2,)
