"""POC-08 uses disposable RustFS, synthetic users/objects and public S3/Admin APIs."""

import hashlib
import json
import secrets
import subprocess
import time
from collections.abc import Generator
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import version
from io import BytesIO
from pathlib import Path

import pytest
import urllib3
from app.adapters.object_storage import open_s3_client
from app.core.config import Settings, load_settings
from minio import Minio
from minio.commonconfig import ENABLED, Filter
from minio.credentials.providers import AssumeRoleProvider, StaticProvider
from minio.deleteobjects import DeleteObject
from minio.error import MinioAdminException, S3Error
from minio.lifecycleconfig import Expiration, LifecycleConfig, Rule
from minio.minioadmin import MinioAdmin
from pydantic import BaseModel, JsonValue, RootModel, SecretStr
from tests.storage_admin_cli import service_account

from scripts.infrastructure import initialize_config

pytestmark = pytest.mark.poc
ROOT = Path(__file__).resolve().parents[2]
PROJECT = "enterprise-rag-poc-storage"
BUCKET = "poc-permissions"
USER = "poc-scoped-user"


def poc_command(*arguments: str, restore: bool = False) -> list[str]:
    return [
        "docker",
        "compose",
        "--project-name",
        f"{PROJECT}-restore" if restore else PROJECT,
        "--file",
        str(ROOT / "infra/compose/storage-poc.yaml"),
        "--env-file",
        str(ROOT / "infra/compose/images.env"),
        "--env-file",
        str(ROOT / "infra/compose/.env.test"),
        *arguments,
    ]


def admin(settings: Settings, pool: urllib3.PoolManager) -> MinioAdmin:
    return MinioAdmin(
        endpoint=settings.object_storage_endpoint,
        secure=False,
        region="us-east-1",
        http_client=pool,
        credentials=StaticProvider(
            settings.object_storage_access_key.get_secret_value(), settings.object_storage_secret_key.get_secret_value()
        ),
    )


@dataclass
class StorageEnvironment:
    settings: Settings
    root: Minio
    administrator: MinioAdmin
    scoped_settings: Settings
    scoped: Minio
    directory: Path


@pytest.fixture(scope="module")
def storage_environment(tmp_path_factory: pytest.TempPathFactory) -> Generator[StorageEnvironment]:
    initialize_config("test")
    directory = tmp_path_factory.mktemp("rustfs-poc")
    settings = load_settings("test")
    scoped_settings = settings.model_copy(
        update={
            "object_storage_access_key": SecretStr(USER),
            "object_storage_secret_key": SecretStr(secrets.token_urlsafe(32)),
        }
    )
    pool = urllib3.PoolManager(timeout=urllib3.Timeout(connect=5, read=5), retries=False)
    try:
        subprocess.run(poc_command("up", "--detach", "--wait", "--wait-timeout", "240"), check=True)
        with ExitStack() as stack:
            root = stack.enter_context(open_s3_client(settings))
            scoped = stack.enter_context(open_s3_client(scoped_settings))
            administrator = admin(settings, pool)
            root.make_bucket(BUCKET)
            root.make_bucket("poc-outside-scope")
            root.put_object("poc-outside-scope", "document.txt", BytesIO(b"outside"), 7)
            root.put_object(BUCKET, "allowed/document.txt", BytesIO(b"synthetic allowed document"), 26)
            root.put_object(BUCKET, "blocked/document.txt", BytesIO(b"synthetic blocked document"), 26)
            policy = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
                        "Resource": [f"arn:aws:s3:::{BUCKET}/allowed/*"],
                    }
                ],
            }
            policy_file = directory / "scoped-policy.json"
            policy_file.write_text(json.dumps(policy))
            administrator.user_add(USER, scoped_settings.object_storage_secret_key.get_secret_value())
            # SDK's unused optional `policy: dict` is untyped; the input here is a JSON file.
            administrator.policy_add("poc-scoped-policy", policy_file=policy_file)  # pyright: ignore[reportUnknownMemberType]
            administrator.policy_set("poc-scoped-policy", user=USER)
            evidence = ROOT / ".poc-results/storage"
            evidence.mkdir(parents=True, exist_ok=True, mode=0o700)
            runtime = {
                "server_version": subprocess.check_output(
                    ["docker", "exec", f"{PROJECT}-rustfs-1", "rustfs", "--version"], text=True
                ).strip(),
                "client_version": f"minio=={version('minio')}",
                "server_image_id": subprocess.check_output(
                    ["docker", "inspect", "--format", "{{.Image}}", f"{PROJECT}-rustfs-1"], text=True
                ).strip(),
                "topology": "single node, single data volume, 2 GiB container limit",
            }
            (evidence / "environment.json").write_text(json.dumps(runtime, indent=2) + "\n")
            yield StorageEnvironment(settings, root, administrator, scoped_settings, scoped, directory)
    finally:
        pool.clear()
        subprocess.run(poc_command("down", "--volumes"), check=True)


