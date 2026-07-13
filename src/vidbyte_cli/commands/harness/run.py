"""`vidbyte-cli harness run <name> --task` — the low-level, generic run escape hatch.

The ergonomic path is the generated `vidbyte-cli harness <name> <command> ...` built from a
manifest. This command stays as the manifest-free path: it forwards a raw invocation for
*any* harness (useful for scripting, or harnesses that haven't published a manifest). It
maps onto the same envelope as everything else: `--task` becomes command="run",
args={"task": ...}.
"""

from __future__ import annotations

import click

from ...lib.errors.cli_error import not_implemented


class HarnessRunCommand:
    def register(self, parent: click.Group) -> None:
        @parent.command(name="run", help="Run a harness against the current repo (generic)")
        @click.argument("name")
        @click.option("--task", required=True, help="what the harness should do")
        def _run(name: str, task: str) -> None:
            self.execute(name, task)

    def execute(self, name: str, task: str) -> None:
        # Will inspect the repo, submit {harness: name, command: "run", args: {task}}, and
        # stream status until done.
        raise not_implemented("'vidbyte-cli harness run'")
