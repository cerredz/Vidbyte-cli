"""Secret-safe provider credential model and file document.

The key is a SecretStr so it stays out of reprs and dumps by default.
Scopes are profile@provider, not profile@host, so Vidbyte and provider keys never collide.
"""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, field_validator

from ...types.provider import PROVIDER_KEY_PREFIXES, Provider
from ..config.atomic import AtomicFileWriter
from ..config.paths import VidbytePaths
from ..errors.failures import StoredProviderCredentialUnreadable
from .keyring_store import CredentialScope  # noqa: F401 - re-export scope concept reference

_MAX_CREDENTIAL_BYTES = 1_000_000
_MAX_KEY_CHARACTERS = 4096


class ProviderCredentials(BaseModel):
    """One provider API token with secret-safe representation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: Provider
    api_key: SecretStr

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, value: SecretStr) -> SecretStr:
        # Bounds before any network or storage write.
        if not 1 <= len(value.get_secret_value()) <= _MAX_KEY_CHARACTERS:
            raise ValueError("API key must contain between 1 and 4096 characters")
        return value

    @classmethod
    def is_live_format(cls, provider: Provider, value: str) -> bool:
        # Prefix: openai/deepseek sk- not sk-ant-; claude sk-ant-; muse LLM|; gemini AIza.
        if provider == Provider.CLAUDE:
            return value.startswith("sk-ant-")
        if provider in (Provider.OPENAI, Provider.DEEPSEEK):
            return value.startswith("sk-") and not value.startswith("sk-ant-")
        if provider == Provider.MUSE:
            return value.startswith("LLM|")
        if provider == Provider.GEMINI:
            return value.startswith("AIza")
        if provider in (Provider.GROK, Provider.GLM):
            return bool(value)
        prefixes = PROVIDER_KEY_PREFIXES.get(provider, ())
        if not prefixes:
            return bool(value)
        return any(value.startswith(prefix) for prefix in prefixes)

    def secret_value(self) -> str:
        # Single deliberate unwrapping point outside the file encoder.
        return self.api_key.get_secret_value()


class ProviderStorage(StrEnum):
    """Durable storage selected for a verified provider login."""

    KEYRING = "keyring"
    RESTRICTED_FILE = "restricted_file"


class ProviderDocument(BaseModel):
    """Version-one restricted fallback file for provider keys."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    entries: dict[str, SecretStr] = Field(default_factory=dict)


class ProviderScope:
    """The profile and provider that one stored secret belongs to."""

    def __init__(self, profile: str, provider: Provider) -> None:
        # Minimal scope; provider is already a closed StrEnum.
        self.profile = profile
        self.provider = provider

    @property
    def account(self) -> str:
        # Mirrors CredentialScope but keyed by provider name.
        return f"{self.profile}@{self.provider.value}"


class FileProviderStore:
    """Permission-restricted fallback store for provider keys."""

    def __init__(self, paths: VidbytePaths, writer: AtomicFileWriter | None = None) -> None:
        # Paths injected so tests can point at a temp directory.
        self._paths = paths
        self._writer = writer or AtomicFileWriter()

    def read(self, profile: str, provider: Provider) -> ProviderCredentials | None:
        # Looks up one entry; missing file means no stored key.
        secret = self._load().entries.get(ProviderScope(profile, provider).account)
        if secret is None:
            return None
        return ProviderCredentials(provider=provider, api_key=secret)

    def write(self, credentials: ProviderCredentials, profile: str, provider: Provider) -> None:
        # Inserts or replaces one entry and rewrites the whole file atomically.
        document = self._load()
        entries = dict(document.entries)
        entries[ProviderScope(profile, provider).account] = credentials.api_key
        self._writer.write(
            self._paths.provider_credentials_file(),
            self._encode(ProviderDocument(entries=entries)),
        )

    def clear(self, profile: str, provider: Provider) -> bool:
        # Removes one entry if present; no-op otherwise.
        document = self._load()
        account = ProviderScope(profile, provider).account
        if account not in document.entries:
            return False
        entries = dict(document.entries)
        del entries[account]
        self._writer.write(
            self._paths.provider_credentials_file(),
            self._encode(ProviderDocument(entries=entries)),
        )
        return True

    def _load(self) -> ProviderDocument:
        # Reads and validates the whole file, bounded before parsing.
        path = self._paths.provider_credentials_file()
        if not path.exists():
            return ProviderDocument()
        try:
            raw = path.read_bytes()
            if len(raw) > _MAX_CREDENTIAL_BYTES:
                raise ValueError("credential file exceeds the size limit")
            parsed = json.loads(raw)
            if isinstance(parsed, dict) and parsed.get("schema_version", 1) != 1:
                raise ValueError("unsupported credential schema")
            return ProviderDocument.model_validate(parsed)
        except (OSError, json.JSONDecodeError, ValidationError, ValueError) as error:
            raise StoredProviderCredentialUnreadable(error) from error

    def _encode(self, document: ProviderDocument) -> bytes:
        # One intentional unwrapping point for the restricted file.
        payload = {
            "schema_version": document.schema_version,
            "entries": {
                account: secret.get_secret_value() for account, secret in document.entries.items()
            },
        }
        return json.dumps(payload, indent=2, sort_keys=True).encode("utf-8") + b"\n"
