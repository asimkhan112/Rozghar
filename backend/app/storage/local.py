"""Local filesystem storage.

Adequate for a single instance and for development. Two instances behind a load
balancer would each hold their own copy — which is survivable for a derived,
regenerable asset like a social card, and would not be for anything else.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from app.core.config import settings
from app.storage.base import StoredAsset

logger = logging.getLogger(__name__)


class LocalStorage:
    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root or settings.storage_root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        """Resolve a key inside the root, refusing anything that escapes it.

        A key reaches this from a database row, and a row can be wrong. Without
        this check a value like `../../etc/passwd` would be a file write
        wherever the process has permission.
        """
        candidate = (self.root / key).resolve()
        if not candidate.is_relative_to(self.root):
            raise ValueError(f"storage key escapes the root: {key!r}")
        return candidate

    async def write(self, key: str, data: bytes, *, content_type: str) -> StoredAsset:
        path = self._resolve(key)

        def _write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            # Write beside, then rename. A reader that arrives mid-write gets
            # either the old file or the new one, never a half-written PNG —
            # rename is atomic within a filesystem.
            temporary = path.with_suffix(f"{path.suffix}.tmp")
            temporary.write_bytes(data)
            temporary.replace(path)

        await asyncio.to_thread(_write)
        return StoredAsset(key=key, size_bytes=len(data), content_type=content_type)

    async def read(self, key: str) -> bytes | None:
        path = self._resolve(key)

        def _read() -> bytes | None:
            return path.read_bytes() if path.is_file() else None

        return await asyncio.to_thread(_read)

    async def exists(self, key: str) -> bool:
        return await asyncio.to_thread(self._resolve(key).is_file)

    async def delete(self, key: str) -> bool:
        path = self._resolve(key)

        def _delete() -> bool:
            if not path.is_file():
                return False
            path.unlink()
            return True

        return await asyncio.to_thread(_delete)


_storage: LocalStorage | None = None


def get_storage() -> LocalStorage:
    """Process-wide storage handle."""
    global _storage
    if _storage is None:
        _storage = LocalStorage()
    return _storage
