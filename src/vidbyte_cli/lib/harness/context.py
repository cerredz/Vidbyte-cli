"""FILE: src/vidbyte_cli/lib/harness/context.py

PURPOSE: Defines the services used by the generic harness command lifecycle and wires its
default collaborators on demand. Command-tree construction receives this object but must
not touch stateful services until dispatch.

ROLE IN CODEBASE: BaseHarness uses credentials, repository inspection, endpoints, rendering,
and logging through this context. ApplicationContext creates the default graph lazily and
shares its OutputManager through Logger.

ARCHITECTURE NOTE: This is the extensibility seam for legacy and manifest-backed harnesses.
It remains separate from ApplicationContext because harness dependencies are optional.

FUNCTION INVENTORY (reviewed 2026-07-26):
- HarnessContext.require_api_key() -> str: returns a stored key or raises a safe auth error.
- HarnessContext.harness_endpoints() -> HarnessEndpoints: builds authenticated endpoints.
- HarnessContext.manifest_cache_dir() -> str: returns the catalog cache location.
- HarnessContext.default(output) -> HarnessContext: wires default lazy harness services.

COMMON MODIFICATION PATTERNS: Add only capabilities shared by all harnesses, preserve lazy
construction, and update lib/harness/README.md plus BaseHarness integration.

WHAT NOT TO DO IN THIS FILE:
1. Do not perform API calls while constructing the context.
2. Do not print, call sys.exit, or create a process-global logger.
3. Do not expose API keys through errors, output, or repr customization.
4. Do not add research-specific services; the research feature owns those.
5. Do not read root CLI flags directly; ApplicationContext owns resolved policy.

KNOWN EDGE CASES: Help and version paths never request this context. Missing credentials
must fail before repository inspection or network work.

RELATED DOCS:
https://github.com/cerredz/Vidbyte-cli/blob/main/docs/architecture.md
explains the generic harness dependency boundary.

TESTS: No dedicated feature tests are added under the approved no-tests workflow.
scripts/smoke.py exercises static harness registration without service calls.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..api.client import ApiClient
from ..api.endpoints.harness import HarnessEndpoints
from ..auth.credentials import CredentialStore
from ..config.paths import VidbytePaths
from ..errors.cli_error import CliError
from ..errors.codes import CliErrorCode, ExitCode
from ..git.repo_info import RepoInspector
from ..output.logger import Logger
from ..output.manager import OutputManager
from ..output.render import RunRenderer


@dataclass
class HarnessContext:
    """Lazy-service graph shared by generic harness commands."""

    credentials: CredentialStore
    repo: RepoInspector
    logger: Logger
    render: RunRenderer
    base_url: str | None = None
    profile: str = "default"
    paths: VidbytePaths | None = None

    def require_api_key(self) -> str:
        # Authentication fails before any repository or backend work.
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
        # The current scaffold creates endpoints on dispatch, never command-tree construction.
        client = ApiClient(base_url=self.base_url, api_key=self.require_api_key())
        return HarnessEndpoints(client)

    def manifest_cache_dir(self) -> str:
        # VidbytePaths remains the single owner of legacy catalog locations.
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
    ) -> HarnessContext:
        # Wire the generic runtime around the invocation-owned output policy.
        return HarnessContext(
            credentials=credentials or CredentialStore(paths=paths),
            repo=RepoInspector(),
            logger=Logger(output),
            render=RunRenderer(),
            base_url=base_url,
            profile=profile,
            paths=paths,
        )
