"""FILE: src/vidbyte_cli/lib/harness/context.py

PURPOSE: Defines lazy generic harness collaborators shared by static and manifest-backed
commands: endpoints, repository inspection, idempotency, recovery journal, polling, output.

ROLE IN CODEBASE: ApplicationContext creates this optional graph only for harness dispatch.
BaseHarness contains mechanism and receives every capability through this object.

ARCHITECTURE NOTE: Endpoint construction remains lazy so rendering a static command tree
does not read credentials or create a network client.

TESTS: No feature tests are added under the approved no-tests workflow.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ...types.harness import HarnessRun
from ..api.client import ApiClient
from ..api.endpoints.harness import HarnessEndpoints
from ..auth.credentials import CredentialStore
from ..config.paths import VidbytePaths
from ..errors import CliError, CliErrorCode, ExitCode
from ..git.repo_info import RepoInspector
from ..operations import IdempotencyKeyFactory, OperationJournal
from ..output.logger import Logger
from ..output.manager import OutputManager
from ..output.render import RunRenderer
from ..polling import Poller
from .watcher import HarnessRunWatcher

_EndpointFactory = Callable[[], HarnessEndpoints]


@dataclass
class HarnessContext:
    """Lazy-service graph shared by generic harness commands."""

    credentials: CredentialStore
    repo: RepoInspector
    logger: Logger
    render: RunRenderer
    output: OutputManager
    journal: OperationJournal
    idempotency: IdempotencyKeyFactory
    poller: Poller
    base_url: str | None = None
    profile: str = "default"
    paths: VidbytePaths | None = None
    endpoint_factory: _EndpointFactory | None = None

    def require_api_key(self) -> str:
        credentials = self.credentials.read(self.profile, self.base_url or "https://api.vidbyte.ai")
        if credentials is None:
            raise CliError(
                CliErrorCode.AUTH_REQUIRED,
                "Authentication is required.",
                ExitCode.AUTHENTICATION,
                hint="Run 'vidbyte-cli login' first.",
            )
        return credentials.secret_value()

    def harness_endpoints(self) -> HarnessEndpoints:
        if self.endpoint_factory is not None:
            return self.endpoint_factory()
        client = ApiClient(
            base_url=self.base_url or "https://api.vidbyte.ai", api_key=self.require_api_key()
        )
        return HarnessEndpoints(client)

    def watch_run(
        self,
        run_id: str,
        timeout_seconds: float | None = None,
    ) -> HarnessRun:
        return HarnessRunWatcher(
            self.harness_endpoints(),
            self.output,
            self.poller,
        ).watch(run_id, timeout_seconds)

    def manifest_cache_dir(self) -> str:
        paths = self.paths or VidbytePaths.default()
        return str(paths.manifests_dir())

    @staticmethod
    def default(
        output: OutputManager,
        *,
        credentials: CredentialStore | None = None,
        paths: VidbytePaths | None = None,
        base_url: str | None = None,
        profile: str = "default",
        endpoint_factory: _EndpointFactory | None = None,
    ) -> HarnessContext:
        resolved_paths = paths or VidbytePaths.default()
        return HarnessContext(
            credentials=credentials or CredentialStore(paths=resolved_paths),
            repo=RepoInspector(),
            logger=Logger(output),
            render=RunRenderer(),
            output=output,
            journal=OperationJournal(resolved_paths),
            idempotency=IdempotencyKeyFactory(),
            poller=Poller(),
            base_url=base_url,
            profile=profile,
            paths=resolved_paths,
            endpoint_factory=endpoint_factory,
        )
