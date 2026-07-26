"""FILE: src/vidbyte_cli/lib/config/models.py

PURPOSE: Defines the versioned, allow-listed configuration schema and the fully resolved
per-invocation configuration contract, including provenance for each effective value.

ROLE IN CODEBASE: ConfigStore validates persisted JSON with ConfigDocument. ConfigResolver
combines ProfileConfig values with command and environment overrides into ResolvedConfig.

ARCHITECTURE NOTE: API origins are normalized here and insecure HTTP is accepted only for
loopback development. Unknown fields are rejected to surface typos instead of ignoring them.

FUNCTION INVENTORY (reviewed 2026-07-26):
- ProfileConfig: one named profile's non-secret settings.
- ConfigDocument: schema-versioned persisted configuration.
- ConfigField/ConfigSource: stable field and provenance vocabularies.
- ResolvedConfig: immutable effective settings for one invocation.

WHAT NOT TO DO IN THIS FILE:
1. Do not add API keys, refresh tokens, prompts, or research data.
2. Do not access the environment or filesystem.
3. Do not silently accept future schema versions or unknown fields.
4. Do not allow cleartext HTTP for non-loopback hosts.

TESTS: No feature tests are added under the approved no-tests workflow.
"""

from __future__ import annotations

import ipaddress
from enum import StrEnum
from typing import Annotated, Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from ..output import ColorMode, OutputFormat

DEFAULT_API_URL = "https://api.vidbyte.ai"
DEFAULT_PROFILE = "default"
ProfileName = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")]


class ConfigField(StrEnum):
    """Public allow-list accepted by config get/set."""

    API_URL = "api_url"
    OUTPUT_FORMAT = "output_format"
    COLOR = "color"
    REQUEST_TIMEOUT_SECONDS = "request_timeout_seconds"


class ConfigSource(StrEnum):
    """Stable provenance values for effective non-secret settings."""

    COMMAND = "command"
    ENVIRONMENT = "environment"
    SELECTED_PROFILE = "selected_profile"
    DEFAULT_PROFILE = "default_profile"
    BUILT_IN = "built_in"


def _normalize_api_url(value: str) -> str:
    # Base URLs are origins; credentials, query strings, and fragments are never meaningful.
    candidate = value.strip()
    parsed = urlsplit(candidate)
    if parsed.scheme not in {"http", "https"} or parsed.hostname is None:
        raise ValueError("API URL must be an absolute HTTP or HTTPS origin")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("API URL cannot contain credentials, a query, or a fragment")
    if parsed.path not in {"", "/"}:
        raise ValueError("API URL cannot contain a path")
    if parsed.scheme == "http" and not _is_loopback(parsed.hostname):
        raise ValueError("HTTP API URLs are restricted to loopback development hosts")
    host = parsed.hostname.lower()
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    netloc = f"{host}:{parsed.port}" if parsed.port is not None else host
    return urlunsplit((parsed.scheme, netloc, "", "", ""))


def _is_loopback(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


NormalizedApiUrl = Annotated[str, AfterValidator(_normalize_api_url)]


class ProfileConfig(BaseModel):
    """Non-secret settings owned by one named CLI profile."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    api_url: NormalizedApiUrl = DEFAULT_API_URL
    output_format: OutputFormat = OutputFormat.HUMAN
    color: ColorMode = ColorMode.AUTO
    request_timeout_seconds: float = Field(default=30.0, ge=1.0, le=300.0)


def _default_profiles() -> dict[str, ProfileConfig]:
    return {DEFAULT_PROFILE: ProfileConfig()}


class ConfigDocument(BaseModel):
    """Version-one persisted config document."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    active_profile: ProfileName = DEFAULT_PROFILE
    profiles: dict[ProfileName, ProfileConfig] = Field(default_factory=_default_profiles)

    @field_validator("profiles")
    @classmethod
    def require_profiles(cls, value: dict[str, ProfileConfig]) -> dict[str, ProfileConfig]:
        if not value:
            raise ValueError("at least one profile is required")
        return value


class ResolvedConfig(BaseModel):
    """Effective non-secret policy and its source for one invocation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    profile: ProfileName
    api_url: NormalizedApiUrl
    output_format: OutputFormat
    color: ColorMode
    request_timeout_seconds: float = Field(ge=1.0, le=300.0)
    provenance: dict[ConfigField, ConfigSource]
    config_path: str | None = None