def read_object(client: Minio, key: str, *, bucket: str = BUCKET) -> bytes:
    response = client.get_object(bucket, key)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


def test_scoped_credentials_can_only_read_their_allowed_prefix(storage_environment: StorageEnvironment) -> None:
    environment = storage_environment
    assert read_object(environment.scoped, "allowed/document.txt") == b"synthetic allowed document"
    with pytest.raises(S3Error) as refused:
        read_object(environment.scoped, "blocked/document.txt")
    assert refused.value.code == "AccessDenied"
    with pytest.raises(S3Error) as other_bucket:
        read_object(environment.scoped, "document.txt", bucket="poc-outside-scope")
    assert other_bucket.value.code == "AccessDenied"


def test_scoped_credentials_cannot_write_delete_or_administer_other_resources(
    storage_environment: StorageEnvironment,
) -> None:
    environment = storage_environment
    environment.scoped.put_object(BUCKET, "allowed/write.txt", BytesIO(b"allowed write"), 13)
    assert read_object(environment.scoped, "allowed/write.txt") == b"allowed write"
    for operation in (
        lambda: environment.scoped.put_object(BUCKET, "blocked/document.txt", BytesIO(b"wrong"), 5),
        lambda: environment.scoped.remove_object(BUCKET, "blocked/document.txt"),
        lambda: environment.scoped.put_object("poc-outside-scope", "document.txt", BytesIO(b"wrong"), 5),
    ):
        with pytest.raises(S3Error) as refused:
            operation()
        assert refused.value.code == "AccessDenied"
    assert read_object(environment.root, "blocked/document.txt") == b"synthetic blocked document"
    assert read_object(environment.root, "document.txt", bucket="poc-outside-scope") == b"outside"
    with urllib3.PoolManager(timeout=urllib3.Timeout(connect=5, read=5), retries=False) as pool:
        limited_admin = admin(environment.scoped_settings, pool)
        with pytest.raises(MinioAdminException, match="Status: 403"):
            limited_admin.user_list()


def test_batch_delete_returns_per_object_errors_and_keeps_other_prefix_intact(
    storage_environment: StorageEnvironment,
) -> None:
    environment = storage_environment
    environment.root.put_object(BUCKET, "allowed/batch.txt", BytesIO(b"batch"), 5)
    errors = list(
        environment.scoped.remove_objects(
            BUCKET,
            [
                DeleteObject("allowed/batch.txt"),
                DeleteObject("blocked/document.txt"),
            ],
        )
    )
    assert [(error.name, error.code) for error in errors] == [("blocked/document.txt", "AccessDenied")]
    with pytest.raises(S3Error) as removed:
        read_object(environment.root, "allowed/batch.txt")
    assert removed.value.code == "NoSuchKey"
    assert read_object(environment.root, "blocked/document.txt") == b"synthetic blocked document"
    traversal = list(environment.scoped.remove_objects(BUCKET, [DeleteObject("allowed/../blocked/document.txt")]))
    assert traversal
    assert read_object(environment.root, "blocked/document.txt") == b"synthetic blocked document"


def test_disabling_parent_credentials_revokes_access_and_can_be_restored(
    storage_environment: StorageEnvironment,
) -> None:
    environment = storage_environment
    environment.administrator.user_disable(USER)
    try:
        with pytest.raises(S3Error) as refused:
            read_object(environment.scoped, "allowed/document.txt")
        assert refused.value.code in ("AccessDenied", "InvalidAccessKeyId")
    finally:
        environment.administrator.user_enable(USER)
    assert read_object(environment.scoped, "allowed/document.txt") == b"synthetic allowed document"


