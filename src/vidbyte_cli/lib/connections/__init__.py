"""Local OAuth connections to context providers.

The package keeps token storage and provider protocol behavior behind a connection manager so
commands can stay thin and machine-readable.
"""

from .manager import ConnectionManager
from .store import ConnectionKeyringStore, ConnectionMetadataStore, ConnectionStore

__all__ = [
    "ConnectionKeyringStore",
    "ConnectionManager",
    "ConnectionMetadataStore",
    "ConnectionStore",
]
