"""FILE: src/vidbyte_cli/commands/harness/run.py

PURPOSE: Provides the low-level manifest-free generic harness mutation with explicit dirty
repository, idempotency, waiting, recovery-journal, and output policy.

TESTS: No feature tests are added under the approved no-tests workflow.
"""

from __future__ import annotations

import hashlib

import click

from ...lib.errors import CliError, CliErrorCode
from ...lib.operations import PendingOperation
from ...lib.output import OutputDocument
from ...lib.runtime.context import ApplicationContext
from ...types.harness import HarnessRunCreateRequest


class HarnessRunCommand:
    def register(self, parent: click.Group) -> None:
        @parent.command(name="run", help="Run a harness against the current repo (generic)")
        @click.argument("name")
        @click.option("--task", required=True, help="What the harness should do.")
        @click.option("--idempotency-key", help="Reuse one logical mutation identity.")
        @click.option("--wait/--no-wait", default=True, show_default=True)
        @click.option("--timeout", type=click.FloatRange(min=1.0), default=None)
        @click.option("--allow-dirty", is_flag=True, help="Permit uncommitted repository state.")
        @click.pass_obj
        def _run(
            context: ApplicationContext,
            name: str,
            task: str,
            idempotency_key: str | None,
            wait: bool,
            timeout: float | None,
            allow_dirty: bool,
        ) -> None:
            self.execute(context, name, task, idempotency_key, wait, timeout, allow_dirty)

    def execute(
        self,
        context: ApplicationContext,
        name: str,
        task: str,
        explicit_key: str | None,
        wait: bool,
        timeout: float | None,
        allow_dirty: bool,
    ) -> None:
        if not task.strip() or len(task) > 20_000:
            raise CliError(
                CliErrorCode.INVALID_ARGUMENT,
                "The task must contain between 1 and 20,000 characters.",
                2,
            )
        harness = context.harness_context()
        repo = harness.repo.inspect()
        if repo.is_dirty and not allow_dirty:
            raise CliError(
                CliErrorCode.OPERATION_FAILED,
                "The current repository has uncommitted changes.",
                hint="Commit/stash changes or pass --allow-dirty explicitly.",
            )
        request = HarnessRunCreateRequest(
            harness=name,
            command="run",
            args={"task": task},
            repo=repo.as_ref(),
        )
        key = harness.idempotency.create(explicit_key)
        fingerprint = hashlib.sha256(request.model_dump_json().encode("utf-8")).hexdigest()
        harness.journal.begin(
            PendingOperation(
                operation_id=key,
                command=f"harness run {name}",
                idempotency_key=key,
                request_fingerprint=fingerprint,
                recovery_command=f"Retry with --idempotency-key {key}",
            )
        )
        run = context.harness_endpoints().create_run(request, key)
        harness.journal.accepted(
            key,
            run.run_id,
            f"vidbyte-cli harness status {run.run_id}",
        )
        if wait:
            run = harness.watch_run(run.run_id, timeout)
        context.output().result(
            OutputDocument(
                kind="harness.run",
                data={
                    "run_id": run.run_id,
                    "harness": run.harness,
                    "command": run.command,
                    "status": run.status,
                },
            ),
            harness.render.render_status(run),
        )