def test_service_account_policy_is_intersected_with_parent_and_cross_owner_updates_are_denied(
    storage_environment: StorageEnvironment,
) -> None:
    environment = storage_environment
    child_key = "poc-scoped-service"
    child_secret = SecretStr(secrets.token_urlsafe(32))
    root_child_key = "poc-root-service"
    policy_file = environment.directory / "read-only-service.json"
    policy_file.write_text(
        json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": ["s3:GetObject"],
                        "Resource": [f"arn:aws:s3:::{BUCKET}/allowed/*"],
                    }
                ],
            }
        )
    )
    manager_settings = environment.settings.model_copy(
        update={
            "object_storage_access_key": SecretStr("poc-service-manager"),
            "object_storage_secret_key": SecretStr(secrets.token_urlsafe(32)),
        }
    )
    environment.administrator.user_add(
        "poc-service-manager", manager_settings.object_storage_secret_key.get_secret_value()
    )
    manager_policy = environment.directory / "service-manager-policy.json"
    manager_policy.write_text(
        json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
                        "Resource": [f"arn:aws:s3:::{BUCKET}/allowed/*"],
                    },
                    {
                        "Effect": "Allow",
                        "Action": ["admin:CreateServiceAccount", "admin:UpdateServiceAccount"],
                        "Resource": ["*"],
                    },
                ],
            }
        )
    )
    environment.administrator.policy_add("poc-service-manager-policy", policy_file=manager_policy)  # pyright: ignore[reportUnknownMemberType]
    environment.administrator.policy_set("poc-service-manager-policy", user="poc-service-manager")
    with urllib3.PoolManager(timeout=urllib3.Timeout(connect=5, read=5), retries=False) as pool:
        limited_admin = admin(environment.scoped_settings, pool)
        with pytest.raises(MinioAdminException, match="Status: 403"):
            limited_admin.add_service_account(  # pyright: ignore[reportUnknownMemberType]
                access_key="poc-unapproved-service",
                secret_key=secrets.token_urlsafe(32),
            )
        read_policy = RootModel[dict[str, JsonValue]].model_validate_json(policy_file.read_text()).root
        created = service_account(
            manager_settings, operation="create", target_key=child_key, target_secret=child_secret, policy=read_policy
        )
        assert created.returncode == 0, created.summary
        root_child_secret = SecretStr(secrets.token_urlsafe(32))
        root_created = service_account(
            environment.settings,
            operation="create",
            target_key=root_child_key,
            target_secret=root_child_secret,
            policy=read_policy,
        )
        assert root_created.returncode == 0, root_created.summary
        cross_created = service_account(
            manager_settings,
            operation="create",
            target_key="poc-cross-root-service",
            target_secret=SecretStr(secrets.token_urlsafe(32)),
            policy=read_policy,
            target_user=environment.settings.object_storage_access_key.get_secret_value(),
        )
        assert cross_created.returncode != 0
        assert "accessdenied" in cross_created.summary.lower() or "access denied" in cross_created.summary.lower()
        child_settings = environment.settings.model_copy(
            update={
                "object_storage_access_key": SecretStr(child_key),
                "object_storage_secret_key": child_secret,
            }
        )
        try:
            with open_s3_client(child_settings) as child:
                assert read_object(child, "allowed/document.txt") == b"synthetic allowed document"
                with pytest.raises(S3Error) as refused:
                    child.put_object(BUCKET, "allowed/no-write.txt", BytesIO(b"wrong"), 5)
                assert refused.value.code == "AccessDenied"
                policy_file.write_text(
                    json.dumps(
                        {
                            "Version": "2012-10-17",
                            "Statement": [
                                {
                                    "Effect": "Allow",
                                    "Action": ["s3:*"],
                                    "Resource": ["*"],
                                }
                            ],
                        }
                    )
                )
                broad_policy = RootModel[dict[str, JsonValue]].model_validate_json(policy_file.read_text()).root
                updated = service_account(
                    manager_settings,
                    operation="update",
                    target_key=child_key,
                    target_secret=child_secret,
                    policy=broad_policy,
                )
                assert updated.returncode == 0, updated.summary
                with pytest.raises(S3Error) as outside_parent:
                    read_object(child, "blocked/document.txt")
                assert outside_parent.value.code == "AccessDenied"
                environment.administrator.user_disable("poc-service-manager")
                try:
                    with pytest.raises(S3Error) as revoked:
                        read_object(child, "allowed/document.txt")
                    assert revoked.value.code in ("AccessDenied", "InvalidAccessKeyId")
                finally:
                    environment.administrator.user_enable("poc-service-manager")
            cross_updated = service_account(
                manager_settings,
                operation="update",
                target_key=root_child_key,
                target_secret=root_child_secret,
                policy=read_policy,
            )
            assert cross_updated.returncode != 0
            assert "accessdenied" in cross_updated.summary.lower() or "access denied" in cross_updated.summary.lower()
        finally:
            environment.administrator.delete_service_account(child_key)
            environment.administrator.delete_service_account(root_child_key)


