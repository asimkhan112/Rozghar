"""Binary asset storage.

An interface with one implementation today. Generated cards live on local disk
because there is no object store yet and no domain to serve one from; inventing
either now would be guessing at infrastructure that does not exist.

The seam is small and deliberate: `Storage` has four methods, and swapping in
S3 or R2 later is one class, not a refactor. What must *not* happen is
`open(path, "wb")` scattered through the service layer, because that is the
version that cannot be swapped.
"""

from app.storage.base import Storage, StoredAsset
from app.storage.local import LocalStorage, get_storage

__all__ = ["LocalStorage", "Storage", "StoredAsset", "get_storage"]
