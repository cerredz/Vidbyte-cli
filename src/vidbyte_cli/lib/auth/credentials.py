"""Secret-safe credential models and the keyring-first store the rest of the CLI talks to.

The key is a `SecretStr`, so it stays out of reprs, logs, and model dumps by default;
`secret_value()` and `FileCredentialStore._encode` are the only two deliberate unwrappings.

The restricted file is a fallback, never a default. It stores a key readable by anything
running as this user, so `CredentialStore.write` refuses it unless the caller passes explicit
consent — a decision that belongs to the person logging in, not to this layer.
"""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, field_validator

from ..config.atomic import AtomicFileWriter
from ..config.models import DEFAULT_API_URL, DEFAULT_PROFILE
from ..config.paths import VidbytePaths
from ..errors.failures import (
    LegacyCredentialRemovalFailed,
    LegacyCredentialSymlink,
    LegacyCredentialUnreadable,
    NoApprovedCredentialStore,
    StoredCredentialUnreadable,
)
from .keyring_store import CredentialScope, KeyringCredentialStore

# Bounds a hostile or accidentally-redirected file before it is parsed into memory.
_MAX_CREDENTIAL_BYTES = 1_000_000
_MAX_KEY_CHARACTERS = 4096
# The only prefix the backend gatekeeper extracts. A key without it yields no candidate at
# all, so the request is not rejected as malformed — it is treated as unauthenticated.
LIVE_API_KEY_PREFIX = "vb_live_"


class Credentials(BaseModel):
    """One opaque Vidbyte API token with secret-safe representation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    api_key: SecretStr

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, value: SecretStr) -> SecretStr:
        if not 1 <= len(value.get_secret_value()) <= _MAX_KEY_CHARACTERS:
            raise ValueError("API key must contain between 1 and 4096 characters")
        return value

    @classmethod
    def from_value(cls, value: str) -> Credentials:
        return cls(api_key=SecretStr(value))

    @classmethod
    def is_live_format(cls, value: str) -> bool:
        # Asked at the input boundaries only. Making it a field invariant would make a stored
        # non-live key unreadable, and so unremovable by the logout that exists to clear it.
        return value.startswith(LIVE_API_KEY_PREFIX)

    def secret_value(self) -> str:
        return self.api_key.get_secret_value()


class CredentialStorage(StrEnum):
    """Durable storage selected for a verified login."""

    KEYRING = "keyring"
    RESTRICTED_FILE = "restricted_file"


class CredentialDocument(BaseModel):
    """Version-one restricted fallback file."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    entries: dict[str, SecretStr] = Field(default_factory=dict)


