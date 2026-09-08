"""Reads every tracked Python source once, parsed, so no rule re-walks the tree itself.

`git ls-files` is the authority on what exists, which keeps sibling worktrees, build output,
and untracked scratch files out of scope. A file that does not parse is recorded as a parse
error rather than skipped, so a rule can never silently report zero findings for it.
"""

from __future__ import annotations

import ast
import subprocess
from dataclasses import dataclass
from pathlib import Path


class SourceDiscoveryError(RuntimeError):
    """Locating or reading tracked source failed, with the repository context to fix it."""


@dataclass(frozen=True, slots=True)
class SourceFile:
    """One tracked file with its text and, for Python, its parsed module."""

    path: Path
    rel: str
    text: str
    tree: ast.Module | None = None
    parse_error: str | None = None

    def line_at(self, line: int) -> str:
        # Returns one 1-indexed line, tolerating an analyzer that reports past the end.
        lines = self.text.splitlines()
        return lines[line - 1] if 0 < line <= len(lines) else ""


class SourceCatalog:
    """Caches the tracked source records that rules select from."""

    def __init__(self, root: Path | None = None) -> None:
        # Anchors discovery to the repository, never to the caller's working directory.
        self.root = (root or self.repository_root()).resolve()
        self._tracked: tuple[str, ...] | None = None
        self._command_files: tuple[SourceFile, ...] | None = None

    @classmethod
    def repository_root(cls) -> Path:
        # `lint/core/discovery.py` is always two directories below the repository root.
        return Path(__file__).resolve().parents[2]

    def command_files(self) -> tuple[SourceFile, ...]:
        # Returns the command surface: every module that can register a click command.
        if self._command_files is None:
            prefix = "src/vidbyte_cli/commands/"
            paths = (
                rel
                for rel in self.tracked_paths()
                if rel.startswith(prefix) and rel.endswith(".py")
            )
            self._command_files = tuple(self._build(rel) for rel in paths)
        return self._command_files

    def tracked_paths(self) -> tuple[str, ...]:
        # Runs git without a shell and reports the exact repository on failure.
        if self._tracked is not None:
            return self._tracked
        try:
            result = subprocess.run(
                ["git", "ls-files", "-z"],
                cwd=self.root,
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except (OSError, subprocess.CalledProcessError) as error:
            raise SourceDiscoveryError(
                f"Could not enumerate tracked files with git ls-files from {self.root}: "
                f"{error}. Run the lint suite from inside a Git worktree."
            ) from error
        self._tracked = tuple(
            sorted(path.replace("\\", "/") for path in result.stdout.split("\0") if path)
        )
        return self._tracked

    def _build(self, rel: str) -> SourceFile:
        # Reads and parses one tracked path, recording a syntax error instead of raising.
        path = self.root / Path(rel)
        try:
            # utf-8-sig so a Windows checkout with a BOM matches what compileall accepts.
            text = path.read_text(encoding="utf-8-sig")
        except OSError as error:
            raise SourceDiscoveryError(
                f"Could not read tracked source {path} as UTF-8 while building the lint "
                f"catalogue: {error}. Restore or re-encode the file."
            ) from error
        try:
            return SourceFile(path=path, rel=rel, text=text, tree=ast.parse(text, filename=rel))
        except SyntaxError as error:
            return SourceFile(
                path=path,
                rel=rel,
                text=text,
                parse_error=f"{error.msg} at {error.lineno}:{error.offset}",
            )
