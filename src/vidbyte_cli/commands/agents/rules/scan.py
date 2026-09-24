"""`vidbyte-cli agents rules scan` and `resume`: turn past prompts into one rules document.

`scan` validates scope and limits, reads prompts locally, stores a batched plan, and only then
resolves credentials and runs paid batches. `resume` reloads a stored plan, re-reads the same
prompts by ID, and runs only the batches that never finished, so no batch is bought twice.
"""

from __future__ import annotations

from pathlib import Path

import click

from ....lib.constants.rules import RulesCap
from ....lib.errors.failures import RulesNoPromptsFound
from ....lib.runtime.context import ApplicationContext
from ....services.rules.runner import RulesScanPlanner
from ....services.rules.store import RulesScanStore
from ....services.rules.transcripts import TranscriptLibrary
from ....types.rules import RulesScanManifest
from .execution import RulesScanExecution
from .options import DurationParser, MoneyParser, RulesLimitOptions, RulesScopeOptions

_SCAN_HELP = (
    "Read the prompts you typed into coding agents and turn the ones that state a lasting rule "
    "into one Markdown document. "
    "Prompts are read locally from Claude Code, Codex, Grok Build, and OpenCode transcripts, then "
    "sent in small paid batches "
    "where TypeSafe Jev flags standing preferences and a hosted agent writes them up as rules. "
    "Every batch is metered against your Vidbyte API wallet, and the spend limit, time limit, and "
    "batch cost cap stop the scan "
    "before it spends more than you allowed. "
    "The scan is stored locally, so a scan that stops early continues with the resume verb and "
    "never pays for a batch twice."
)
_RESUME_HELP = (
    "Continue a stored rules scan named by SCAN_ID from the first batch that did not finish. "
    "The scan's original hosts, dates, project, and limits are reused, and its prompts are "
    "re-read from the same transcripts by ID. "
    "Pass --max-spend to raise the spend cap of a scan that stopped on its budget, or "
    "--time-limit to bound this run. "
    "Batches that already finished are never sent or charged again, and the rules document is "
    "rewritten from every finished batch."
)
_OUT_HELP = (
    "Also write the finished rules document to this file path, in addition to the copy kept in "
    "the scan folder. "
    "Parent folders are created when they do not exist, and an existing file at the path is "
    "replaced. "
    "Use it to drop the document straight into a repository, for example as docs/agent-rules.md. "
    "The path printed in the result always points at the scan folder's own copy."
)
_DRY_RUN_HELP = (
    "Read and select prompts, store the batched plan, and stop before any credential is used or "
    "anything is charged. "
    "The result reports how many prompts and batches the scan would send and the spend cap it "
    "would run under. "
    "The stored plan is a real scan, so running the printed resume command executes exactly that "
    "plan. "
    "Use it to check a scope and its size before paying for it."
)
_RESUME_SPEND_HELP = (
    "Replace this scan's total spend cap with a new dollar amount, for example 5.00. "
    "The cap still counts everything the scan already spent, so it must be higher than that "
    "amount to allow another batch. "
    "Use it when a scan stopped with the spend_limit reason and you want it to finish. "
    "Omit it to keep the cap the scan was created with."
)
_RESUME_TIME_HELP = (
    "Stop sending new batches once this much wall-clock time has passed in this resumed run, such "
    "as 20m or 1h. "
    "A batch already in flight is allowed to finish, so the run never discards work it paid for. "
    "The limit applies only to this run and replaces any time limit stored with the scan. "
    "Omit it to keep the scan's stored time limit."
)


class RulesScanCommand:
    """Registers and executes `agents rules scan`."""

    def register(self, parent: click.Group) -> None:
        # Options are attached before the group takes the callback, so help lists them in order.
        def _run(context: ApplicationContext, /, **values: object) -> None:
            self.execute(context, values)

        callback = click.option("--dry-run", is_flag=True, help=_DRY_RUN_HELP)(click.pass_obj(_run))
        callback = click.option(
            "--out", type=click.Path(dir_okay=False, path_type=Path), default=None, help=_OUT_HELP
        )(callback)
        callback = RulesLimitOptions().apply(RulesScopeOptions().apply(callback))
        parent.command(name="scan", help=_SCAN_HELP)(callback)

    def execute(self, context: ApplicationContext, values: dict[str, object]) -> None:
        # Validate, read, plan, and store before anything paid; then run and publish.
        scope = RulesScopeOptions().build(values)
        limits = RulesLimitOptions().build(values)
        prompts = TranscriptLibrary().prompts(scope)
        if not prompts:
            raise RulesNoPromptsFound()
        store = RulesScanStore(context.paths())
        manifest = RulesScanPlanner().plan(store.create_scan_id(), scope, limits, prompts)
        store.save_manifest(manifest)
        out = values.get("out")
        if values.get("dry_run"):
            RulesScanExecution(context, store).publish(
                manifest, out if isinstance(out, Path) else None
            )
            return
        RulesScanExecution(context, store).run(
            manifest,
            {prompt.prompt_id: prompt for prompt in prompts},
            out if isinstance(out, Path) else None,
        )


class RulesResumeCommand:
    """Registers and executes `agents rules resume`."""

    def register(self, parent: click.Group) -> None:
        # SCAN_ID is the only required input; the stored manifest supplies everything else.
        def _run(context: ApplicationContext, /, **values: object) -> None:
            self.execute(context, values)

        callback = click.option(
            "--out", type=click.Path(dir_okay=False, path_type=Path), default=None, help=_OUT_HELP
        )(click.pass_obj(_run))
        callback = click.option(
            "--time-limit", "time_limit_text", type=str, default=None, help=_RESUME_TIME_HELP
        )(callback)
        callback = click.option(
            "--max-spend", "max_spend_text", type=str, default=None, help=_RESUME_SPEND_HELP
        )(callback)
        parent.command(name="resume", help=_RESUME_HELP)(click.argument("scan_id")(callback))

    def execute(self, context: ApplicationContext, values: dict[str, object]) -> None:
        # Reloads the plan, applies any limit overrides, re-reads prompts by ID, and runs.
        store = RulesScanStore(context.paths())
        manifest = self._with_overrides(store.load_manifest(str(values["scan_id"])), values)
        out = values.get("out")
        if not manifest.pending_batches:
            RulesScanExecution(context, store).publish(
                manifest, out if isinstance(out, Path) else None
            )
            return
        # Caps are dropped on re-read so newer sessions cannot push planned prompts out.
        scope = manifest.scope.model_copy(update={"max_sessions": None, "max_prompts": None})
        prompts = {prompt.prompt_id: prompt for prompt in TranscriptLibrary().prompts(scope)}
        RulesScanExecution(context, store).run(
            manifest, prompts, out if isinstance(out, Path) else None
        )

    @staticmethod
    def _with_overrides(
        manifest: RulesScanManifest, values: dict[str, object]
    ) -> RulesScanManifest:
        # Replaces the stored spend cap or time limit only when the caller passed a new one.
        updates: dict[str, object] = {}
        if values.get("max_spend_text"):
            updates["max_spend_cents"] = MoneyParser.cents(
                "--max-spend", str(values["max_spend_text"]), maximum=RulesCap.MAX_SPEND_CENTS
            )
        if values.get("time_limit_text"):
            updates["time_limit_seconds"] = DurationParser().seconds(
                "--time-limit", str(values["time_limit_text"])
            )
        if updates:
            manifest.limits = manifest.limits.model_copy(update=updates)
        return manifest
