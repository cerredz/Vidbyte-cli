"""The canonical repository gate: one script run identically by developers and CI.

`.github/workflows/ci.yml` supplies only the OS/Python matrix and calls this — the step list
is never duplicated in YAML. Source gates run first (fast, fail-fast), then the distribution
is built in a temporary clean copy and smoke-tested from a fresh virtualenv, which is the
only way to prove imports come from the wheel and not the checkout.

Never publishes, never needs credentials, never calls a live Vidbyte endpoint.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import venv
from pathlib import Path

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

# Copied source excludes VCS metadata, environments, caches, and prior build output so local
# state can never leak into the wheel under test.
_BUILD_COPY_EXCLUDES = (
    ".git", ".env", ".venv", "venv", "build", "dist", "*.egg-info", "__pycache__",
    ".coverage*", ".mypy_cache", ".nox", ".pytest_cache", ".ruff_cache", ".tox",
)  # fmt: skip


class CiRunner:
    """Runs every verification gate in order, stopping at the first failure."""

    def __init__(self, repository_root: Path) -> None:
        # Anchor every subprocess to one explicit checkout, whatever the caller's cwd.
        self._root = repository_root

    def run(self) -> int:
        # Quality and source smoke are cheap, so they precede distribution verification.
        python = sys.executable
        source_gates = (
            ("ruff lint", (python, "-m", "ruff", "check", ".")),
            ("ruff format", (python, "-m", "ruff", "format", "--check", ".")),
            ("mypy strict", (python, "-m", "mypy", "src")),
            ("byte compilation", (python, "-m", "compileall", "-q", "src")),
            ("offline smoke", (python, "scripts/smoke.py")),
            # Loopback-only, so it stays as offline as the smoke gate above it.
            ("login key verification", (python, "scripts/test_login_key_verification.py")),
            # Offline: inspects the command tree and runs help/usage paths only.
            ("research-only surface", (python, "scripts/test_research_only_surface.py")),
        )
        for label, arguments in source_gates:
            if status := self._run(label, arguments):
                return status
        return self._verify_distribution()

    def _run(self, label: str, arguments: tuple[str, ...], cwd: Path | None = None) -> int:
        # Stream native tool output so a failure keeps its most useful diagnostics.
        sys.stdout.write(f"==> {label}\n")
        sys.stdout.flush()
        return subprocess.run(arguments, cwd=cwd or self._root, check=False).returncode

    def _verify_distribution(self) -> int:
        # Build from a clean copy, validate the metadata, then install and run that wheel.
        with tempfile.TemporaryDirectory(prefix="vidbyte-cli-ci-") as temporary:
            workspace = Path(temporary)
            source, dist = workspace / "source", workspace / "dist"
            excluded = shutil.ignore_patterns(*_BUILD_COPY_EXCLUDES)
            shutil.copytree(self._root, source, ignore=excluded)
            build = (sys.executable, "-m", "build", "--sdist", "--wheel", "--outdir", str(dist))
            # Build isolation also proves the declared build-system requirements suffice.
            if status := self._run("build sdist and wheel", build, cwd=source):
                return status

            artifacts = sorted(dist.iterdir())
            if not artifacts:
                sys.stderr.write("Distribution build produced no artifacts.\n")
                return 1
            check = (sys.executable, "-m", "twine", "check", *(str(path) for path in artifacts))
            if status := self._run("distribution metadata", check):
                return status
            return self._verify_installed_wheel(workspace, artifacts)

    def _verify_installed_wheel(self, workspace: Path, artifacts: list[Path]) -> int:
        # Running from `workspace` (outside the checkout) is what proves the wheel is used.
        wheels = [path for path in artifacts if path.suffix == ".whl"]
        if len(wheels) != 1:
            sys.stderr.write(f"Expected one wheel, found {len(wheels)}.\n")
            return 1
        environment = workspace / "installed"
        venv.EnvBuilder(with_pip=True).create(environment)
        python, console = self._environment_executables(environment)
        gates = (
            ("clean wheel install", (str(python), "-m", "pip", "install", str(wheels[0]))),
            ("installed module smoke", (str(python), "-m", "vidbyte_cli", "--version")),
            ("installed console smoke", (str(console), "--help")),
        )
        for label, arguments in gates:
            if status := self._run(label, arguments, cwd=workspace):
                return status
        return 0

    def _environment_executables(self, environment: Path) -> tuple[Path, Path]:
        # Windows and POSIX virtualenvs differ in both script directory and file extension.
        scripts = environment / ("Scripts" if os.name == "nt" else "bin")
        suffix = ".exe" if os.name == "nt" else ""
        return scripts / f"python{suffix}", scripts / f"vidbyte-cli{suffix}"


def main() -> int:
    return CiRunner(_REPOSITORY_ROOT).run()


if __name__ == "__main__":
    raise SystemExit(main())
