"""FILE: src/vidbyte_cli/lib/auth/credentials.py

PURPOSE: Defines secret-safe credential models and the composite local store that prefers
the OS keyring and uses a permission-restricted file only after explicit caller consent.

ROLE IN CODEBASE: CredentialResolver reads through this boundary. Login writes a verified
token with an explicit fallback policy; logout clears the selected profile/API-host scope.

ARCHITECTURE NOTE: Credential scope is `<profile>@<normalized-api-host>`. SecretStr keeps
values out of repr/model output; secret_value() is the only deliberate unwrapping method.

FUNCTION INVENTORY (reviewed 2026-07-26):
- Credentials.secret_value() -> str: explicitly unwraps the token for auth headers.
- FileCredentialStore: reads/writes the restricted versioned fallback document.
- CredentialStore: keyring-first composite read/write/clear operations.

WHAT NOT TO DO IN THIS FILE:
1. Do not log, render, stringify, or include tokens in errors.
2. Do not write the fallback file unless allow_file_fallback is true.
3. Do not persist a token sourced implicitly from the environment.
4. Do not silently broaden credentials across profile/API-host scopes.

TESTS: No feature tests are added under the approved no-tests workflow.
"""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, field_validator

from ..config.atomic import AtomicFileWriter
from ..config.models import DEFAULT_API_URL, DEFAULT_PROFILE
from ..config.paths import VidbytePaths
from ..errors import CliError, CliErrorCode
from .keyring_store import KeyringCredentialStore, credential_account

_MAX_CREDENTIAL_BYTES = 1_000_000


class Credentials(BaseModel):
    """One opaque Vidbyte API token with secret-safe representation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    api_key: SecretStr

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, value: SecretStr) -> SecretStr:
        if not 1 <= len(value.get_secret_value()) <= 4096:
            raise ValueError("API key must contain between 1 and 4096 characters")
        return value

    @classmethod
    def from_value(cls, value: str) -> Credentials:
        return cls(api_key=SecretStr(value))

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

    def __init__(
        self,
        paths: VidbytePaths,
        writer: AtomicFileWriter | None = None,
    ) -> None:
        self._paths = paths
        self._writer = writer or AtomicFileWriter()

    def read(self, profile: str, api_url: str) -> Credentials | None:
        account = credential_account(profile, api_url)
        document = self._load()
        secret = document.entries.get(account)
        if secret is not None:
            return Credentials(api_key=secret)
        return self._read_legacy_unscoped(profile, api_url)

    def write(self, credentials: Credentials, profile: str, api_url: str) -> None:
        account = credential_account(profile, api_url)
        document = self._load()
        entries = dict(document.entries)
        entries[account] = credentials.api_key
        updated = CredentialDocument(entries=entries)
        self._writer.write(self._paths.credentials_file(), self._encode(updated))

    def clear(self, profile: str, api_url: str) -> bool:
        path = self._paths.credentials_file()
        document = self._load()
        account = credential_account(profile, api_url)
        if account not in document.entries:
            return False
        entries = dict(document.entries)
        del entries[account]
        updated = CredentialDocument(entries=entries)
        self._writer.write(path, self._encode(updated))
        return True

    def clear_legacy(self, profile: str, api_url: str) -> bool:
        # Logout is an explicit destructive request; unlike migration, it must ensure a
        # legacy token cannot become effective after the scoped stores are cleared.
        if profile != DEFAULT_PROFILE or api_url != DEFAULT_API_URL:
            return False
        path = self._paths.legacy_credentials_file()
        if not path.exists():
            return False
        if path.is_symlink():
            raise CliError(
                CliErrorCode.CREDENTIAL_STORE_UNAVAILABLE,
                "Refusing to remove legacy credentials through a symbolic link.",
                hint="Remove the symbolic link manually after verifying its target.",
            )
        try:
            path.unlink()
        except OSError as error:
            raise CliError(
                CliErrorCode.CREDENTIAL_STORE_UNAVAILABLE,
                "Legacy credentials could not be removed.",
                hint="Check the legacy file permissions and retry logout.",
                cause=error,
            ) from error
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
            raise CliError(
                CliErrorCode.CREDENTIAL_STORE_UNAVAILABLE,
                "Stored CLI credentials are invalid or unavailable.",
                hint="Move the fallback credential file and run 'vidbyte-cli login' again.",
                cause=error,
            ) from error

    def _read_legacy_unscoped(self, profile: str, api_url: str) -> Credentials | None:
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
            raise CliError(
                CliErrorCode.CREDENTIAL_STORE_UNAVAILABLE,
                "Legacy CLI credentials are invalid or unavailable.",
                hint="Run 'vidbyte-cli login' to replace the stored credential.",
                cause=error,
            ) from error

    def _encode(self, document: CredentialDocument) -> bytes:
        # SecretStr's normal JSON serializer redacts values; this is the one intentional
        # unwrapping point for the permission-restricted credential file.
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
        keyring_value = self.keyring.read(profile, api_url)
        return keyring_value or self.file.read(profile, api_url)

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
            raise CliError(
                CliErrorCode.CREDENTIAL_STORE_UNAVAILABLE,
                "No usable OS credential store is available.",
                hint="Retry login and explicitly approve the restricted-file fallback.",
            )
        self.file.write(credentials, profile, api_url)
        return CredentialStorage.RESTRICTED_FILE

    def clear(
        self,
        profile: str = DEFAULT_PROFILE,
        api_url: str = DEFAULT_API_URL,
    ) -> bool:
        keyring_cleared = self.keyring.clear(profile, api_url)
        file_cleared = self.file.clear(profile, api_url)
        legacy_cleared = self.file.clear_legacy(profile, api_url)
        return keyring_cleared or file_cleared or legacy_cleared