def test_sts_session_policy_cannot_expand_parent_and_invalid_tokens_are_rejected(
    storage_environment: StorageEnvironment,
) -> None:
    environment = storage_environment
    broad = json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": ["s3:*"],
                    "Resource": ["*"],
                }
            ],
        }
    )
    with urllib3.PoolManager(timeout=urllib3.Timeout(connect=5, read=5), retries=False) as pool:
        provider = AssumeRoleProvider(
            sts_endpoint=f"http://{environment.settings.object_storage_endpoint}",
            access_key=USER,
            secret_key=environment.scoped_settings.object_storage_secret_key.get_secret_value(),
            policy=broad,
            region="us-east-1",
            http_client=pool,
        )
        credentials = provider.retrieve()
        assert credentials.session_token is not None
        assert credentials.expiration is not None and credentials.expiration > datetime.now(UTC).replace(tzinfo=None)
        session = Minio(
            environment.settings.object_storage_endpoint,
            secure=False,
            region="us-east-1",
            http_client=pool,
            credentials=StaticProvider(credentials.access_key, credentials.secret_key, credentials.session_token),
        )
        assert read_object(session, "allowed/document.txt") == b"synthetic allowed document"
        with pytest.raises(S3Error) as refused:
            read_object(session, "blocked/document.txt")
        assert refused.value.code == "AccessDenied"
        with pytest.raises(S3Error) as other_bucket:
            read_object(session, "document.txt", bucket="poc-outside-scope")
        assert other_bucket.value.code == "AccessDenied"
        for token in (None, credentials.session_token + "tampered"):
            invalid = Minio(
                environment.settings.object_storage_endpoint,
                secure=False,
                region="us-east-1",
                http_client=pool,
                credentials=StaticProvider(credentials.access_key, credentials.secret_key, token),
            )
            with pytest.raises(S3Error) as rejected:
                read_object(invalid, "allowed/document.txt")
            if rejected.value.code == "InvalidRequest":
                assert "invalid token" in (rejected.value.message or "").lower()
            else:
                assert rejected.value.code in ("AccessDenied", "InvalidToken", "InvalidAccessKeyId")
        environment.administrator.user_disable(USER)
        try:
            with pytest.raises(S3Error) as revoked:
                read_object(session, "allowed/document.txt")
            assert revoked.value.code in ("AccessDenied", "InvalidAccessKeyId")
        finally:
            environment.administrator.user_enable(USER)


def test_sts_read_only_session_restricts_parent_write_permission(storage_environment: StorageEnvironment) -> None:
    environment = storage_environment
    policy = json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {"Effect": "Allow", "Action": ["s3:GetObject"], "Resource": [f"arn:aws:s3:::{BUCKET}/allowed/*"]}
            ],
        }
    )
    with urllib3.PoolManager(timeout=urllib3.Timeout(connect=5, read=5), retries=False) as pool:
        provider = AssumeRoleProvider(
            sts_endpoint=f"http://{environment.settings.object_storage_endpoint}",
            access_key=USER,
            secret_key=environment.scoped_settings.object_storage_secret_key.get_secret_value(),
            policy=policy,
            region="us-east-1",
            http_client=pool,
        )
        credentials = provider.retrieve()
        session = Minio(
            environment.settings.object_storage_endpoint,
            secure=False,
            region="us-east-1",
            http_client=pool,
            credentials=StaticProvider(credentials.access_key, credentials.secret_key, credentials.session_token),
        )
        assert read_object(session, "allowed/document.txt") == b"synthetic allowed document"
        with pytest.raises(S3Error) as denied:
            session.put_object(BUCKET, "allowed/sts-denied.txt", BytesIO(b"wrong"), 5)
        assert denied.value.code == "AccessDenied"


