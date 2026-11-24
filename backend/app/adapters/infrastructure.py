"""Local dependency probes; this module owns SDK clients and their lifetime."""

import asyncio
from typing import Literal

import aio_pika
import httpx2
import redis.asyncio as redis
import urllib3
from minio import Minio
from psycopg import AsyncConnection
from psycopg.conninfo import make_conninfo
from pydantic import BaseModel

from app.core.config import Settings
from app.core.readiness import ReadinessReport, check_dependencies


class ElasticsearchHealth(BaseModel):
    status: Literal["green", "yellow", "red"]
    timed_out: bool = False


class InfrastructureMonitor:
    """Reuse HTTP/Redis pools and close short-lived SQL and AMQP probe connections."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.http: httpx2.AsyncClient | None = None
        self.redis: redis.Redis | None = None
        self.minio_http: urllib3.PoolManager | None = None
        self.minio: Minio | None = None

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
        self.minio_http = urllib3.PoolManager(
            timeout=urllib3.Timeout(connect=settings.dependency_timeout, read=settings.dependency_timeout),
            retries=False,
        )
        self.minio = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key.get_secret_value() or None,
            secret_key=settings.minio_secret_key.get_secret_value() or None,
            secure=False,
            region="us-east-1",
            http_client=self.minio_http,
        )

    async def close(self) -> None:
        if self.http is not None:
            await self.http.aclose()
        if self.redis is not None:
            await self.redis.aclose()
        if self.minio_http is not None:
            self.minio_http.clear()

    async def check(self) -> ReadinessReport:
        checks = (
            {
                "postgres": self.check_postgres,
                "redis": self.check_redis,
                "rabbitmq": self.check_rabbitmq,
                "elasticsearch": self.check_elasticsearch,
                "minio": self.check_minio,
                "phoenix": self.check_phoenix,
            }
            if self.settings.infrastructure_enabled
            else {}
        )
        return await check_dependencies(checks, self.settings.dependency_timeout)

    async def check_postgres(self) -> None:
        settings = self.settings
        conninfo = make_conninfo(
            host=settings.postgres_host,
            port=str(settings.postgres_port),
            user=settings.postgres_user,
            password=settings.postgres_password.get_secret_value(),
            dbname=settings.postgres_database,
            connect_timeout=str(max(1, int(settings.dependency_timeout))),
        )
        async with await AsyncConnection.connect(conninfo) as connection:
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

    async def check_minio(self) -> None:
        if self.minio is None:
            raise RuntimeError("MinIO probe client has not started")
        if not await asyncio.to_thread(self.minio.bucket_exists, self.settings.minio_bucket):
            raise RuntimeError("MinIO initialization is incomplete")

    async def check_phoenix(self) -> None:
        if self.http is None:
            raise RuntimeError("HTTP probe client has not started")
        response = await self.http.get(f"{str(self.settings.phoenix_url).rstrip('/')}/healthz")
        response.raise_for_status()
