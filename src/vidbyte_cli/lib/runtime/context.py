"""The dependency graph and presentation policy owned by exactly one invocation.

Commands reach services through here instead of module globals. Everything expensive is
built lazily, so `--help` and `--version` never touch the keyring, the config file, or the
network — a keyring lookup can pop an OS unlock dialog, which no help invocation may do.

Root options arrive through `configure()` before any command service exists, because output
policy has to be settled before the first byte is written.

The environment is injected rather than read at each use, so a test or an embedding process
gets one place to control credential and configuration discovery.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from ...types.provider import Provider
from ..api.client import ApiClient
from ..api.endpoints.research import ResearchEndpoints
from ..api.endpoints.runtime import RuntimeEndpoints
from ..auth import (
    ApiCredentialVerifier,
    CredentialResolver,
    CredentialStore,
    CredentialVerifier,
)
from ..auth.credentials import Credentials
from ..auth.provider_credentials import ProviderCredentials
from ..auth.provider_resolver import ProviderResolver
from ..auth.provider_store import ProviderCredentialStore
from ..auth.provider_verifier import ProviderVerifier, verifier_for_provider
from ..config import ConfigResolver, ConfigStore, ResolvedConfig, VidbytePaths
from ..config.migration import StateMigration
from ..config.models import DEFAULT_API_URL, DEFAULT_PROFILE
from ..errors.failures import AuthenticationRequired, ProviderAuthenticationRequired
from ..errors.handler import ErrorHandler
from ..io import IOStreams
from ..io.terminal import TerminalCapabilities, TerminalPolicy
from ..output.formats import ColorMode, OutputFormat
from ..output.manager import OutputManager, OutputPolicy
from ..runtime_primitives import RuntimeExecutor, RuntimeHostRegistry, RuntimeLaunchPlanner


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
        self._verifier_factory = verifier_factory or ApiCredentialVerifier
        self._verifier: CredentialVerifier | None = None
        self._output = self._build_output()
        self._errors = ErrorHandler(self._output)
        self._api_client: ApiClient | None = None
        self._research_endpoints: ResearchEndpoints | None = None
        self._runtime_endpoints: RuntimeEndpoints | None = None
        self._runtime_hosts: RuntimeHostRegistry | None = None
        self._runtime_launch_planner: RuntimeLaunchPlanner | None = None
        self._runtime_executor: RuntimeExecutor | None = None
        self._provider_store: ProviderCredentialStore | None = None
        self._provider_resolver: ProviderResolver | None = None

    def configure(self, options: InvocationOptions, config: ResolvedConfig) -> None:
        # Root options are read twice — once by the pre-scan, once by Click — so an unchanged
        # policy must not rebuild the OutputManager and leave two disagreeing about a stream.
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

    def require_credentials(self) -> Credentials:
        # The API key for this invocation's profile and host, or a clean failure if none.
        config = self.resolved_config()
        resolved = self.credential_resolver().resolve(config.profile, config.api_url)
        if resolved is None:
            raise AuthenticationRequired()
        return resolved.credentials

    def api_client(self) -> ApiClient:
        # One client per invocation, so a polling command reuses a single connection pool.
        if self._api_client is None:
            self._api_client = ApiClient(self.resolved_config(), self.require_credentials())
        return self._api_client

    def research_endpoints(self) -> ResearchEndpoints:
        # The authenticated research route group; requires a logged-in user.
        if self._research_endpoints is None:
            self._research_endpoints = ResearchEndpoints(self.api_client())
        return self._research_endpoints

    def runtime_endpoints(self) -> RuntimeEndpoints:
        # Lazily binds runtime HTTP operations to this invocation's authenticated client.
        if self._runtime_endpoints is None:
            self._runtime_endpoints = RuntimeEndpoints(self.api_client())
        return self._runtime_endpoints

    def runtime_hosts(self) -> RuntimeHostRegistry:
        # Shares one PATH discovery policy between doctor and launch planning.
        if self._runtime_hosts is None:
            self._runtime_hosts = RuntimeHostRegistry()
        return self._runtime_hosts

    def runtime_launch_planner(self) -> RuntimeLaunchPlanner:
        # Builds local launch plans without credentials, network calls, or subprocesses.
        if self._runtime_launch_planner is None:
            self._runtime_launch_planner = RuntimeLaunchPlanner(self.runtime_hosts())
        return self._runtime_launch_planner

    def runtime_executor(self) -> RuntimeExecutor:
        # Returns the inert boundary a later runtime implementation will replace.
        if self._runtime_executor is None:
            self._runtime_executor = RuntimeExecutor()
        return self._runtime_executor

    def close(self) -> None:
        # Releases network resources this invocation opened; a help path opened none.
        if self._api_client is not None:
            self._api_client.close()

    def output(self) -> OutputManager:
        # Callers share one policy object so stdout cardinality stays enforceable.
        return self._output

    def provider_store(self) -> ProviderCredentialStore:
        # Lazily created so --help never opens the keyring.
        if self._provider_store is None:
            self._provider_store = ProviderCredentialStore(paths=self.paths())
        return self._provider_store

    def provider_resolver(self) -> ProviderResolver:
        # Env > keyring > file, scoped by profile+provider.
        if self._provider_resolver is None:
            self._provider_resolver = ProviderResolver(self.provider_store(), self.environment)
        return self._provider_resolver

    def provider_verifier(self, provider: Provider) -> ProviderVerifier:
        # Factory keeps command from branching on provider.
        return verifier_for_provider(provider)

    def require_provider_credentials(self, provider: Provider) -> ProviderCredentials:
        # Provider key for this profile, or a typed failure before any network call.
        config = self.resolved_config()
        resolved = self.provider_resolver().resolve(config.profile, provider)
        if resolved is None:
            raise ProviderAuthenticationRequired(provider.value)
        return resolved.credentials

    def error_handler(self) -> ErrorHandler:
        return self._errors

    def _build_output(self) -> OutputManager:
        # Terminal detection reruns whenever color or no-input preferences change.
        terminal_policy = TerminalPolicy(
            self.options.color,
            self.options.no_input,
            self.environment,
        )
        terminal = TerminalCapabilities.detect(self.streams, terminal_policy)
        return OutputManager(self.streams, OutputPolicy(self.options.output_format, terminal))
