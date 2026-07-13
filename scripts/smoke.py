"""Smoke test: the CLI boots and its command tree (static + a harness namespace) renders.

Run with `python scripts/smoke.py`. Exits non-zero if any help screen fails to build.
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
        )
        if result.returncode != 0:
            print(f"FAIL: {' '.join(args)} (exit {result.returncode})")
            print(result.stderr)
            return 1
        print(f"ok: vidbyte-cli {' '.join(args)}")
    print("smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
