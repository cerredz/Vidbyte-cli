"""Non-secret CLI settings at ~/.vidbyte/config.json."""

from __future__ import annotations

from ...lib.errors.cli_error import not_implemented


class ConfigStore:
    def get(self, key: str) -> str | None:
        # Returns the stored value for a config key, or None when unset.
        raise not_implemented("config store reads")

    def set(self, key: str, value: str) -> None:
        # Persists a config key/value pair, creating ~/.vidbyte on first write.
        raise not_implemented("config store writes")
