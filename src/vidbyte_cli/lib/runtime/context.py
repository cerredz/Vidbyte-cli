"""FILE: src/vidbyte_cli/lib/runtime/context.py

PURPOSE: Owns one invocation's dependencies, resolved policy, and presentation boundaries.
Filesystem, credential, migration, verifier, and harness collaborators are all lazy.

ROLE IN CODEBASE: CliApplication creates ApplicationContext and places it in Click context.
Thin commands request typed services from it; no process-global dependency graph exists.

ARCHITECTURE NOTE: Construction and command registration remain side-effect free. Reading
configuration occurs during root policy resolution; credentials and migration are deferred
until a command explicitly requests them.

FUNCTION INVENTORY (reviewed 2026-07-26):
- InvocationOptions: immutable effective root policy.
- configure(options, resolved_config) -> None: binds validated invocation policy.
- config_store()/credential_store()/migration(): lazy platform services.
- output()/error_handler()/harness_context(): invocation presentation/runtime services.

WHAT NOT TO DO IN THIS FILE:
1. Do not execute command use cases or API calls.
2. Do not instantiate keyring, stores, or harness services at module import time.
3. Do not retain dependencies across invocations.
4. Do not resolve or persist environment credentials here.

TESTS: No feature tests are added under the approved no-tests workflow. scripts/smoke.py
exercises lazy help and command composition.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from ..api.client import ApiClient
from ..api.endpoints.auth import AuthEndpoints
from ..api.endpoints.harness import HarnessEndpoints
from ..auth import (
    ApiCredentialVerifier,
    CredentialResolver,
    CredentialStore,
    CredentialVerifier,
)
from ..config import (
    ConfigResolver,
    ConfigStore,
    ResolvedConfig,
    VidbytePaths,
)
from ..config.migration import StateMigration
from ..errors.handler import ErrorHandler
from ..harness.context import HarnessContext
from ..io import IOStreams
from ..io.terminal import TerminalCapabilities, TerminalPolicy
from ..output.formats import ColorMode, OutputFormat
from ..output.manager import OutputManager, OutputPolicy

_HarnessFactory = Callable[[], HarnessContext]
_VerifierFactory = Callable[[], CredentialVerifier]


@dataclass(frozen=True)
class InvocationOptions:
    """Effective root presentation, profile, and API policy."""

    output_format: OutputFormat = OutputFormat.HUMAN
    profile: str = "default"
    api_url: str = "https://api.vidbyte.ai"
    request_timeout_seconds: float = 30.0
    no_input: bool = False
    color: ColorMode = ColorMode.AUTO
    debug: bool = False


class ApplicationContext:
    """Invocation-owned lazy dependency graph shared through Click context."""

    def __init__(
        self,
        streams: IOStreams,
        factory: _HarnessFactory | None = None,
        *,
        environment: Mapping[str, str] | None = None,
        paths: VidbytePaths | None = None,
        verifier_factory: _VerifierFactory | None = None,
    ) -> None:
        self.streams = streams
        self.environment = dict(os.environ if environment is None else environment)
        self.options = InvocationOptions()
        self._resolved_config: ResolvedConfig | None = None
        self._paths = paths
        self._config_store: ConfigStore | None = None
        self._config_resolver: ConfigResolver | None = None
        self._credential_store: CredentialStore | None = None
        self._credential_resolver: CredentialResolver | None = None
        self._api_client: ApiClient | None = None
        self._migration: StateMigration | None = None
        self._verifier_factory = verifier_factory or ApiCredentialVerifier
        self._verifier: CredentialVerifier | None = None
        self._output = self._build_output()
        self._errors = ErrorHandler(self._output)
        self._harness_factory = factory or self._build_harness_context
        self._harness_context: HarnessContext | None = None

    def configure(self, options: InvocationOptions, config: ResolvedConfig) -> None:
        if self._harness_context is not None and options != self.options:
            raise RuntimeError("Invocation options cannot change after harness construction.")
        if options == self.options and config == self._resolved_config:
            return
        self.options = options
        self._resolved_config = config
        self._output = self._build_output()
        self._errors = ErrorHandler(self._output, debug=options.debug)

    def resolved_config(self) -> ResolvedConfig:
        if self._resolved_config is None:
            self._resolved_config = self.config_resolver().resolve()
        return self._resolved_config

    def paths(self) -> VidbytePaths:
        if self._paths is None:
            self._paths = VidbytePaths.default()
        return self._paths

    def config_store(self) -> ConfigStore:
        if self._config_store is None:
            self._config_store = ConfigStore(self.paths())
        return self._config_store

    def config_resolver(self) -> ConfigResolver:
        if self._config_resolver is None:
            self._config_resolver = ConfigResolver(self.config_store(), self.environment)
        return self._config_resolver

    def credential_store(self) -> CredentialStore:
        if self._credential_store is None:
            self._credential_store = CredentialStore(paths=self.paths())
        return self._credential_store

    def credential_resolver(self) -> CredentialResolver:
        if self._credential_resolver is None:
            self._credential_resolver = CredentialResolver(
                self.credential_store(),
                self.environment,
            )
        return self._credential_resolver

    def migration(self) -> StateMigration:
        if self._migration is None:
            store = self.credential_store()
            self._migration = StateMigration(
                self.paths(),
                self.config_store(),
                store.keyring,
            )
        return self._migration

    def credential_verifier(self) -> CredentialVerifier:
        if self._verifier is None:
            self._verifier = self._verifier_factory()
        return self._verifier

    def api_client(self) -> ApiClient:
        if self._api_client is None:
            config = self.resolved_config()
            resolved = self.credential_resolver().resolve(config.profile, config.api_url)
            if resolved is None:
                from ..errors import CliError, CliErrorCode, ExitCode

                raise CliError(
                    CliErrorCode.AUTH_REQUIRED,
                    "Authentication is required.",
                    ExitCode.AUTHENTICATION,
                    hint="Run 'vidbyte-cli login' first.",
                )
            if resolved.source.value == "restricted_file":
                self.output().warning(
                    "Using credentials from the permission-restricted file fallback."
                )
            self._api_client = ApiClient(
                config.api_url,
                resolved.credentials.secret_value(),
                timeout_seconds=config.request_timeout_seconds,
                diagnostic=self.output().diagnostic if self.options.debug else None,
            )
        return self._api_client

    def auth_endpoints(self) -> AuthEndpoints:
        return AuthEndpoints(self.api_client())

    def harness_endpoints(self) -> HarnessEndpoints:
        return HarnessEndpoints(self.api_client())

    def output(self) -> OutputManager:
        return self._output

    def error_handler(self) -> ErrorHandler:
        return self._errors

    def harness_context(self) -> HarnessContext:
        if self._harness_context is None:
            self._harness_context = self._harness_factory()
        return self._harness_context

    def close(self) -> None:
        if self._api_client is not None:
            self._api_client.close()
            self._api_client = None

    def _build_output(self) -> OutputManager:
        terminal_policy = TerminalPolicy(
            self.options.color,
            self.options.no_input,
            self.environment,
        )
        terminal = TerminalCapabilities.detect(self.streams, terminal_policy)
        return OutputManager(self.streams, OutputPolicy(self.options.output_format, terminal))

    def _build_harness_context(self) -> HarnessContext:
        return HarnessContext.default(
            self._output,
            credentials=self.credential_store(),
            paths=self.paths(),
            base_url=self.options.api_url,
            profile=self.options.profile,
            endpoint_factory=self.harness_endpoints,
        )
