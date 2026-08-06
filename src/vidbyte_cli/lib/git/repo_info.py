"""Reads identifying facts about the git repo in the current working directory, so
`harness run` can tell the backend exactly which code to execute against.
"""

from __future__ import annotations

from pydantic import BaseModel

from ...lib.errors.failures import NotImplementedFeature
from ...types.harness import HarnessRepoRef


class RepoInfo(BaseModel):
    origin_url: str
    head_sha: str
    branch: str
    is_dirty: bool


class RepoInspector:
    def inspect(self) -> RepoInfo:
        # Returns origin URL, HEAD sha, current branch, and dirty state for cwd's repo.
        raise NotImplementedFeature("repository inspection")

    def as_repo_ref(self) -> HarnessRepoRef:
        # Convenience: the subset of repo facts a run submission needs.
        info = self.inspect()
        return HarnessRepoRef(url=info.origin_url, sha=info.head_sha, branch=info.branch)
