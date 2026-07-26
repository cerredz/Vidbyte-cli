"""FILE: src/vidbyte_cli/lib/io/streams.py

PURPOSE: Defines the invocation-owned text streams used by the CLI. This module makes input
and output explicit dependencies so the runtime can be embedded or exercised without
replacing process globals. Formatting policy does not belong here; lib/output owns it.

ROLE IN CODEBASE: lib/runtime/application.py creates system streams for normal invocations,
and lib/runtime/context.py exposes them to command services. The class wraps Python TextIO
objects but never closes streams it did not create.

ARCHITECTURE NOTE: This is the process-I/O boundary described in
docs/design/python-cli-research-harness-program.md. It applies dependency inversion to
stdin, stdout, and stderr while preserving Click's synchronous execution model.

FUNCTION INVENTORY (reviewed 2026-07-26):
- IOStreams.system() -> IOStreams: binds the current process standard streams.
- IOStreams.write_output(message) -> None: writes and flushes ordinary output.
- IOStreams.write_error(message) -> None: writes and flushes diagnostic output.

COMMON MODIFICATION PATTERNS: Add a new process channel as a typed field, update system(),
then update lib/runtime/context.py and every output manager that consumes the stream set.

WHAT NOT TO DO IN THIS FILE:
1. Do not select JSON or human formatting; lib/output owns presentation policy.
2. Do not read credentials or configuration; lib/auth and lib/config own those boundaries.
3. Do not call sys.exit; lib/runtime/application.py owns return-code mapping.
4. Do not close caller-provided streams; their lifecycle belongs to the caller.

KNOWN EDGE CASES: StringIO and redirected streams may not expose terminal capabilities.
This class deliberately depends only on write() and flush(), leaving TTY detection to
lib/io/terminal.py when that adapter is introduced.

RELATED DOCS:
https://github.com/cerredz/Vidbyte-cli/blob/main/docs/design/python-cli-research-harness-program.md
explains invocation-owned I/O and stdout/stderr separation after this stack merges.

TESTS: No dedicated feature tests are added under the approved no-tests workflow.
scripts/smoke.py and scripts/run_ci.py exercise the CLI process boundary.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import TextIO


@dataclass(frozen=True)
class IOStreams:
    """Text channels owned by one CLI invocation."""

    stdin: TextIO
    stdout: TextIO
    stderr: TextIO

    @classmethod
    def system(cls) -> IOStreams:
        # Bind at invocation time so redirection performed after import remains visible.
        return cls(stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr)

    def write_output(self, message: str) -> None:
        # Ordinary command results use stdout so shell pipelines remain dependable.
        self.stdout.write(f"{message}\n")
        self.stdout.flush()

    def write_error(self, message: str) -> None:
        # Diagnostics use stderr so a failed command cannot corrupt structured stdout.
        self.stderr.write(f"{message}\n")
        self.stderr.flush()
