"""Reads and writes the user's Vidbyte API key at ~/.vidbyte/credentials.json.

The key is a secret: it must never be logged or included in error messages.
"""

from __future__ import annotations

from pydantic import BaseModel

from ...lib.errors.failures import NotImplementedFeature


class Credentials(BaseModel):
    api_key: str


class CredentialStore:
    def read(self) -> Credentials | None:
        # Returns stored credentials, or None when the user has never logged in.
        raise NotImplementedFeature("credential store reads")

    def write(self, credentials: Credentials) -> None:
        # Persists credentials with owner-only file permissions where supported.
        raise NotImplementedFeature("credential store writes")

    def clear(self) -> None:
        # Deletes stored credentials; safe to call when none exist.
        raise NotImplementedFeature("credential store clearing")
