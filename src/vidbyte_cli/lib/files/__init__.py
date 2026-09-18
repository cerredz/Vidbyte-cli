"""Public local-file contract: stores rooted at one directory, product-neutral."""

from .documents import LocalDocumentStore
from .store import LocalFileStore

__all__ = ["LocalDocumentStore", "LocalFileStore"]
