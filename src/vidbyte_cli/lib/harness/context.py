"""The services a harness command needs, injected rather than reached for.

Dependency injection is the extensibility seam: when a harness needs a new capability, it
is added here once, not to every harness subclass. Building the command tree never touches
these services — only `dispatch` does — so `--help` stays free of credential or network I/O.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..api.client import ApiClient
from ..api.endpoints.harness import HarnessEndpoints
from ..auth.credentials import CredentialStore
from ..config.paths import VidbytePaths
from ..errors.failures import AuthenticationRequired
from ..git.repo_info import RepoInspector
from ..output.logger import Logger
from ..output.manager import OutputManager
from ..output.render import RunRenderer


@dataclass
class HarnessContext:
    credentials: CredentialStore
    repo: RepoInspector
    logger: Logger
    render: RunRenderer
    base_url: str | None = None

    def require_api_key(self) -> str:
        # Guard: the stored API key, or a clean CliError if the user is not logged in.
        creds = self.credentials.read()
        if creds is None:
            raise AuthenticationRequired()
        return creds.api_key

    def harness_endpoints(self) -> HarnessEndpoints:
        # An authenticated harness endpoint group; requires a logged-in user.
        client = ApiClient(base_url=self.base_url, api_key=self.require_api_key())
        return HarnessEndpoints(client)

    def manifest_cache_dir(self) -> str:
        # Where the catalog caches downloaded manifests.
        return str(VidbytePaths.manifests_dir())

    @staticmethod
    def default(output: OutputManager) -> HarnessContext:
        # Wires the real services around this invocation's output policy. The logger is no
        # longer a process global, so a harness cannot bypass the selected format.
        return HarnessContext(
            credentials=CredentialStore(),
            repo=RepoInspector(),
            logger=Logger(output),
            render=RunRenderer(),
        )
