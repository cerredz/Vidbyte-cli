"""FILE: src/vidbyte_cli/lib/git/repo_info.py

PURPOSE: Reads stable repository identity and dirty state through bounded Git subprocesses.

ROLE IN CODEBASE: Generic harness commands choose whether a dirty checkout is acceptable,
then submit the exact origin URL, HEAD SHA, and optional branch.

ARCHITECTURE NOTE: Commands use Git plumbing/porcelain output, never localized human text.

TESTS: No feature tests are added under the approved no-tests workflow.
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from ...types.harness import HarnessRepoRef
from ..errors import CliError, CliErrorCode


class RepoInfo(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    origin_url: str
    head_sha: str
    branch: str | None
    is_dirty: bool

    def as_ref(self) -> HarnessRepoRef:
        return HarnessRepoRef(url=self.origin_url, sha=self.head_sha, branch=self.branch)


class RepoInspector:
    """Bounded read-only Git adapter for one working directory."""

    def __init__(self, cwd: Path | None = None) -> None:
        self._cwd = cwd or Path.cwd()

    def inspect(self) -> RepoInfo:
        self._run(("rev-parse", "--show-toplevel"))
        origin = self._run(("remote", "get-url", "origin"))
        sha = self._run(("rev-parse", "--verify", "HEAD"))
        branch_result = self._run_optional(("symbolic-ref", "--quiet", "--short", "HEAD"))
        status = self._run(("status", "--porcelain=v1", "-z"))
        return RepoInfo(
            origin_url=origin,
            head_sha=sha,
            branch=branch_result or None,
            is_dirty=bool(status),
        )

    def as_repo_ref(self) -> HarnessRepoRef:
        return self.inspect().as_ref()

    def _run(self, arguments: Sequence[str]) -> str:
        result = self._execute(arguments)
        if result.returncode != 0:
            raise self._failure()
        return result.stdout.strip()

    def _run_optional(self, arguments: Sequence[str]) -> str:
        result = self._execute(arguments)
        return result.stdout.strip() if result.returncode == 0 else ""

    def _execute(self, arguments: Sequence[str]) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                ["git", *arguments],
                cwd=self._cwd,
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise self._failure(error) from error

    def _failure(self, cause: Exception | None = None) -> CliError:
        return CliError(
            CliErrorCode.OPERATION_FAILED,
            "The current directory is not a usable Git repository.",
            hint="Run the command from a checkout with an origin remote and at least one commit.",
            cause=cause,
        )
