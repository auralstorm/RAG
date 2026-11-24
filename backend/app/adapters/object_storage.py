"""S3 protocol client lifecycle; the maintained minio SDK also supports RustFS."""

from collections.abc import Generator
from contextlib import contextmanager

import urllib3
from minio import Minio

from app.core.config import Settings


@contextmanager
def open_s3_client(settings: Settings) -> Generator[Minio]:
    """Open a bounded local S3 client and release its pool even on failure."""
    pool = urllib3.PoolManager(
        timeout=urllib3.Timeout(connect=settings.dependency_timeout, read=settings.dependency_timeout),
        retries=False,
    )
    try:
        yield Minio(
            settings.object_storage_endpoint,
            access_key=settings.object_storage_access_key.get_secret_value() or None,
            secret_key=settings.object_storage_secret_key.get_secret_value() or None,
            secure=False,
            region="us-east-1",
            http_client=pool,
        )
    finally:
        pool.clear()