def physical_parts() -> set[str]:
    """Inspect hashes of synthetic payload files, including RustFS trash, without exposing contents."""
    result = subprocess.check_output(
        [
            "docker",
            "exec",
            f"{PROJECT}-rustfs-1",
            "find",
            "/data",
            "-type",
            "f",
            "-name",
            "part.*",
            "-exec",
            "sha256sum",
            "{}",
            ";",
        ],
        text=True,
    )
    return {line.split()[0] for line in result.splitlines() if line.strip()}


def test_lifecycle_expiration_removes_target_payload_and_preserves_unmatched_objects(
    storage_environment: StorageEnvironment,
) -> None:
    environment = storage_environment
    bucket = "poc-lifecycle"
    environment.root.make_bucket(bucket)
    environment.root.put_object(bucket, "keep/document.txt", BytesIO(b"keep"), 4)
    before_parts = physical_parts()
    payload = b"rustfs-poc-lifecycle-payload\0" * 65536
    environment.root.put_object(bucket, "expire/payload.bin", BytesIO(payload), len(payload))
    assert read_object(environment.root, "expire/payload.bin", bucket=bucket) == payload
    allocated = physical_parts() - before_parts
    assert allocated, "The test must observe a physical payload before proving its cleanup"
    before_kib = int(
        subprocess.check_output(["docker", "exec", f"{PROJECT}-rustfs-1", "du", "-sk", "/data"], text=True).split()[0]
    )
    started = time.monotonic()
    environment.root.set_bucket_lifecycle(
        bucket,
        LifecycleConfig(
            [
                Rule(
                    ENABLED,
                    rule_filter=Filter(prefix="expire/"),
                    expiration=Expiration(days=1),
                    rule_id="poc-expiration",
                ),
            ]
        ),
    )
    expiry_seconds: float | None = None
    while time.monotonic() - started < 90:
        try:
            environment.root.stat_object(bucket, "expire/payload.bin")
        except S3Error as removed:
            assert removed.code == "NoSuchKey"
            expiry_seconds = round(time.monotonic() - started, 3)
            break
        time.sleep(2)
    assert expiry_seconds is not None, "Configured lifecycle must produce actual expiration in the accelerated POC"
    # Allow for delayed trash cleanup; logical expiration alone cannot prove reclaim.
    while time.monotonic() - started < 390 and allocated & physical_parts():
        time.sleep(5)
    assert not allocated & physical_parts(), "Expired object payload still occupies active/trash storage"
    after_kib = int(
        subprocess.check_output(["docker", "exec", f"{PROJECT}-rustfs-1", "du", "-sk", "/data"], text=True).split()[0]
    )
    assert after_kib < before_kib
    assert read_object(environment.root, "keep/document.txt", bucket=bucket) == b"keep"
    measurements = ROOT / ".poc-results/storage"
    measurements.mkdir(parents=True, exist_ok=True, mode=0o700)
    (measurements / "lifecycle.json").write_text(
        json.dumps(
            {
                "payload_bytes": len(payload),
                "payload_sha256": hashlib.sha256(payload).hexdigest(),
                "logical_expiration_seconds": expiry_seconds,
                "physical_cleanup_seconds": round(time.monotonic() - started, 3),
                "data_volume_kib_before": before_kib,
                "data_volume_kib_after": after_kib,
                "test_day_seconds": 5,
                "scanner_cycle_seconds": 2,
                "qualification": "Single-node accelerated test; not production retention timing or filesystem compaction proof",
            },
            indent=2,
        )
        + "\n"
    )


class BackupObject(BaseModel):
    """Manifest entry for a synthetic current object, excluding account credentials."""

    key: str
    filename: str
    size: int
    content_type: str
    metadata: dict[str, str]
    sha256: str


