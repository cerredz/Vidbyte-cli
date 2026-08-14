"""The versioned, allow-listed shape of everything the CLI is willing to persist.

`extra="forbid"` everywhere is deliberate: a typo in a hand-edited config file surfaces as a
rejection rather than a setting that silently does nothing. `schema_version` is a `Literal`
for the same reason — a future document is refused, never guessed at.

Nothing here reads the environment or the filesystem, and no field may hold a secret;
`ResolvedConfig` is the non-secret half of an invocation, `lib/auth` owns the other half.
"""

from __future__ import annotations

import ipaddress
from enum import StrEnum
from typing import Annotated, Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator

from ..output import ColorMode, OutputFormat

DEFAULT_API_URL = "https://vidbyte-backend.onrender.com"
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


class ApiOrigin:
    """The scheme/host/port an API base URL is allowed to be, parsed and re-rendered.

    A base URL is an origin. Userinfo, a query, a fragment, or a path on one is either a
    mistake or an attempt to redirect requests, so each is rejected rather than dropped — a
    silently truncated URL sends credentials somewhere the caller never named.

    Loopback detection lives here rather than beside it because the question is only ever
    asked to decide whether cleartext HTTP is acceptable for this exact origin.
    """

    def __init__(self, scheme: str, host: str, port: int | None) -> None:
        self.scheme = scheme
        self.host = host
        self.port = port

    @classmethod
    def parse(cls, value: str) -> ApiOrigin:
        parsed = urlsplit(value.strip())
        if parsed.scheme not in {"http", "https"} or parsed.hostname is None:
            raise ValueError("API URL must be an absolute HTTP or HTTPS origin")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("API URL cannot contain credentials, a query, or a fragment")
        if parsed.path not in {"", "/"}:
            raise ValueError("API URL cannot contain a path")
        origin = cls(parsed.scheme, parsed.hostname.lower(), parsed.port)
        if origin.scheme == "http" and not origin.is_loopback:
            raise ValueError("HTTP API URLs are restricted to loopback development hosts")
        return origin

    @classmethod
    def normalize(cls, value: str) -> str:
        # The pydantic entry point: validating and canonicalizing are one operation.
        return str(cls.parse(value))

    @property
    def is_loopback(self) -> bool:
        if self.host == "localhost":
            return True
        try:
            return ipaddress.ip_address(self.host).is_loopback
        except ValueError:
            return False

    def __str__(self) -> str:
        # urlsplit strips the brackets an IPv6 literal needs to sit in a netloc; put them back.
        host = f"[{self.host}]" if ":" in self.host else self.host
        netloc = f"{host}:{self.port}" if self.port is not None else host
        return urlunsplit((self.scheme, netloc, "", "", ""))


NormalizedApiUrl = Annotated[str, AfterValidator(ApiOrigin.normalize)]


class ProfileConfig(BaseModel):
    """Non-secret settings owned by one named CLI profile."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    api_url: NormalizedApiUrl = DEFAULT_API_URL
    output_format: OutputFormat = OutputFormat.HUMAN
    color: ColorMode = ColorMode.AUTO
    request_timeout_seconds: float = Field(default=30.0, ge=1.0, le=300.0)

    @classmethod
    def default_map(cls) -> dict[str, ProfileConfig]:
        # A document always carries at least the default profile, so a fresh install
        # resolves exactly like one that has been written to.
        return {DEFAULT_PROFILE: cls()}


class ConfigDocument(BaseModel):
    """Version-one persisted config document."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    active_profile: ProfileName = DEFAULT_PROFILE
    profiles: dict[ProfileName, ProfileConfig] = Field(default_factory=ProfileConfig.default_map)

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
