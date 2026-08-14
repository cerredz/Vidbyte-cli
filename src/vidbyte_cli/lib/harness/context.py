"""The services a harness command needs, injected rather than reached for.

Dependency injection is the extensibility seam: when a harness needs a new capability, it
is added here once, not to every harness subclass. Building the command tree never touches
these services — only `dispatch` does — so `--help` stays free of credential or network I/O.

The whole `ResolvedConfig` travels rather than a loose host string, because a credential is
scoped to profile *and* host: a harness run against a staging host must not authenticate
with the production key. Credentials arrive through the resolver, never the raw store, so an
exported key outranks whatever a developer once saved on this machine.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..api.client import ApiClient
from ..api.endpoints.harness import HarnessEndpoints
from ..auth.credentials import Credentials
from ..auth.resolver import CredentialResolver
from ..config import ResolvedConfig
from ..config.paths import VidbytePaths
from ..errors.failures import AuthenticationRequired
from ..git.repo_info import RepoInspector
from ..output.logger import Logger
from ..output.manager import OutputManager
from ..output.render import RunRenderer


@dataclass
class HarnessContext:
    credentials: CredentialResolver
    repo: RepoInspector
    logger: Logger
    render: RunRenderer
    config: ResolvedConfig
    paths: VidbytePaths | None = None

    def require_credentials(self) -> Credentials:
        # Guard: the resolved API key for this scope, or a clean CliError if nobody is logged in.
        resolved = self.credentials.resolve(self.config.profile, self.config.api_url)
        if resolved is None:
            raise AuthenticationRequired()
        return resolved.credentials

    def harness_endpoints(self) -> HarnessEndpoints:
        # An authenticated harness endpoint group; requires a logged-in user.
        return HarnessEndpoints(ApiClient(self.config, self.require_credentials()))

    def manifest_cache_dir(self) -> str:
        # Where the catalog caches downloaded manifests.
        paths = self.paths or VidbytePaths.default()
        return str(paths.manifests_dir())

    @staticmethod
    def default(
        output: OutputManager,
        *,
        credentials: CredentialResolver,
        config: ResolvedConfig,
        paths: VidbytePaths | None = None,
    ) -> HarnessContext:
        # Wires the real services around this invocation's output policy. The logger is no
        # longer a process global, so a harness cannot bypass the selected format. The resolver
        # is required rather than defaulted: building one needs an injected environment, and
        # this module must not reach for `os.environ` to invent it.
        return HarnessContext(
            credentials=credentials,
            repo=RepoInspector(),
            logger=Logger(output),
            render=RunRenderer(),
            config=config,
            paths=paths,
        )
