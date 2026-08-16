"""The storage contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class StoredAsset:
    """Where an asset lives, in terms both the database and the API can use."""

    #: Storage-relative key, e.g. `social/job_<id>_square.png`. This is what is
    #: persisted — never an absolute path, which would break the moment the
    #: deployment directory changes.
    key: str
    size_bytes: int
    content_type: str


class Storage(Protocol):
    async def write(self, key: str, data: bytes, *, content_type: str) -> StoredAsset: ...

    async def read(self, key: str) -> bytes | None: ...

    async def exists(self, key: str) -> bool: ...

    async def delete(self, key: str) -> bool: ...
