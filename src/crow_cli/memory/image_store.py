"""Image stores: content-addressed blob backends for message images.

Images never live in the database — ``memory.messages`` extracts inline
base64 blocks at write time into a store keyed by ``<sha256hex><ext>``
(content-addressed, so dupes dedupe for free) and hydrates them back to
data URLs at read time. The store is the seam: filesystem today (default),
S3 (RustFS) when configured and reachable — see Phase 3.
"""

from pathlib import Path
from typing import Protocol, runtime_checkable


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
