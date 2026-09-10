"""Typed contracts for named context-provider connections.

Connection tokens are secret-bearing values that stay inside the connection subsystem. Metadata,
identities, resources, and reads intentionally contain only provider data safe to render.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, SecretStr, StrictInt, field_validator


class ConnectionProvider(StrEnum):
    """Context providers supported by the local connection commands."""

    GITHUB = "github"
    SLACK = "slack"
    GOOGLE_DRIVE = "google-drive"

    @classmethod
    def cli_choices(cls) -> tuple[str, ...]:
        # Keep the storage value explicit while accepting the concise Google CLI alias.
        return tuple(item.value for item in cls) + ("google",)

    @classmethod
    def from_cli(cls, value: str) -> ConnectionProvider:
        # Canonicalizes the user-facing Google alias before provider dispatch.
        return cls.GOOGLE_DRIVE if value == "google" else cls(value)


class ConnectionToken(BaseModel):
    """One OAuth token envelope stored only in the system keyring."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    access_token: SecretStr
    refresh_token: SecretStr | None = None
    token_type: str = "Bearer"
    expires_at: StrictInt | None = None
    provider_data: dict[str, str] = Field(default_factory=dict)

    @field_validator("access_token")
    @classmethod
    def validate_access_token(cls, value: SecretStr) -> SecretStr:
        # Keep the keyring payload bounded before any network operation.
        if not 1 <= len(value.get_secret_value()) <= 16_384:
            raise ValueError("access token must contain between 1 and 16384 characters")
        return value

    @field_validator("refresh_token")
    @classmethod
    def validate_refresh_token(cls, value: SecretStr | None) -> SecretStr | None:
        # Refresh tokens are optional but receive the same size bound as access tokens.
        if value is not None and not 1 <= len(value.get_secret_value()) <= 16_384:
            raise ValueError("refresh token must contain between 1 and 16384 characters")
        return value

    @field_validator("expires_at")
    @classmethod
    def validate_expiration(cls, value: int | None) -> int | None:
        # Provider expiry values are Unix seconds and must not be negative.
        if value is not None and value < 0:
            raise ValueError("token expiration cannot be negative")
        return value

    def access_secret(self) -> str:
        # This is the single deliberate access-token unwrap for HTTP authorization.
        return self.access_token.get_secret_value()

    def refresh_secret(self) -> str | None:
        # This is the single deliberate refresh-token unwrap for token refresh requests.
        return self.refresh_token.get_secret_value() if self.refresh_token is not None else None


class ConnectionMetadata(BaseModel):
    """Non-secret account and permission metadata for one named connection."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    profile: str
    provider: ConnectionProvider
    name: str
    account_id: str
    account_label: str | None = None
    workspace_id: str | None = None
    workspace_label: str | None = None
    scopes: tuple[str, ...] = ()
    token_type: str = "Bearer"
    expires_at: StrictInt | None = None
    storage: Literal["keyring"] = "keyring"

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        # Connection names are stable keyring identifiers, so normalization is forbidden.
        if not 1 <= len(value) <= 64:
            raise ValueError("connection name must contain between 1 and 64 characters")
        allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
        if any(character not in allowed for character in value):
            raise ValueError("connection name contains an unsupported character")
        return value

    @field_validator("account_id")
    @classmethod
    def validate_account_id(cls, value: str) -> str:
        # Provider identifiers are metadata, but an empty identifier is never a valid identity.
        if not value or len(value) > 512:
            raise ValueError("account identifier is invalid")
        return value

    @field_validator("scopes")
    @classmethod
    def validate_scopes(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        # Scope names are bounded to prevent provider response data growing local state.
        if len(value) > 128 or any(not 0 < len(scope) <= 256 for scope in value):
            raise ValueError("connection scopes are invalid")
        return tuple(dict.fromkeys(value))


class ConnectionDocument(BaseModel):
    """Versioned, secret-free metadata document."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    entries: tuple[ConnectionMetadata, ...] = ()


class ConnectionIdentity(BaseModel):
    """Provider identity returned after OAuth or a later identity check."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: ConnectionProvider
    account_id: str
    account_label: str | None = None
    workspace_id: str | None = None
    workspace_label: str | None = None
    scopes: tuple[str, ...] = ()


class ConnectionResource(BaseModel):
    """A bounded provider resource selected for a read operation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: ConnectionProvider
    resource_type: Literal["repo", "pull-request", "channel", "file"]
    identifier: str
    number: StrictInt | None = None
    limit: StrictInt = 50

    @field_validator("identifier")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        # Resource identifiers become URL path components or API parameters.
        if not 1 <= len(value) <= 512:
            raise ValueError("resource identifier must contain between 1 and 512 characters")
        return value

    @field_validator("limit")
    @classmethod
    def validate_limit(cls, value: int) -> int:
        # Every adapter can rely on one safe upper bound before making a request.
        if not 1 <= value <= 100:
            raise ValueError("resource limit must be between 1 and 100")
        return value


class ConnectionRead(BaseModel):
    """Secret-free result of one bounded provider read."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: ConnectionProvider
    resource_type: str
    identifier: str
    data: dict[str, JsonValue]