def test_s3_backup_restores_objects_metadata_and_scoped_policy_to_a_fresh_volume(
    storage_environment: StorageEnvironment,
) -> None:
    """Restore a synthetic current-object backup and replay one explicit IAM policy."""
    environment = storage_environment
    environment.root.put_object(
        BUCKET,
        "allowed/backup.bin",
        BytesIO(b"synthetic backup\0" * 65536),
        17 * 65536,
        content_type="application/octet-stream",
        metadata={"purpose": "backup-restore-poc"},
    )
    records: list[BackupObject] = []
    for index, item in enumerate(environment.root.list_objects(BUCKET, recursive=True)):
        assert item.object_name is not None
        metadata = environment.root.stat_object(BUCKET, item.object_name)
        payload = read_object(environment.root, item.object_name)
        filename = f"backup-{index}.bin"
        (environment.directory / filename).write_bytes(payload)
        records.append(
            BackupObject(
                key=item.object_name,
                filename=filename,
                size=len(payload),
                content_type=metadata.content_type or "application/octet-stream",
                metadata={
                    key.removeprefix("x-amz-meta-"): value
                    for key, value in (metadata.metadata or {}).items()
                    if key.lower().startswith("x-amz-meta-")
                },
                sha256=hashlib.sha256(payload).hexdigest(),
            )
        )
    manifest = environment.directory / "backup-manifest.json"
    manifest.write_text(RootModel[list[BackupObject]](records).model_dump_json(indent=2))
    subprocess.run(poc_command("stop", "rustfs"), check=True)
    try:
        subprocess.run(poc_command("up", "--detach", "--wait", "--wait-timeout", "240", restore=True), check=True)
        with open_s3_client(environment.settings) as restored:
            assert restored.list_buckets() == [], "Restore must begin with an empty independent volume"
            restored.make_bucket(BUCKET)
            restored_records = RootModel[list[BackupObject]].model_validate_json(manifest.read_text()).root
            for record in restored_records:
                payload = (environment.directory / record.filename).read_bytes()
                assert hashlib.sha256(payload).hexdigest() == record.sha256
                restored.put_object(
                    BUCKET,
                    record.key,
                    BytesIO(payload),
                    record.size,
                    content_type=record.content_type,
                    metadata={**record.metadata},
                )
            restored_keys: list[str] = []
            for item in restored.list_objects(BUCKET, recursive=True):
                assert item.object_name is not None
                restored_keys.append(item.object_name)
            assert sorted(restored_keys) == sorted(record.key for record in restored_records)
            for record in restored_records:
                assert hashlib.sha256(read_object(restored, record.key)).hexdigest() == record.sha256
                metadata = restored.stat_object(BUCKET, record.key)
                assert (metadata.size, metadata.content_type) == (record.size, record.content_type)
                assert all(
                    (metadata.metadata or {}).get(f"x-amz-meta-{key}") == value
                    for key, value in record.metadata.items()
                )
            # Recreate only this synthetic identity; no root keys or account export enter the backup.
            environment.administrator.user_add(
                USER, environment.scoped_settings.object_storage_secret_key.get_secret_value()
            )
            environment.administrator.policy_add(  # pyright: ignore[reportUnknownMemberType]
                "poc-scoped-policy", policy_file=environment.directory / "scoped-policy.json"
            )
            environment.administrator.policy_set("poc-scoped-policy", user=USER)
            with open_s3_client(environment.scoped_settings) as scoped:
                assert read_object(scoped, "allowed/document.txt") == b"synthetic allowed document"
                with pytest.raises(S3Error) as denied:
                    read_object(scoped, "blocked/document.txt")
                assert denied.value.code == "AccessDenied"
        evidence = ROOT / ".poc-results/storage/backup.json"
        evidence.write_text(
            json.dumps(
                {
                    "object_count": len(records),
                    "total_bytes": sum(record.size for record in records),
                    "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
                    "restored_to_empty_independent_volume": True,
                    "content_metadata_and_scoped_policy_verified": True,
                    "qualification": "Synthetic current objects and explicit policy replay only; versions, full IAM, encryption and production DR pending",
                },
                indent=2,
            )
            + "\n"
        )
    finally:
        try:
            subprocess.run(poc_command("down", "--volumes", restore=True), check=True)
        finally:
            subprocess.run(poc_command("up", "--detach", "--wait", "--wait-timeout", "240"), check=True)
    assert read_object(environment.root, "allowed/document.txt") == b"synthetic allowed document"
