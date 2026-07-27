"""Smoke test: the CLI boots and its command tree (static + a harness namespace) renders.

Run with `python scripts/smoke.py`, or via `scripts/run_ci.py`. Every case goes through the
public `python -m vidbyte_cli` entry point in a fresh process, so import and executable
boundary failures stay visible. This proves startup, not feature correctness, and must stay
credential-free and offline.
"""

from __future__ import annotations

import subprocess
import sys

INVOCATIONS = [
    ["--help"],
    ["--version"],
    ["harness", "--help"],
    ["harness", "software-engineering", "--help"],
    ["harness", "software-engineering", "fix", "--help"],
    ["connect", "--help"],
    ["config", "--help"],
]


def main() -> int:
    for args in INVOCATIONS:
        result = subprocess.run(
            [sys.executable, "-m", "vidbyte_cli", *args],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            # Diagnostics go to stderr so CI log scrapers see the failing invocation.
            print(f"FAIL: {' '.join(args)} (exit {result.returncode})", file=sys.stderr)
            print(result.stderr, file=sys.stderr)
            return 1
        print(f"ok: vidbyte-cli {' '.join(args)}")
    print("smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