class FileCredentialStore:
    """Permission-restricted fallback store, never an automatic first choice."""

    def __init__(self, paths: VidbytePaths, writer: AtomicFileWriter | None = None) -> None:
        self._paths = paths
        self._writer = writer or AtomicFileWriter()

    def read(self, profile: str, api_url: str) -> Credentials | None:
        secret = self._load().entries.get(CredentialScope(profile, api_url).account)
        if secret is not None:
            return Credentials(api_key=secret)
        return self._read_legacy_unscoped(profile, api_url)

    def write(self, credentials: Credentials, profile: str, api_url: str) -> None:
        document = self._load()
        entries = dict(document.entries)
        entries[CredentialScope(profile, api_url).account] = credentials.api_key
        self._writer.write(
            self._paths.credentials_file(),
            self._encode(CredentialDocument(entries=entries)),
        )

    def clear(self, profile: str, api_url: str) -> bool:
        document = self._load()
        account = CredentialScope(profile, api_url).account
        if account not in document.entries:
            return False
        entries = dict(document.entries)
        del entries[account]
        self._writer.write(
            self._paths.credentials_file(),
            self._encode(CredentialDocument(entries=entries)),
        )
        return True

    def clear_legacy(self, profile: str, api_url: str) -> bool:
        # Logout is an explicit destructive request. Unlike migration, which preserves the
        # legacy tree, it must ensure an old unscoped token cannot become effective again
        # once the scoped stores are empty.
        if profile != DEFAULT_PROFILE or api_url != DEFAULT_API_URL:
            return False
        path = self._paths.legacy_credentials_file()
        if not path.exists():
            return False
        if path.is_symlink():
            raise LegacyCredentialSymlink()
        try:
            path.unlink()
        except OSError as error:
            raise LegacyCredentialRemovalFailed(error) from error
        return True

    def _load(self) -> CredentialDocument:
        path = self._paths.credentials_file()
        if not path.exists():
            return CredentialDocument()
        try:
            raw = path.read_bytes()
            if len(raw) > _MAX_CREDENTIAL_BYTES:
                raise ValueError("credential file exceeds the size limit")
            parsed = json.loads(raw)
            if isinstance(parsed, dict) and parsed.get("schema_version", 1) != 1:
                raise ValueError("unsupported credential schema")
            return CredentialDocument.model_validate(parsed)
        except (OSError, json.JSONDecodeError, ValidationError, ValueError) as error:
            raise StoredCredentialUnreadable(error) from error

    def _read_legacy_unscoped(self, profile: str, api_url: str) -> Credentials | None:
        # The legacy file predates scoping, so it can only answer for the default scope.
        if profile != DEFAULT_PROFILE or api_url != DEFAULT_API_URL:
            return None
        path = self._paths.legacy_credentials_file()
        if not path.exists():
            return None
        try:
            raw = path.read_bytes()
            if len(raw) > _MAX_CREDENTIAL_BYTES:
                raise ValueError("legacy credential file exceeds the size limit")
            return Credentials.model_validate(json.loads(raw))
        except (OSError, json.JSONDecodeError, ValidationError, ValueError) as error:
            raise LegacyCredentialUnreadable(error) from error

    def _encode(self, document: CredentialDocument) -> bytes:
        # SecretStr's JSON serializer redacts values, which is right everywhere except here:
        # this is the one intentional unwrapping point for the restricted credential file.
        payload = {
            "schema_version": document.schema_version,
            "entries": {
                account: secret.get_secret_value() for account, secret in document.entries.items()
            },
        }
        return json.dumps(payload, indent=2, sort_keys=True).encode("utf-8") + b"\n"


class CredentialStore:
    """Keyring-first durable credential facade."""

    def __init__(
        self,
        keyring_store: KeyringCredentialStore | None = None,
        file_store: FileCredentialStore | None = None,
        paths: VidbytePaths | None = None,
    ) -> None:
        resolved_paths = paths or VidbytePaths.default()
        self.keyring = keyring_store or KeyringCredentialStore()
        self.file = file_store or FileCredentialStore(resolved_paths)

    def read(
        self,
        profile: str = DEFAULT_PROFILE,
        api_url: str = DEFAULT_API_URL,
    ) -> Credentials | None:
        return self.keyring.read(profile, api_url) or self.file.read(profile, api_url)

    def write(
        self,
        credentials: Credentials,
        profile: str = DEFAULT_PROFILE,
        api_url: str = DEFAULT_API_URL,
        *,
        allow_file_fallback: bool = False,
    ) -> CredentialStorage:
        if self.keyring.available():
            self.keyring.write(credentials, profile, api_url)
            return CredentialStorage.KEYRING
        if not allow_file_fallback:
            raise NoApprovedCredentialStore()
        self.file.write(credentials, profile, api_url)
        return CredentialStorage.RESTRICTED_FILE

    def clear(
        self,
        profile: str = DEFAULT_PROFILE,
        api_url: str = DEFAULT_API_URL,
    ) -> bool:
        # Every store is cleared, not just the first that answers: a stale entry left in one
        # of them would keep authenticating after the user asked to be logged out.
        keyring_cleared = self.keyring.clear(profile, api_url)
        file_cleared = self.file.clear(profile, api_url)
        legacy_cleared = self.file.clear_legacy(profile, api_url)
        return keyring_cleared or file_cleared or legacy_cleared
