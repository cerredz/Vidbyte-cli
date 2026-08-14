"""The dependency graph and presentation policy owned by exactly one invocation.

Commands reach services through here instead of module globals. Everything expensive is
built lazily, so `--help` and `--version` never touch the keyring, the config file, or the
network — a keyring lookup can pop an OS unlock dialog, which no help invocation may do.

Root options arrive through `configure()` before any command service exists — output policy
has to be settled before the first byte is written, and before an optional harness context
can capture the wrong OutputManager.

The environment is injected rather than read at each use, so a test or an embedding process
gets one place to control credential and configuration discovery.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from ..auth import (
    CredentialResolver,
    CredentialStore,
    CredentialVerifier,
    PendingCredentialVerifier,
)
from ..config import ConfigResolver, ConfigStore, ResolvedConfig, VidbytePaths
from ..config.migration import StateMigration
from ..config.models import DEFAULT_API_URL, DEFAULT_PROFILE
from ..errors.handler import ErrorHandler
from ..harness.context import HarnessContext
from ..io import IOStreams
from ..io.terminal import TerminalCapabilities, TerminalPolicy
from ..output.formats import ColorMode, OutputFormat
from ..output.manager import OutputManager, OutputPolicy


@dataclass(frozen=True)
class InvocationOptions:
    """Root presentation, profile, and API policy resolved before command execution."""

    output_format: OutputFormat = OutputFormat.HUMAN
    profile: str = DEFAULT_PROFILE
    api_url: str = DEFAULT_API_URL
    request_timeout_seconds: float = 30.0
    no_input: bool = False
    color: ColorMode = ColorMode.AUTO
    debug: bool = False


class ApplicationContext:
    """Invocation-scoped services, shared with commands via click's context object."""

    def __init__(
        self,
        streams: IOStreams,
        harness_factory: Callable[[], HarnessContext] | None = None,
        *,
        environment: Mapping[str, str] | None = None,
        paths: VidbytePaths | None = None,
        verifier_factory: Callable[[], CredentialVerifier] | None = None,
    ) -> None:
        # Construction stays side-effect free; factories run on first request only.
        self.streams = streams
        self.environment = dict(os.environ if environment is None else environment)
        self.options = InvocationOptions()
        self._resolved_config: ResolvedConfig | None = None
        self._paths = paths
        self._config_store: ConfigStore | None = None
        self._config_resolver: ConfigResolver | None = None
        self._credential_store: CredentialStore | None = None
        self._credential_resolver: CredentialResolver | None = None
        self._migration: StateMigration | None = None
        self._verifier_factory = verifier_factory or PendingCredentialVerifier
        self._verifier: CredentialVerifier | None = None
        self._output = self._build_output()
        self._errors = ErrorHandler(self._output)
        self._harness_factory = harness_factory or self._build_harness_context
        self._harness_context: HarnessContext | None = None

    def configure(self, options: InvocationOptions, config: ResolvedConfig) -> None:
        # The harness context captured the current OutputManager, so changing policy after
        # it exists would leave two managers disagreeing about the same streams.
        if self._harness_context is not None and options != self.options:
            raise RuntimeError("Invocation options cannot change after harness construction.")
        if options == self.options and config == self._resolved_config:
            return
        self.options = options
        self._resolved_config = config
        self._output = self._build_output()
        self._errors = ErrorHandler(self._output, debug=options.debug)

    def resolved_config(self) -> ResolvedConfig:
        # A command reached for configuration without going through the root callback,
        # which happens whenever Click short-circuits; resolve it on demand.
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
            self._migration = StateMigration(
                self.paths(),
                self.config_store(),
                self.credential_store().keyring,
            )
        return self._migration

    def credential_verifier(self) -> CredentialVerifier:
        if self._verifier is None:
            self._verifier = self._verifier_factory()
        return self._verifier

    def output(self) -> OutputManager:
        # Callers share one policy object so stdout cardinality stays enforceable.
        return self._output

    def error_handler(self) -> ErrorHandler:
        return self._errors

    def harness_context(self) -> HarnessContext:
        # One invocation reuses one graph, and never leaks it into the next run.
        if self._harness_context is None:
            self._harness_context = self._harness_factory()
        return self._harness_context

    def _build_output(self) -> OutputManager:
        # Terminal detection reruns whenever color or no-input preferences change.
        terminal_policy = TerminalPolicy(
            self.options.color,
            self.options.no_input,
            self.environment,
        )
        terminal = TerminalCapabilities.detect(self.streams, terminal_policy)
        return OutputManager(self.streams, OutputPolicy(self.options.output_format, terminal))

    def _build_harness_context(self) -> HarnessContext:
        # The harness adapter shares this invocation's output contract and credential scope.
        return HarnessContext.default(
            self._output,
            credentials=self.credential_resolver(),
            config=self.resolved_config(),
            paths=self.paths(),
        )
