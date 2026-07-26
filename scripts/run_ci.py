"""FILE: scripts/run_ci.py

PURPOSE: Runs the canonical repository verification sequence used both locally and in
GitHub Actions. It owns lint, formatting, strict typing, compilation, offline smoke,
distribution build, metadata validation, and clean-wheel installation checks. It never
publishes artifacts or exercises live Vidbyte APIs.

ROLE IN CODEBASE: .github/workflows/ci.yml installs development dependencies and invokes
main(). The runner calls Ruff, mypy, compileall, scripts/smoke.py, build, Twine, pip, an
installed module process, and the generated console script. pyproject.toml owns tool policy.

ARCHITECTURE NOTE: One executable sequence prevents local and remote gates from drifting.
The no-feature-test constraint and package-clean requirement are approved in
docs/design/python-cli-research-harness-program.md.

FUNCTION INVENTORY (reviewed 2026-07-26):
- CommandSpec: immutable label and argv for one subprocess.
- CiRunner.run() -> int: executes quality, smoke, and package checks in fail-fast order.
- main() -> int: runs the canonical verifier from the repository root.

COMMON MODIFICATION PATTERNS: Add a platform-independent CommandSpec for a new quality gate,
or add a small private method when a gate requires temporary resources. Update
scripts/README.md and GitHub cache inputs if dependencies change.

WHAT NOT TO DO IN THIS FILE:
1. Do not publish packages, create releases, or push repository changes.
2. Do not call live Vidbyte endpoints or require credentials.
3. Do not duplicate the command list in workflow YAML.
4. Do not swallow subprocess output or continue after a failed gate.
5. Do not add feature test packs under the approved no-tests workflow.

KNOWN EDGE CASES: Virtual-environment Python paths differ on Windows and POSIX. Clean-wheel
verification runs outside the repository so the source tree cannot shadow the installed
artifact. Builds use a temporary clean source copy so ignored local state cannot leak into
the wheel. Package dependency installation may use the configured pip index.

COMMON ERRORS RAISED BY THIS FILE: A failing subprocess returns its original non-zero status
through the runner. Missing build artifacts produce a concise repository-verification error.

RELATED DOCS:
https://github.com/cerredz/Vidbyte-cli/blob/main/docs/design/python-cli-research-harness-program.md
defines the PR gate and supported platforms after this stack merges.

TESTS: This file is the canonical verifier. It invokes scripts/smoke.py and validates both
module and generated-console entry points from a wheel installed in a fresh environment.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import venv
from dataclasses import dataclass
from pathlib import Path

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class CommandSpec:
    """One named verification subprocess."""

    label: str
    arguments: tuple[str, ...]


class CiRunner:
    """Fail-fast orchestrator for repository and distribution verification."""

    def __init__(self, repository_root: Path) -> None:
        # Keep every subprocess anchored to the same explicit checkout.
        self._repository_root = repository_root

    def run(self) -> int:
        # Quality and source smoke checks precede the slower distribution verification.
        for command in self._source_commands():
            status = self._run_command(command)
            if status != 0:
                return status
        return self._verify_distribution()

    def _source_commands(self) -> tuple[CommandSpec, ...]:
        # Keep this ordered tuple as the single source for local and remote source gates.
        python = sys.executable
        return (
            CommandSpec("ruff lint", (python, "-m", "ruff", "check", ".")),
            CommandSpec("ruff format", (python, "-m", "ruff", "format", "--check", ".")),
            CommandSpec("mypy strict", (python, "-m", "mypy", "src")),
            CommandSpec("byte compilation", (python, "-m", "compileall", "-q", "src")),
            CommandSpec("offline smoke", (python, "scripts/smoke.py")),
        )

    def _run_command(self, command: CommandSpec, cwd: Path | None = None) -> int:
        # Stream native tool output so a failure preserves its most useful diagnostics.
        sys.stdout.write(f"==> {command.label}\n")
        sys.stdout.flush()
        result = subprocess.run(
            command.arguments,
            cwd=cwd or self._repository_root,
            check=False,
        )
        return result.returncode

    def _verify_distribution(self) -> int:
        # Build into an isolated temporary tree, then inspect and install that exact wheel.
        with tempfile.TemporaryDirectory(prefix="vidbyte-cli-ci-") as temporary:
            workspace = Path(temporary)
            source = workspace / "source"
            self._copy_source_tree(source)
            distribution_dir = workspace / "dist"
            build_status = self._build_distribution(source, distribution_dir)
            if build_status != 0:
                return build_status
            artifacts = tuple(sorted(distribution_dir.iterdir()))
            metadata_status = self._check_metadata(artifacts)
            if metadata_status != 0:
                return metadata_status
            return self._verify_installed_wheel(workspace, artifacts)

    def _copy_source_tree(self, destination: Path) -> None:
        # Exclude repository metadata, environments, caches, and prior package outputs.
        ignored = shutil.ignore_patterns(
            ".git",
            ".env",
            ".venv",
            "venv",
            "build",
            "dist",
            "*.egg-info",
            "__pycache__",
            ".coverage*",
            ".mypy_cache",
            ".nox",
            ".pytest_cache",
            ".ruff_cache",
            ".tox",
        )
        shutil.copytree(self._repository_root, destination, ignore=ignored)

    def _build_distribution(self, source: Path, distribution_dir: Path) -> int:
        # Build isolation verifies the declared build-system requirements are sufficient.
        command = CommandSpec(
            "build sdist and wheel",
            (
                sys.executable,
                "-m",
                "build",
                "--sdist",
                "--wheel",
                "--outdir",
                str(distribution_dir),
            ),
        )
        return self._run_command(command, cwd=source)

    def _check_metadata(self, artifacts: tuple[Path, ...]) -> int:
        # Twine validates every produced distribution without publishing any artifact.
        if not artifacts:
            sys.stderr.write("Distribution build produced no artifacts.\n")
            return 1
        arguments = (sys.executable, "-m", "twine", "check", *(str(path) for path in artifacts))
        return self._run_command(CommandSpec("distribution metadata", arguments))

    def _verify_installed_wheel(self, workspace: Path, artifacts: tuple[Path, ...]) -> int:
        # Running outside the checkout proves imports and entry behavior come from the wheel.
        wheels = tuple(path for path in artifacts if path.suffix == ".whl")
        if len(wheels) != 1:
            sys.stderr.write(f"Expected one wheel, found {len(wheels)}.\n")
            return 1
        environment = workspace / "installed"
        venv.EnvBuilder(with_pip=True).create(environment)
        python = self._environment_python(environment)
        install = CommandSpec(
            "clean wheel install", (str(python), "-m", "pip", "install", str(wheels[0]))
        )
        install_status = self._run_command(install, cwd=workspace)
        if install_status != 0:
            return install_status
        module_command = CommandSpec(
            "installed module smoke", (str(python), "-m", "vidbyte_cli", "--version")
        )
        module_status = self._run_command(module_command, cwd=workspace)
        if module_status != 0:
            return module_status
        console = self._environment_console(environment)
        console_command = CommandSpec("installed console smoke", (str(console), "--help"))
        return self._run_command(console_command, cwd=workspace)

    def _environment_python(self, environment: Path) -> Path:
        # Virtual environments use a platform-specific executable directory.
        scripts_directory = self._environment_scripts_directory(environment)
        executable = "python.exe" if os.name == "nt" else "python"
        return scripts_directory / executable

    def _environment_console(self, environment: Path) -> Path:
        # Pip creates the public console entry point beside the environment's interpreter.
        scripts_directory = self._environment_scripts_directory(environment)
        executable = "vidbyte-cli.exe" if os.name == "nt" else "vidbyte-cli"
        return scripts_directory / executable

    def _environment_scripts_directory(self, environment: Path) -> Path:
        # Windows and POSIX virtual environments use different script directory names.
        directory = "Scripts" if os.name == "nt" else "bin"
        return environment / directory


def main() -> int:
    # Anchor the gate to the checkout containing this script, regardless of caller cwd.
    return CiRunner(_REPOSITORY_ROOT).run()


if __name__ == "__main__":
    raise SystemExit(main())
