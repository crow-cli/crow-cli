"""Image stores: content-addressed blob backends for message images.

Images never live in the database — ``memory.messages`` extracts inline
base64 blocks at write time into a store keyed by ``<sha256hex><ext>``
(content-addressed, so dupes dedupe for free) and hydrates them back to
data URLs at read time. The store is the seam: filesystem by default,
S3 (RustFS) when configured and reachable — ``resolve_image_store`` probes
once at init and falls back to the filesystem when the endpoint is down.
"""

import logging
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

log = logging.getLogger(__name__)

#: Probe/connect timeouts (seconds) — a dead endpoint must not stall startup.
S3_CONNECT_TIMEOUT = 2.0
S3_READ_TIMEOUT = 10.0


@runtime_checkable
class ImageStore(Protocol):
    """Content-addressed blob store. Keys are ``<sha256hex><ext>``."""

    def put(self, key: str, data: bytes) -> None:
        """Store bytes under key; idempotent (same content = same key)."""
        ...

    def get(self, key: str) -> bytes | None:
        """Return bytes for key, or None when absent."""
        ...

    def exists(self, key: str) -> bool: ...


class FsImageStore:
    """The original design: files under a directory, one per blob."""

    def __init__(self, images_dir: Path):
        self.images_dir = Path(images_dir)

    def put(self, key: str, data: bytes) -> None:
        self.images_dir.mkdir(parents=True, exist_ok=True)
        path = self.images_dir / key
        if not path.exists():
            path.write_bytes(data)

    def get(self, key: str) -> bytes | None:
        path = self.images_dir / key
        if path.exists():
            return path.read_bytes()
        return None

    def exists(self, key: str) -> bool:
        return (self.images_dir / key).exists()


class S3ImageStore:
    """S3-backed store (RustFS or any S3 endpoint). Sync boto3 client — the
    async layer wraps calls in asyncio.to_thread."""

    def __init__(
        self,
        endpoint: str,
        bucket: str,
        access_key: str,
        secret_key: str,
        region: str = "us-east-1",
    ):
        import boto3
        from botocore.client import Config as BotoConfig
        from botocore.exceptions import ClientError

        self.endpoint = endpoint
        self.bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            config=BotoConfig(
                connect_timeout=S3_CONNECT_TIMEOUT,
                read_timeout=S3_READ_TIMEOUT,
                retries={"max_attempts": 1},
            ),
        )
        # Probe + bootstrap: head_bucket proves reachability AND auth;
        # create the bucket when it simply doesn't exist yet.
        try:
            self._client.head_bucket(Bucket=bucket)
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            if code in ("404", "NoSuchBucket"):
                self._client.create_bucket(Bucket=bucket)
            else:
                raise

    def put(self, key: str, data: bytes) -> None:
        self._client.put_object(Bucket=self.bucket, Key=key, Body=data)

    def get(self, key: str) -> bytes | None:
        from botocore.exceptions import ClientError

        try:
            resp = self._client.get_object(Bucket=self.bucket, Key=key)
            return resp["Body"].read()
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
                return None
            raise

    def exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self._client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError:
            return False


class HybridReadStore:
    """Writes go to the primary (S3); reads fall back to the filesystem so
    images stored before the switch keep hydrating forever. Zero migration."""

    def __init__(self, primary: ImageStore, fallback: ImageStore):
        self.primary = primary
        self.fallback = fallback

    def put(self, key: str, data: bytes) -> None:
        self.primary.put(key, data)

    def get(self, key: str) -> bytes | None:
        data = self.primary.get(key)
        if data is None:
            data = self.fallback.get(key)
        return data

    def exists(self, key: str) -> bool:
        return self.primary.exists(key) or self.fallback.exists(key)


def resolve_image_store(s3_config: dict[str, Any] | None, images_dir: Path) -> ImageStore:
    """Pick the image store ONCE at init. s3 configured + reachable → S3 with
    FS read-fallback; anything else → plain filesystem. Logs the decision."""
    if s3_config and s3_config.get("endpoint"):
        try:
            s3 = S3ImageStore(
                endpoint=s3_config["endpoint"],
                bucket=s3_config.get("bucket", "crow-images"),
                access_key=s3_config.get("access_key", ""),
                secret_key=s3_config.get("secret_key", ""),
            )
            log.info(
                "image store: S3 %s/%s (filesystem read-fallback for legacy images)",
                s3_config["endpoint"],
                s3.bucket,
            )
            return HybridReadStore(s3, FsImageStore(images_dir))
        except Exception as e:
            log.warning(
                "image store: S3 endpoint %s unreachable (%s) — falling back "
                "to filesystem images at %s",
                s3_config.get("endpoint"),
                e,
                images_dir,
            )
    return FsImageStore(images_dir)
