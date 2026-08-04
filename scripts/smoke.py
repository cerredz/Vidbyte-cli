"""Smoke test: the CLI boots, its command tree renders, and failures keep their contracts.

Run with `python scripts/smoke.py`, or via `scripts/run_ci.py`. Every case goes through the
public `python -m vidbyte_cli` entry point in a fresh process, so import and executable
boundary failures stay visible. This proves startup and the published output/exit contracts,
not feature correctness, and must stay credential-free and offline.

The source directory is prepended to PYTHONPATH because a stale editable install of another
worktree would otherwise silently supply the package under test.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# Importing the package alone must not drag in Click or httpx, or `--version` gets slow and
# help paths start depending on the network stack.
IMPORT_BOUNDARY_CODE = (
    "import sys; import vidbyte_cli; "
    "assert 'click' not in sys.modules; assert 'httpx' not in sys.modules"
)


@dataclass(frozen=True)
class Case:
    """One public invocation and the process contract it must honour."""

    args: list[str]
    exit_code: int = 0
    error_code: str | None = None
    machine_error: bool = False


CASES = [
    Case(["--help"]),
    Case(["--version"]),
    Case(["harness", "--help"]),
    Case(["harness", "software-engineering", "--help"]),
    Case(["harness", "software-engineering", "fix", "--help"]),
    Case(["connect", "--help"]),
    Case(["config", "--help"]),
    # An option value must never be read as a dynamic harness namespace.
    Case(["harness", "--not-an-option", "namespace"], exit_code=2, error_code="INVALID_ARGUMENT"),
    Case(["doctor"], exit_code=1, error_code="NOT_IMPLEMENTED"),
    Case(["--json", "doctor"], exit_code=1, error_code="NOT_IMPLEMENTED", machine_error=True),
    Case(
        ["--format", "jsonl", "doctor"],
        exit_code=1,
        error_code="NOT_IMPLEMENTED",
        machine_error=True,
    ),
    Case(
        ["--format", "json", "not-a-command"],
        exit_code=2,
        error_code="INVALID_ARGUMENT",
        machine_error=True,
    ),
    Case(
        ["--format", "json", "--not-an-option"],
        exit_code=2,
        error_code="INVALID_ARGUMENT",
        machine_error=True,
    ),
    Case(["--json", "--format", "human", "doctor"], exit_code=2, error_code="INVALID_ARGUMENT"),
]


def run_python(args: list[str]) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    source = str(Path(__file__).resolve().parents[1] / "src")
    existing = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = f"{source}{os.pathsep}{existing}" if existing else source
    return subprocess.run(
        [sys.executable, *args], capture_output=True, text=True, check=False, env=environment
    )


def check(case: Case, result: subprocess.CompletedProcess[str]) -> str | None:
    # Returns the first contract violation, or None when the case holds.
    if result.returncode != case.exit_code:
        return f"expected exit {case.exit_code}, got {result.returncode}"
    if case.error_code is None:
        return None
    if result.stdout:
        return "a failing invocation wrote to stdout"
    if not case.machine_error:
        label = f"Error [{case.error_code}]"
        return None if label in result.stderr else f"missing '{label}'"
    return check_machine_error(case, result.stderr)


def check_machine_error(case: Case, serialized: str) -> str | None:
    # A machine failure must be exactly one versioned document, on stderr.
    try:
        document = json.loads(serialized)
    except json.JSONDecodeError:
        return "machine error was not valid JSON"
    if document.get("schema_version") != 1 or document.get("kind") != "error":
        return "machine error was not schema_version=1 kind=error"
    data = document.get("data", {})
    if data.get("code") != case.error_code:
        return f"expected error code {case.error_code}, got {data.get('code')}"
    if data.get("exit_code") != case.exit_code:
        return f"expected exit_code {case.exit_code} in the document"
    # The agent-native fields are part of the contract: an agent branches on them.
    missing = [field for field in ("description", "trace", "file_path") if not data.get(field)]
    return f"machine error omitted {', '.join(missing)}" if missing else None


def main() -> int:
    boundary = run_python(["-c", IMPORT_BOUNDARY_CODE])
    if boundary.returncode != 0:
        print("FAIL: package import boundaries", file=sys.stderr)
        print(boundary.stderr, file=sys.stderr)
        return 1
    print("ok: package import boundaries")
    for case in CASES:
        result = run_python(["-m", "vidbyte_cli", *case.args])
        if failure := check(case, result):
            # Diagnostics go to stderr so CI log scrapers see the failing invocation.
            print(f"FAIL: {' '.join(case.args)}: {failure}", file=sys.stderr)
            print(result.stdout, file=sys.stderr)
            print(result.stderr, file=sys.stderr)
            return 1
        print(f"ok: vidbyte-cli {' '.join(case.args)}")
    print("smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
