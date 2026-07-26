"""FILE: src/vidbyte_cli/lib/config/resolver.py

PURPOSE: Resolves one invocation's effective non-secret settings from command options,
environment variables, selected/default profiles, and built-in defaults with provenance.

ROLE IN CODEBASE: CliApplication passes root overrides into ConfigResolver before command
execution. Commands and service factories consume the resulting immutable ResolvedConfig.

ARCHITECTURE NOTE: Resolution is read-only and deterministic for an injected environment.
Secrets are deliberately excluded; CredentialResolver owns their separate precedence.

FUNCTION INVENTORY (reviewed 2026-07-26):
- ConfigOverrides: optional root-command settings.
- ConfigResolver.resolve(overrides) -> ResolvedConfig: applies typed precedence.

WHAT NOT TO DO IN THIS FILE:
1. Do not read API keys or construct network clients.
2. Do not mutate or migrate configuration during resolution.
3. Do not treat an unknown profile as an error; it may be a credential-only scope.
4. Do not omit provenance when adding a new resolved field.

TESTS: No feature tests are added under the approved no-tests workflow.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TypeVar

from pydantic import ValidationError

from ..errors import CliError, CliErrorCode
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

    def __init__(
        self,
        store: ConfigStore,
        environment: Mapping[str, str],
    ) -> None:
        self._store = store
        self._environment = environment

    def resolve(self, overrides: ConfigOverrides | None = None) -> ResolvedConfig:
        explicit = overrides or ConfigOverrides()
        snapshot = self._store.load()
        document = snapshot.document
        profile = explicit.profile or self._environment.get("VIDBYTE_PROFILE")
        profile = profile or document.active_profile or DEFAULT_PROFILE
        selected = document.profiles.get(profile) if snapshot.path is not None else None
        default = document.profiles.get(DEFAULT_PROFILE) if snapshot.path is not None else None
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
            raise CliError(
                CliErrorCode.CONFIG_INVALID,
                "An environment or command configuration value is invalid.",
                hint="Check VIDBYTE_* settings and the selected CLI profile.",
                cause=error,
            ) from error

    def _resolve_value(
        self,
        command: _T | None,
        environment: str | None,
        profile: _T,
        profile_source: ConfigSource,
        parser: Callable[[str], _T],
    ) -> tuple[_T, ConfigSource]:
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
