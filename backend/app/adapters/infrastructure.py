"""Local dependency probes; this module owns SDK clients and their lifetime."""

import asyncio
from contextlib import ExitStack
from typing import Literal

import aio_pika
import httpx2
import redis.asyncio as redis
from minio import Minio
from pydantic import BaseModel

from app.adapters.object_storage import open_s3_client
from app.adapters.postgres import postgres_transaction
from app.core.config import Settings
from app.core.observability import MetricSink
from app.core.readiness import ReadinessReport, check_dependencies


class ElasticsearchHealth(BaseModel):
    status: Literal["green", "yellow", "red"]
    timed_out: bool = False


class InfrastructureMonitor:
    """Reuse HTTP/Redis pools and close short-lived SQL and AMQP probe connections."""

    def __init__(self, settings: Settings, metrics: MetricSink | None = None) -> None:
        self.settings = settings
        self.metrics = metrics
        self.http: httpx2.AsyncClient | None = None
        self.redis: redis.Redis | None = None
        self.storage_context = ExitStack()
        self.object_storage: Minio | None = None

    async def start(self) -> None:
        settings = self.settings
        if not settings.infrastructure_enabled:
            return
        self.http = httpx2.AsyncClient(timeout=settings.dependency_timeout, trust_env=False)
        self.redis = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            password=settings.redis_password.get_secret_value(),
            socket_timeout=settings.dependency_timeout,
            socket_connect_timeout=settings.dependency_timeout,
            decode_responses=True,
        )
        self.object_storage = self.storage_context.enter_context(open_s3_client(settings))

    async def close(self) -> None:
        if self.http is not None:
            await self.http.aclose()
        if self.redis is not None:
            await self.redis.aclose()
        self.storage_context.close()

    async def check(self) -> ReadinessReport:
        checks = (
            {
                "postgres": self.check_postgres,
                "redis": self.check_redis,
                "rabbitmq": self.check_rabbitmq,
                "elasticsearch": self.check_elasticsearch,
                "object_storage": self.check_object_storage,
                "phoenix": self.check_phoenix,
            }
            if self.settings.infrastructure_enabled
            else {}
        )
        return await check_dependencies(
            checks,
            self.settings.dependency_timeout,
            record=self.metrics.dependency if self.metrics is not None else None,
        )

    async def sample_metrics(self) -> None:
        """Bound read-only sampling; an unavailable source has no fabricated zero measurement."""
        if self.metrics is None:
            return
        if not self.settings.infrastructure_enabled:
            self.metrics.dependency("configuration", False, 0)
            self.metrics.postgres_connections(None)
            return

        async def connections() -> None:
            count = None
            try:
                count = await asyncio.wait_for(self.count_postgres_connections(), self.settings.dependency_timeout)
            except Exception:
                count = None
            if self.metrics is not None:
                self.metrics.postgres_connections(count)

        async def messages(queue: str) -> None:
            count = None
            try:
                count = await asyncio.wait_for(self.count_queue_messages(queue), self.settings.dependency_timeout)
            except Exception:
                count = None
            if self.metrics is not None:
                self.metrics.queue_messages(queue, count)

        await asyncio.gather(self.check(), connections(), *(messages(name) for name in self.settings.telemetry_queues))

    async def count_postgres_connections(self) -> int:
        async with postgres_transaction(self.settings) as connection:
            await connection.execute(
                "SELECT set_config('statement_timeout', %s, true)", (str(int(self.settings.dependency_timeout * 1000)),)
            )
            cursor = await connection.execute(
                "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid()"
            )
            row = await cursor.fetchone()
            if row is None:
                raise RuntimeError("Connection observation is unavailable")
            return int(row[0])

    async def count_queue_messages(self, queue: str) -> int:
        settings = self.settings
        connection = await aio_pika.connect(
            host=settings.rabbitmq_host,
            port=settings.rabbitmq_port,
            login=settings.rabbitmq_user,
            password=settings.rabbitmq_password.get_secret_value(),
            timeout=settings.dependency_timeout,
        )
        async with connection:
            async with await connection.channel() as channel:
                observed = await channel.declare_queue(queue, passive=True)
                count = observed.declaration_result.message_count
                if count is None:
                    raise RuntimeError("Queue observation is unavailable")
                return count

    async def check_postgres(self) -> None:
        async with postgres_transaction(self.settings) as connection:
            cursor = await connection.execute("SELECT 1")
            if await cursor.fetchone() != (1,):
                raise RuntimeError("PostgreSQL probe did not return the expected result")

    async def check_redis(self) -> None:
        if self.redis is None:
            raise RuntimeError("Redis probe client has not started")
        # Redis annotates unused **kwargs as unknown; its awaited PING result is bool.
        available = await self.redis.ping()  # pyright: ignore[reportUnknownMemberType]
        if not available:
            raise RuntimeError("Redis probe did not return PONG")

    async def check_rabbitmq(self) -> None:
        settings = self.settings
        connection = await aio_pika.connect(
            host=settings.rabbitmq_host,
            port=settings.rabbitmq_port,
            login=settings.rabbitmq_user,
            password=settings.rabbitmq_password.get_secret_value(),
            timeout=settings.dependency_timeout,
        )
        async with connection:
            await connection.channel()

    async def check_elasticsearch(self) -> None:
        if self.http is None:
            raise RuntimeError("HTTP probe client has not started")
        response = await self.http.get(
            f"{str(self.settings.elasticsearch_url).rstrip('/')}/_cluster/health",
            params={"wait_for_status": "yellow", "timeout": "1s"},
        )
        response.raise_for_status()
        health = ElasticsearchHealth.model_validate(response.json())
        if health.status == "red" or health.timed_out:
            raise RuntimeError("Elasticsearch is not ready")

    async def check_object_storage(self) -> None:
        if self.object_storage is None:
            raise RuntimeError("Object storage probe client has not started")
        if not await asyncio.to_thread(self.object_storage.bucket_exists, self.settings.object_storage_bucket):
            raise RuntimeError("Object storage initialization is incomplete")

    async def check_phoenix(self) -> None:
        if self.http is None:
            raise RuntimeError("HTTP probe client has not started")
        response = await self.http.get(f"{str(self.settings.phoenix_url).rstrip('/')}/healthz")
        response.raise_for_status()
