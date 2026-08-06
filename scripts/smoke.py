"""FILE: scripts/smoke.py

PURPOSE: Verifies that the public CLI module boots and representative static plus harness
help screens render without credentials or network access. This script is a fast startup
gate, not a substitute for feature tests or live API validation.

ROLE IN CODEBASE: scripts/run_ci.py invokes SmokeRunner after lint, typing, and compilation.
Each case launches `python -m vidbyte_cli`, exercising __main__.py, cli.py, runtime
composition, command registration, and the static software-engineering harness.

ARCHITECTURE NOTE: The approved no-tests workflow retains and strengthens deterministic
smoke verification. The rationale is in docs/design/python-cli-research-harness-program.md.

FUNCTION INVENTORY (reviewed 2026-07-26):
- SmokeRunner.run() -> int: launches every declared invocation and reports the first failure.
- SmokeRunner._invoke_python(arguments) -> completed command: runs from this worktree source.
- SmokeRunner._validate(case, result) -> str | None: checks status and stream contracts.
- SmokeRunner._validate_machine_error(code, serialized) -> str | None: validates envelopes.
- main() -> int: constructs and runs the smoke verifier.

COMMON MODIFICATION PATTERNS: Add a case when the public tree, exit vocabulary, or global
output contract changes. Keep cases credential-free and avoid live API operations.

WHAT NOT TO DO IN THIS FILE:
1. Do not call real Vidbyte routes or require API keys.
2. Do not mutate user config, credentials, repositories, or backend state.
3. Do not treat startup smoke coverage as feature correctness.
4. Do not bypass the public `python -m vidbyte_cli` entry point.

KNOWN EDGE CASES: Subprocess output is captured so a failed case can print both channels.
The script prepends this checkout's src directory so stacked worktrees cannot use a stale
editable install.

RELATED DOCS:
https://github.com/cerredz/Vidbyte-cli/blob/main/docs/design/python-cli-research-harness-program.md
defines verification scope after this stack merges.

TESTS: This file is itself the approved offline smoke verification and is executed by
scripts/run_ci.py on every supported CI platform.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from json import JSONDecodeError, loads
from os import environ, pathsep
from pathlib import Path

_CompletedCommand = subprocess.CompletedProcess[str]
_IMPORT_CODE = (
    "import sys; import vidbyte_cli; "
    "assert 'click' not in sys.modules; assert 'httpx' not in sys.modules; "
    "import vidbyte_cli.features.research.application; "
    "assert 'click' not in sys.modules; assert 'httpx' not in sys.modules; "
    "import vidbyte_cli.lib.output; import vidbyte_cli.lib.io; import vidbyte_cli.lib.errors"
)


@dataclass(frozen=True)
class SmokeCase:
    """One public invocation and its stable process/error expectations."""

    arguments: tuple[str, ...]
    expected_exit: int = 0
    error_code: str | None = None
    machine_error: bool = False


_CASES: tuple[SmokeCase, ...] = (
    SmokeCase(("--help",)),
    SmokeCase(("--version",)),
    SmokeCase(("harness", "--help")),
    SmokeCase(("harness", "run", "--help")),
    SmokeCase(
        ("harness", "--not-an-option", "namespace"), expected_exit=2, error_code="INVALID_ARGUMENT"
    ),
    SmokeCase(("harness", "software-engineering", "--help")),
    SmokeCase(("harness", "software-engineering", "fix", "--help")),
    SmokeCase(("connect", "--help")),
    SmokeCase(("config", "--help")),
    SmokeCase(("research", "--help")),
    SmokeCase(("research", "start", "--help")),
    SmokeCase(("research", "add", "--help")),
    SmokeCase(("research", "resume", "--help")),
    SmokeCase(("research", "status", "--help")),
    SmokeCase(("research", "watch", "--help")),
    SmokeCase(("research", "runs", "list", "--help")),
    SmokeCase(("research", "threads", "list", "--help")),
    SmokeCase(("research", "sources", "list", "--help")),
    SmokeCase(("research", "artifacts", "list", "--help")),
    SmokeCase(("research", "artifacts", "get", "--help")),
    SmokeCase(("research", "capabilities", "--help")),
    SmokeCase(("research", "export", "artifact", "--help")),
    SmokeCase(("research", "export", "thread", "--help")),
    SmokeCase(("research", "export", "portfolio", "--help")),
    SmokeCase(("research", "export", "status", "--help")),
    SmokeCase(
        ("research", "start", "offline smoke prompt", "--no-wait"),
        expected_exit=1,
        error_code="NOT_IMPLEMENTED",
    ),
    SmokeCase(("doctor",)),
    SmokeCase(("--json", "doctor")),
    SmokeCase(("--format", "jsonl", "doctor")),
    SmokeCase(
        ("--format", "json", "not-a-command"),
        expected_exit=2,
        error_code="INVALID_ARGUMENT",
        machine_error=True,
    ),
    SmokeCase(
        ("--format", "json", "--not-an-option"),
        expected_exit=2,
        error_code="INVALID_ARGUMENT",
        machine_error=True,
    ),
    SmokeCase(
        ("--json", "--format", "human", "doctor"),
        expected_exit=2,
        error_code="INVALID_ARGUMENT",
    ),
)


class SmokeRunner:
    """Launch representative commands through the public module entry point."""

    def run(self) -> int:
        # Stop at the first broken public invocation and preserve its diagnostic output.
        import_result = self._invoke_python(("-c", _IMPORT_CODE))
        if import_result.returncode != 0:
            self._report_import_failure(import_result)
            return 1
        sys.stdout.write("ok: package import boundaries\n")
        for case in _CASES:
            result = self._invoke(case.arguments)
            validation_error = self._validate(case, result)
            if validation_error is not None:
                self._report_failure(case, result, validation_error)
                return 1
            self._report_success(case)
        sys.stdout.write("smoke passed\n")
        return 0

    def _invoke(self, arguments: Sequence[str]) -> _CompletedCommand:
        # Launch a fresh process so import and executable-boundary failures remain visible.
        return self._invoke_python(("-m", "vidbyte_cli", *arguments))

    def _invoke_python(self, arguments: Sequence[str]) -> _CompletedCommand:
        # Prepend this worktree's source so stacked branches cannot use a stale editable install.
        process_environment = dict(environ)
        source_root = str(Path(__file__).resolve().parents[1] / "src")
        existing_python_path = process_environment.get("PYTHONPATH")
        process_environment["PYTHONPATH"] = (
            f"{source_root}{pathsep}{existing_python_path}" if existing_python_path else source_root
        )
        # Keep smoke read-only and isolated from a developer's actual profile/keyring.
        smoke_root = Path(__file__).resolve().parents[1] / ".smoke-state"
        process_environment["XDG_CONFIG_HOME"] = str(smoke_root / "config")
        process_environment["XDG_CACHE_HOME"] = str(smoke_root / "cache")
        process_environment["XDG_DATA_HOME"] = str(smoke_root / "data")
        process_environment["XDG_STATE_HOME"] = str(smoke_root / "state")
        process_environment["LOCALAPPDATA"] = str(smoke_root / "local")
        process_environment["PYTHON_KEYRING_BACKEND"] = "keyring.backends.null.Keyring"
        process_environment["VIDBYTE_EXPERIMENTAL_RESEARCH"] = "1"
        return subprocess.run(
            [sys.executable, *arguments],
            capture_output=True,
            text=True,
            check=False,
            env=process_environment,
        )

    def _report_import_failure(self, result: _CompletedCommand) -> None:
        # Import-order regressions need both channels because Python may use either.
        sys.stderr.write("FAIL: package import boundaries\n")
        sys.stderr.write(result.stdout)
        sys.stderr.write(result.stderr)

    def _validate(self, case: SmokeCase, result: _CompletedCommand) -> str | None:
        # Stable exit and error shape checks make this useful without becoming a feature suite.
        if result.returncode != case.expected_exit:
            return f"expected exit {case.expected_exit}, got {result.returncode}"
        if case.error_code is None:
            return None
        if result.stdout:
            return "error invocation wrote to stdout"
        if case.machine_error:
            return self._validate_machine_error(case.error_code, case.expected_exit, result.stderr)
        expected_label = f"Error [{case.error_code}]"
        return None if expected_label in result.stderr else f"missing '{expected_label}'"

    def _validate_machine_error(
        self, error_code: str, expected_exit: int, serialized: str
    ) -> str | None:
        # Machine failures must remain one valid versioned document on stderr.
        try:
            document = loads(serialized)
        except JSONDecodeError:
            return "machine error was not valid JSON"
        if not isinstance(document, dict):
            return "machine error was not a JSON object"
        if document.get("schema_version") != 1 or document.get("kind") != "error":
            return "machine error envelope was not schema_version=1 kind=error"
        data = document.get("data", {})
        if not isinstance(data, dict):
            return "machine error data was not a JSON object"
        if data.get("code") != error_code:
            return f"missing error code {error_code}"
        if data.get("exit_code") != expected_exit:
            return f"missing exit code {expected_exit}"
        return None

    def _report_failure(
        self,
        case: SmokeCase,
        result: _CompletedCommand,
        validation_error: str,
    ) -> None:
        # CI needs the exact invocation and stderr to route a startup failure quickly.
        arguments = " ".join(case.arguments)
        sys.stderr.write(f"FAIL: {arguments}: {validation_error}\n")
        sys.stderr.write(result.stdout)
        sys.stderr.write(result.stderr)

    def _report_success(self, case: SmokeCase) -> None:
        # One compact line per case makes cross-platform CI progress easy to scan.
        sys.stdout.write(f"ok: vidbyte-cli {' '.join(case.arguments)}\n")


def main() -> int:
    # Keep the executable wrapper small so SmokeRunner is reusable from the CI orchestrator.
    return SmokeRunner().run()


if __name__ == "__main__":
    raise SystemExit(main())
