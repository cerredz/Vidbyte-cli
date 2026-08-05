"""Where one invocation's effective non-secret settings come from, and which layer won.

Precedence is command → environment → selected profile → default profile → built-in, and
every field records which of those supplied it. Provenance is not decoration: `config get`
reports the effective value, and without a source a user cannot tell a stored setting from
an environment variable they forgot was exported.

Resolution is read-only and deterministic for an injected environment — it never migrates,
never writes, and never touches a secret. `CredentialResolver` owns that separate order.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TypeVar

from pydantic import ValidationError

from ..errors.failures import InvalidConfigOverride
from ..output import ColorMode, OutputFormat
from .config import ConfigStore
from .models import (
    DEFAULT_API_URL,
    DEFAULT_PROFILE,
    ConfigField,
    ConfigSource,
    ProfileConfig,
    ResolvedConfig,
)

_T = TypeVar("_T")


@dataclass(frozen=True)
class ConfigOverrides:
    """Explicit root values that outrank environment and stored profiles."""

    profile: str | None = None
    api_url: str | None = None
    output_format: OutputFormat | None = None
    color: ColorMode | None = None
    request_timeout_seconds: float | None = None


class ConfigResolver:
    """Resolve typed invocation settings and retain how each value was chosen."""

    def __init__(self, store: ConfigStore, environment: Mapping[str, str]) -> None:
        self._store = store
        self._environment = environment

    def resolve(self, overrides: ConfigOverrides | None = None) -> ResolvedConfig:
        explicit = overrides or ConfigOverrides()
        snapshot = self._store.load()
        document = snapshot.document
        profile = explicit.profile or self._environment.get("VIDBYTE_PROFILE")
        profile = profile or document.active_profile or DEFAULT_PROFILE
        # With no file on disk the document is built-in defaults, so its profiles must not be
        # reported as a stored source the user could go and edit.
        stored = document.profiles if snapshot.path is not None else {}
        selected = stored.get(profile)
        default = stored.get(DEFAULT_PROFILE)
        base = selected or default or ProfileConfig()
        base_source = self._profile_source(selected, default)
        try:
            api_url, api_source = self._resolve_value(
                explicit.api_url,
                self._environment.get("VIDBYTE_API_URL"),
                base.api_url,
                base_source,
                str,
            )
            output, output_source = self._resolve_value(
                explicit.output_format,
                self._environment.get("VIDBYTE_OUTPUT_FORMAT"),
                base.output_format,
                base_source,
                OutputFormat,
            )
            color, color_source = self._resolve_value(
                explicit.color,
                self._environment.get("VIDBYTE_COLOR"),
                base.color,
                base_source,
                ColorMode,
            )
            timeout, timeout_source = self._resolve_value(
                explicit.request_timeout_seconds,
                self._environment.get("VIDBYTE_REQUEST_TIMEOUT_SECONDS"),
                base.request_timeout_seconds,
                base_source,
                float,
            )
            return ResolvedConfig(
                profile=profile,
                api_url=api_url or DEFAULT_API_URL,
                output_format=output,
                color=color,
                request_timeout_seconds=timeout,
                provenance={
                    ConfigField.API_URL: api_source,
                    ConfigField.OUTPUT_FORMAT: output_source,
                    ConfigField.COLOR: color_source,
                    ConfigField.REQUEST_TIMEOUT_SECONDS: timeout_source,
                },
                config_path=str(snapshot.path) if snapshot.path is not None else None,
            )
        except (ValidationError, ValueError) as error:
            raise InvalidConfigOverride(error) from error

    def _resolve_value(
        self,
        command: _T | None,
        environment: str | None,
        profile: _T,
        profile_source: ConfigSource,
        parser: Callable[[str], _T],
    ) -> tuple[_T, ConfigSource]:
        # An exported-but-empty variable is treated as unset; the alternative is a shell
        # that silently forces built-in defaults on every invocation.
        if command is not None:
            return command, ConfigSource.COMMAND
        if environment is not None and environment.strip():
            return parser(environment.strip()), ConfigSource.ENVIRONMENT
        return profile, profile_source

    def _profile_source(
        self,
        selected: ProfileConfig | None,
        default: ProfileConfig | None,
    ) -> ConfigSource:
        if selected is not None:
            return ConfigSource.SELECTED_PROFILE
        if default is not None:
            return ConfigSource.DEFAULT_PROFILE
        return ConfigSource.BUILT_IN
