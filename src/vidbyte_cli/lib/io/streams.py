"""The process channels one CLI invocation writes to, as an injected dependency.

Reusable code never touches `sys.stdout`/`sys.stderr` directly, so the CLI can be embedded,
redirected, or captured without monkey-patching `sys`. Formatting policy (human vs JSON,
color) is deliberately NOT here — `lib/output` owns it.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import TextIO


@dataclass(frozen=True)
class IOStreams:
    """The stdin/stdout/stderr triple owned by one invocation."""

    stdin: TextIO
    stdout: TextIO
    stderr: TextIO

    @classmethod
    def system(cls) -> IOStreams:
        # Bound at invocation time, not import time, so redirection set up by an embedding
        # caller after `import vidbyte_cli` is still honoured.
        return cls(stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr)

    def write_output(self, message: str) -> None:
        # Results go to stdout so shell pipelines stay dependable.
        self.stdout.write(f"{message}\n")
        self.stdout.flush()

    def write_error(self, message: str) -> None:
        # Diagnostics go to stderr so a failure can't corrupt structured stdout.
        self.stderr.write(f"{message}\n")
        self.stderr.flush()
