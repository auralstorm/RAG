"""Exercise real disposable Docker services, their failure paths and volume lifecycle."""

import asyncio
from contextlib import ExitStack
from io import BytesIO
from uuid import uuid4

import aio_pika
import httpx2
import pytest
import redis.asyncio as redis
from app.adapters.object_storage import open_s3_client
from app.adapters.postgres import postgres_conninfo, postgres_transaction
from app.core.config import Settings, load_settings
from app.main import create_app
from fastapi.testclient import TestClient
from psycopg import AsyncConnection, sql
from tests.iam_schema import verify_iam_schema
from tests.storage_protocol import verify_storage_protocol

from scripts.infrastructure import compose, initialize_config, reset, up
from scripts.migrate_database import run_migration

pytestmark = [pytest.mark.infrastructure, pytest.mark.anyio]


async def verify_database_foundation(settings: Settings) -> None:
    database_name = f"p1_verify_{uuid4().hex}"
    identifier = sql.Identifier(database_name)
    async with await AsyncConnection.connect(postgres_conninfo(settings), autocommit=True) as admin:
        await admin.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(identifier))
        try:
            isolated = settings.model_copy(update={"postgres_database": database_name})
            assert await asyncio.to_thread(run_migration, isolated, "current") == ""
            await asyncio.to_thread(run_migration, isolated, "upgrade")
            await asyncio.to_thread(run_migration, isolated, "upgrade")
            assert await asyncio.to_thread(run_migration, isolated, "current") == "0002_iam_audit (head)"
            await verify_iam_schema(isolated)

            async with postgres_transaction(isolated) as connection:
                await connection.execute("CREATE TABLE transaction_probe (value text NOT NULL)")
                await connection.execute("INSERT INTO transaction_probe VALUES (%s)", ("committed",))
            assert connection.closed

            with pytest.raises(ValueError, match="rollback probe"):
                async with postgres_transaction(isolated) as connection:
                    await connection.execute("INSERT INTO transaction_probe VALUES (%s)", ("rolled back",))
                    raise ValueError("rollback probe")
            assert connection.closed

            async with postgres_transaction(isolated) as connection:
                rows = await connection.execute("SELECT value FROM transaction_probe")
                assert await rows.fetchall() == [("committed",)]

            await asyncio.to_thread(run_migration, isolated, "downgrade", "base")
            assert await asyncio.to_thread(run_migration, isolated, "current") == ""
            async with postgres_transaction(isolated) as connection:
                cursor = await connection.execute(
                    "SELECT to_regclass('public.users'), to_regclass('public.audit_events')"
                )
                assert await cursor.fetchone() == (None, None)
            await asyncio.to_thread(run_migration, isolated, "upgrade")
            assert await asyncio.to_thread(run_migration, isolated, "current") == "0002_iam_audit (head)"
        finally:
            await admin.execute(sql.SQL("DROP DATABASE {}").format(identifier))


async def rabbit_connection(settings: Settings) -> aio_pika.abc.AbstractConnection:
    return await aio_pika.connect(
        host=settings.rabbitmq_host,
        port=settings.rabbitmq_port,
        login=settings.rabbitmq_user,
        password=settings.rabbitmq_password.get_secret_value(),
    )


async def test_environment_persistence_outages_and_reset() -> None:
    initialize_config("test")
    settings = load_settings("test")
    marker = uuid4().hex
    queue_name = f"p0_verify_{marker}"
    index_name = f"p0-verify-{marker}"
    object_name = f"p0-verify/{marker}.txt"
    cache = redis.Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        password=settings.redis_password.get_secret_value(),
        decode_responses=True,
    )
    storage_context = ExitStack()
    store = storage_context.enter_context(open_s3_client(settings))
    try:
        up("test")
        await verify_database_foundation(settings)
        await verify_storage_protocol(store, settings, marker)
        with TestClient(create_app(settings)) as api:
            report = api.get("/health/ready")
            assert report.status_code == 200, report.text
            assert all(report.json()["dependencies"].values())

        async with postgres_transaction(settings) as connection:
            await connection.execute("CREATE TABLE IF NOT EXISTS p0_probe (id text PRIMARY KEY)")
            await connection.execute("INSERT INTO p0_probe VALUES (%s)", (marker,))
        await cache.set(f"p0:verify:{marker}", marker)
        connection = await rabbit_connection(settings)
        async with connection:
            channel = await connection.channel(publisher_confirms=True)
            await channel.declare_queue(queue_name, durable=True)
            await channel.default_exchange.publish(
                aio_pika.Message(body=marker.encode(), delivery_mode=aio_pika.DeliveryMode.PERSISTENT),
                routing_key=queue_name,
            )
        async with httpx2.AsyncClient(trust_env=False) as http:
            response = await http.put(
                f"{str(settings.elasticsearch_url).rstrip('/')}/{index_name}",
                json={"settings": {"number_of_shards": 1, "number_of_replicas": 0}},
            )
            response.raise_for_status()
            response = await http.put(
                f"{str(settings.elasticsearch_url).rstrip('/')}/{index_name}/_doc/probe?refresh=true",
                json={"value": marker},
            )
            response.raise_for_status()
        await asyncio.to_thread(
            store.put_object, settings.object_storage_bucket, object_name, BytesIO(marker.encode()), len(marker)
        )

        compose("test", "down")
        up("test")

        async with postgres_transaction(settings) as connection:
            cursor = await connection.execute("SELECT id FROM p0_probe WHERE id=%s", (marker,))
            assert await cursor.fetchone() == (marker,)
        assert await cache.get(f"p0:verify:{marker}") == marker
        connection = await rabbit_connection(settings)
        async with connection:
            channel = await connection.channel()
            queue = await channel.declare_queue(queue_name, durable=True)
            message = await queue.get(timeout=5)
            assert message is not None
            async with message.process():
                assert message.body.decode() == marker
        async with httpx2.AsyncClient(trust_env=False) as http:
            response = await http.get(f"{str(settings.elasticsearch_url).rstrip('/')}/{index_name}/_doc/probe")
            response.raise_for_status()
            assert response.json()["_source"]["value"] == marker
        response = await asyncio.to_thread(store.get_object, settings.object_storage_bucket, object_name)
        try:
            assert response.read().decode() == marker
        finally:
            response.close()
            response.release_conn()

        with TestClient(create_app(settings)) as api:
            for service in ("postgres", "redis", "rabbitmq", "elasticsearch", "rustfs", "phoenix"):
                compose("test", "stop", service)
                report = api.get("/health/ready")
                assert report.status_code == 503, (service, report.text)
                assert report.json()["dependencies"]["object_storage" if service == "rustfs" else service] is False
                assert settings.postgres_password.get_secret_value() not in report.text
                assert api.get("/health/live").status_code == 200
                up("test")
                assert api.get("/health/ready").status_code == 200

        reset("test", confirmed=True)
        async with postgres_transaction(settings) as connection:
            cursor = await connection.execute("SELECT to_regclass('public.p0_probe')")
            assert await cursor.fetchone() == (None,)
        assert await cache.get(f"p0:verify:{marker}") is None
        with TestClient(create_app(settings)) as api:
            assert api.get("/health/ready").status_code == 200
    finally:
        storage_context.close()
        await cache.aclose()
        compose("test", "down", "--volumes")
