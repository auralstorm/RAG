"""Real S3 compatibility checks used by the disposable infrastructure acceptance."""

import asyncio
import hashlib
from datetime import UTC, datetime, timedelta
from io import BytesIO
from urllib.parse import urlsplit, urlunsplit

import httpx2
from app.core.config import Settings
from minio import Minio


async def verify_storage_protocol(store: Minio, settings: Settings, marker: str) -> None:
    """Check metadata, multipart integrity, presigning and unauthorized requests."""
    bucket = settings.object_storage_bucket
    object_name = f"p0-verify/{marker}-multipart.bin"
    # Exceeds the S3 5 MiB minimum part size: the SDK must complete two parts.
    payload = b"rustfs-s3-compatibility\n" * 300_000
    digest = hashlib.sha256(payload).hexdigest()
    await asyncio.to_thread(
        store.put_object,
        bucket,
        object_name,
        BytesIO(payload),
        len(payload),
        content_type="application/octet-stream",
        metadata={"sha256": digest},
        part_size=5 * 1024 * 1024,
    )
    metadata = await asyncio.to_thread(store.stat_object, bucket, object_name)
    assert metadata.size == len(payload)
    assert metadata.content_type == "application/octet-stream"
    assert metadata.metadata is not None
    assert metadata.metadata["x-amz-meta-sha256"] == digest
    response = await asyncio.to_thread(store.get_object, bucket, object_name)
    try:
        assert hashlib.sha256(response.read()).hexdigest() == digest
    finally:
        response.close()
        response.release_conn()

    upload_key = f"p0-verify/{marker}-presigned.txt"
    upload_url = await asyncio.to_thread(store.presigned_put_object, bucket, upload_key, expires=timedelta(minutes=1))
    download_url = await asyncio.to_thread(store.presigned_get_object, bucket, upload_key, expires=timedelta(minutes=1))
    expired_url = await asyncio.to_thread(
        store.presigned_get_object,
        bucket,
        upload_key,
        expires=timedelta(minutes=1),
        request_date=datetime.now(UTC) - timedelta(minutes=2),
    )
    async with httpx2.AsyncClient(trust_env=False, timeout=10) as http:
        uploaded = await http.put(upload_url, content=marker.encode())
        assert uploaded.status_code == 200
        downloaded = await http.get(download_url)
        assert downloaded.status_code == 200
        assert downloaded.content == marker.encode()
        assert (await http.get(expired_url)).status_code == 403
        split = urlsplit(download_url)
        tampered = urlunsplit(split._replace(path=split.path + "-other-key"))
        assert (await http.get(tampered)).status_code == 403
        assert (await http.get(f"http://{settings.object_storage_endpoint}/{bucket}/{upload_key}")).status_code == 403
        assert (await http.get(upload_url)).status_code == 403
        injected = await http.put(
            upload_url, headers={"x-amz-copy-source": f"/{bucket}/{object_name}"}, content=b"injected"
        )
        assert injected.status_code == 403
        assert (await http.get(download_url)).content == marker.encode()
        await asyncio.to_thread(store.remove_object, bucket, upload_key)
        assert (await http.get(download_url)).status_code == 404
    await asyncio.to_thread(store.remove_object, bucket, object_name)
    empty_key = f"p0-verify/{marker}-empty"
    await asyncio.to_thread(store.put_object, bucket, empty_key, BytesIO(b""), 0)
    assert (await asyncio.to_thread(store.stat_object, bucket, empty_key)).size == 0
    await asyncio.to_thread(store.remove_object, bucket, empty_key)
