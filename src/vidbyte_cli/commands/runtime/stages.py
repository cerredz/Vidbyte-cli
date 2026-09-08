"""`vidbyte-cli runtime stages` runs caller-defined stages on fresh Codex agents.

Every stage is described entirely on the command line: each `--stage-*` option repeats once
per stage, and occurrence i of every option describes the agent that runs stage i. There is
no stage file, because review of PR #36 asked for a surface an agent can drive from argv
alone without first writing a document to disk. Sequential mode is the default and threads
the previous reply through `{{previous}}`; parallel mode fans every stage out at once. Only
`run` charges (one cent); `describe` stays offline so an agent can read the tunables first.
"""

from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

import click

from ...lib.constants.runtime import StagesLimit
from ...lib.constants.runtime import StagesProgress as Progress
from ...lib.errors.failures import (
    RuntimeAdmissionNotVerified,
    StagesOptionCountMismatch,
    StagesSettingsInvalid,
)
from ...lib.output import OutputDocument
from ...lib.runtime.context import ApplicationContext as Ctx
from ...lib.runtime_primitives.gate import RuntimeAdmissionGate
from ...lib.runtime_primitives.stages import StagesCodexSession
from ...types.provider import PROVIDER_ENV_VARS, Provider
from ...types.runtime import RuntimeAdmissionRequest as AdmitRequest
from ...types.runtime import RuntimeGrantVerificationRequest as VerifyRequest
from ...types.runtime import RuntimeHost as Host
from ...types.runtime import (
    StageApproval,
    StageEffort,
    StagePersonality,
    StageSandbox,
    StageSpec,
    StagesSettings,
    StageSummary,
)

_GROUP_HELP = (
    "Run one task through several ordered stages, each on its own brand-new Codex agent. A "
    "stage is a complete agent configuration - its own system prompt, turn prompt, model, "
    "effort, and sandbox - so an auditing stage and an implementing stage no longer have to "
    "share one set of standing instructions. Stages are described entirely with repeated "
    "--stage-* options on the run subcommand, never from a file, so a caller can build a "
    "whole staged flow in a single invocation. Run charges a flat one-cent Vidbyte admission "
    "however many stages the run holds, while every model call is billed to your own OpenAI "
    "account. Describe is offline and free, and prints every option a stage accepts."
)
_RUN_HELP = (
    "Admit and run every stage of TASK, one fresh Codex agent per stage, on this machine. "
    "TASK is the single top-level statement of what the whole run is for; it is what the "
    "first stage sees in place of {{previous}}, and in parallel mode what every stage sees. "
    "Stages are built by position from the repeated --stage-* options: the first "
    "--stage-prompt and --stage-system-prompt describe stage 1, the second pair describes "
    "stage 2, and so on, so --stage-prompt is what decides how many stages run. Each agent "
    "is discarded when its stage ends, which is the whole point of staging - no thread "
    "history, tool state, or context ever crosses a stage boundary. Vidbyte charges one cent "
    "to admit the run and refuses to start any stage until that admission is verified."
)
_DESCRIBE_HELP = (
    "Print every option a stage accepts, with the legal values for each closed-value setting, "
    "and exit. This subcommand touches no network, buys no admission, starts no agent, and "
    "costs nothing, so it is safe to call before deciding how to shape a run. It is written "
    "for a caller assembling a stages invocation programmatically: it names each --stage-* "
    "option, says what one occurrence of it configures, and lists the exact words the closed "
    "sets accept. Read it once and you have the whole surface without needing this "
    "repository. The same text is what --help expands on for each individual option."
)
_STAGE_PROMPT_HELP = (
    "The turn prompt for one stage, repeated once per stage in the order the stages run. This "
    "option is what defines the run: give it three times and three stages run, in that order. "
    "The token {{previous}} inside a prompt is replaced before the turn starts - in sequential "
    "mode with the previous stage's entire output, and for stage 1, or for every stage in "
    "parallel mode, with TASK itself. Write each prompt as a complete standalone instruction, "
    "because the agent running it has no thread history and has never seen the other stages. A "
    "run accepts between 1 and 25 prompts, and a blank one is rejected before payment."
)
_STAGE_SYSTEM_PROMPT_HELP = (
    "The system prompt for one stage, repeated once per stage in the same order as "
    "--stage-prompt. It must be given exactly as many times as --stage-prompt, because a "
    "stage without standing instructions of its own would silently inherit nothing. This is "
    "where a stage's role lives: what it is for, what it must not do, and what shape its "
    "output should take for whichever stage reads it next. It is applied when the stage's "
    "agent is built and is discarded with that agent, so it never leaks into another stage. A "
    "blank system prompt is rejected before credentials are read or any admission is bought."
)
_STAGE_NAME_HELP = (
    "A short label for one stage, repeated once per stage in the same order as "
    "--stage-prompt. Omit it entirely and the stages are named stage-1, stage-2, and so on, "
    "which is fine for a run you are not going to read progress output from. Give it and the "
    "name is used as the agent's name and in the per-stage progress lines, which is what makes "
    "a failure in a long run readable. Names need not be unique, are never sent to the backend "
    "with the admission request, and have no effect on ordering. Either give one per stage or "
    "give none at all; a partial list is rejected as a count mismatch."
)
_STAGE_MODEL_HELP = (
    "The model id one stage's agent runs on, repeated once per stage in the same order as "
    "--stage-prompt. Omit the option and every stage uses whatever model the installed Codex "
    "is already configured with, which is usually what you want. Pass an empty string for a "
    "single stage to leave that one stage on the configured default while pinning the others. "
    "This is the only stage setting with an open value set, so an unrecognized id is not "
    "caught here and fails inside Codex after the admission has already been charged. Use it "
    "to put a cheap model on early stages and a strong one on the stage that does the work."
)
_STAGE_EFFORT_HELP = (
    "How much reasoning one stage's agent spends before answering, repeated once per stage in "
    "the same order as --stage-prompt. Accepted values are none, minimal, low, medium, high, "
    "and xhigh, and the default for every stage is medium. Higher effort costs more tokens on "
    "your own OpenAI account and takes longer, and it is the single setting that most changes "
    "what a stage is capable of. Analysis, planning, and review stages usually justify high, "
    "while mechanical or formatting stages rarely do. Because the value set is closed, a "
    "misspelling is rejected by the parser instead of quietly falling back to a default."
)
_STAGE_SUMMARY_HELP = (
    "How much of its own reasoning one stage's agent reports back, repeated once per stage in "
    "the same order as --stage-prompt. Accepted values are none, auto, concise, and detailed, "
    "and the default for every stage is auto, which lets Codex decide. This changes what you "
    "read, not what the agent does, so it affects neither the result nor the one-cent "
    "admission. Choose detailed when a stage exists to show its reasoning to the stage that "
    "reads it next, and none when the summary is noise. Like the other closed-value settings, "
    "an unrecognized word fails at parse time, before any credential or wallet is touched."
)
_STAGE_SANDBOX_HELP = (
    "How far one stage's agent may reach into the filesystem, repeated once per stage in the "
    "same order as --stage-prompt. Accepted values are read-only, workspace-write, and "
    "full-access, and the default for every stage is workspace-write. Codex itself enforces "
    "the sandbox rather than this CLI, so it is a real boundary and not a hint to the model. "
    "Give read-only to stages that only inspect, audit, or plan, and reserve workspace-write "
    "for the stages that actually have to change files. full-access exists for the rare stage "
    "that must reach outside the working directory and is never right for an unattended run."
)
_STAGE_APPROVAL_HELP = (
    "What one stage's agent does when an action needs approval, repeated once per stage in the "
    "same order as --stage-prompt. Accepted values are auto_review and deny_all, and the "
    "default for every stage is auto_review. A staged run is not interactive, so neither value "
    "ever stops to prompt you: auto_review lets Codex review the action and proceed on its "
    "own, which is what keeps the run moving, while deny_all refuses it outright. Pair "
    "deny_all with a read-only sandbox for a stage that must not act under any circumstances. "
    "Both words come from a closed set that is validated before the wallet is touched."
)
_STAGE_PERSONALITY_HELP = (
    "The response personality one stage's agent writes in, repeated once per stage in the same "
    "order as --stage-prompt. Accepted values are none, friendly, and pragmatic, and the "
    "default for every stage is none. It changes tone and framing only - never capability, "
    "tool use, sandboxing, or cost. It is worth setting on a stage whose output a person will "
    "read and worth leaving alone on a stage whose output is consumed by the next stage. Each "
    "stage carries its own, so the stages of one run need not agree. An unrecognized value is "
    "rejected at parse time along with the rest of the closed-value options."
)
_STAGE_CONTEXT_HELP = (
    "Extra turn-scoped context for one stage, repeated once per stage in the same order as "
    "--stage-prompt. Use it for reference material rather than instruction: the file excerpt, "
    "the schema, or the prior decision a stage needs in front of it but that does not belong "
    "in the prompt itself. It is applied to that one stage only and never reaches another, so "
    "context two stages both need has to be given to both. Omit the option and every stage "
    "runs with none, which is the right choice when the prompt already says everything. It "
    "counts against the same token budget the prompt does, billed to your own OpenAI account."
)
_PARALLEL_HELP = (
    "Whether the stages all run at once instead of one after another. Sequential, the default, "
    "awaits each stage before starting the next and substitutes the finished output into the "
    "next stage's {{previous}} token, which is what lets a later stage build on an earlier "
    "one. Parallel starts every stage together and gives each one TASK as {{previous}}, so "
    "stages that depend on each other's results must not be run this way. Parallel finishes "
    "sooner in wall-clock time but runs every stage's model calls concurrently against your "
    "own OpenAI account. The one-cent Vidbyte admission is the same under either topology."
)
_IDEMPOTENCY_KEY_HELP = (
    "A caller-supplied key that makes the paid admission for this run replay-safe. Leave it "
    "unset and the CLI generates a fresh key, which is correct for every new run. Reuse a key "
    "from an earlier invocation only to recover an admission whose response you never saw, so "
    "the wallet is not charged twice for the same run. Reusing a key does not resume or "
    "deduplicate the stages themselves: every stage runs again from the first, and every model "
    "call is billed to your own OpenAI account again. The key must be 8 to 128 characters of "
    "letters, digits, and the punctuation . _ - and :, and is rejected before anything runs."
)
_KEY_PATTERN = r"[A-Za-z0-9._:-]{8,128}"
_SECRET_NAMES = (
    "GOOGLE_API_KEY",
    "VIDBYTE_API_KEY",
    "RUNTIME_ADMISSION_SIGNING_KEY",
    "CODEX_API_KEY",
)
_REFERENCE = (
    "Stages are built from repeated --stage-* options; occurrence i of every option describes "
    "the agent that runs stage i, and --stage-prompt decides how many stages there are.\n"
    "  --stage-prompt          required, 1-25 times; the turn prompt, where {{previous}} "
    "becomes the prior stage output (or TASK for stage 1 and for parallel runs)\n"
    "  --stage-system-prompt   required, once per stage; that stage's standing instructions\n"
    "  --stage-name            optional; defaults to stage-1, stage-2, ...\n"
    "  --stage-model           optional; open value set, empty means the configured default\n"
    "  --stage-effort          optional; none|minimal|low|medium|high|xhigh (default medium)\n"
    "  --stage-summary         optional; none|auto|concise|detailed (default auto)\n"
    "  --stage-sandbox         optional; read-only|workspace-write|full-access "
    "(default workspace-write)\n"
    "  --stage-approval        optional; auto_review|deny_all (default auto_review)\n"
    "  --stage-personality     optional; none|friendly|pragmatic (default none)\n"
    "  --stage-context         optional; turn-scoped reference material for that stage\n"
    "Each optional option must be given once per stage or omitted entirely.\n"
    "--parallel runs every stage at once; --sequential (the default) runs them in order."
)


class StagesCommand:
    """Owns the stages group: one priced run plus the offline option reference."""

    def register(self, parent: click.Group) -> None:
        # Attaches a subgroup so every stage tunable surfaces in nested --help.
        group = click.Group(name="stages", help=_GROUP_HELP)
        self._register_run(group)
        self._register_describe(group)
        parent.add_command(group)

    def _register_run(self, group: click.Group) -> None:
        # Declares the only priced path in this group, with one repeated option per knob.
        @group.command(name="run", help=_RUN_HELP)
        @click.argument("task")
        @click.option("--stage-prompt", "prompts", multiple=True, help=_STAGE_PROMPT_HELP)
        @click.option(
            "--stage-system-prompt", "systems", multiple=True, help=_STAGE_SYSTEM_PROMPT_HELP
        )
        @click.option("--stage-name", "names", multiple=True, help=_STAGE_NAME_HELP)
        @click.option("--stage-model", "models", multiple=True, help=_STAGE_MODEL_HELP)
        @click.option(
            "--stage-effort",
            "efforts",
            multiple=True,
            type=click.Choice(tuple(item.value for item in StageEffort)),
            help=_STAGE_EFFORT_HELP,
        )
        @click.option(
            "--stage-summary",
            "summaries",
            multiple=True,
            type=click.Choice(tuple(item.value for item in StageSummary)),
            help=_STAGE_SUMMARY_HELP,
        )
        @click.option(
            "--stage-sandbox",
            "sandboxes",
            multiple=True,
            type=click.Choice(tuple(item.value for item in StageSandbox)),
            help=_STAGE_SANDBOX_HELP,
        )
        @click.option(
            "--stage-approval",
            "approvals",
            multiple=True,
            type=click.Choice(tuple(item.value for item in StageApproval)),
            help=_STAGE_APPROVAL_HELP,
        )
        @click.option(
            "--stage-personality",
            "personalities",
            multiple=True,
            type=click.Choice(tuple(item.value for item in StagePersonality)),
            help=_STAGE_PERSONALITY_HELP,
        )
        @click.option("--stage-context", "contexts", multiple=True, help=_STAGE_CONTEXT_HELP)
        @click.option("--parallel/--sequential", default=False, help=_PARALLEL_HELP)
        @click.option("--idempotency-key", "key", default=None, help=_IDEMPOTENCY_KEY_HELP)
        @click.pass_obj
        def _run(ctx: Ctx, /, task: str, parallel: bool, key: str | None, **stages: object) -> None:
            # Delegates without normalizing the task text.
            self.execute_run(ctx, task, parallel, key, **stages)

    def _register_describe(self, group: click.Group) -> None:
        # Declares the offline tunable reference for stage authors.
        @group.command(name="describe", help=_DESCRIBE_HELP)
        @click.pass_obj
        def _describe(ctx: Ctx) -> None:
            # Delegates reference rendering to the owned method.
            self.execute_describe(ctx)

    def execute_run(
        self, ctx: Ctx, task: str, parallel: bool, key: str | None, **stages: object
    ) -> None:
        # Everything before ADMISSION is free, so every rejection a caller can cause happens
        # before the wallet is touched, and no stage starts until the grant is verified.
        progress = ctx.output().diagnostic
        progress(Progress.PREPARING)
        # The key is validated first because an invalid one would otherwise surface only after
        # the stages have been assembled and a host has been resolved on PATH.
        resolved_key = self._resolve_key(key)
        # Assembling the stages is pure argv work: it aligns the repeated options by position
        # and fails closed on a count mismatch, a blank prompt, or more than the stage ceiling.
        settings = self._settings(stages, parallel)
        planner = ctx.runtime_launch_planner()
        # The plan carries only the task and the resolved host; stage prompts are local and
        # never travel to the backend with the admission request.
        plan = planner.build(task, Host.CODEX, Path.cwd(), "runtime.stages@1")
        progress(Progress.CREDENTIALS)
        # Building the session imports the SDK and filters the child environment, so a missing
        # SDK or a missing provider key also fails before payment rather than after it.
        session = self._session(ctx)
        # prepare() constructs one agent per stage and starts no turn, which is what proves
        # every stage's settings are valid while the run is still free.
        session.prepare(plan, settings)
        endpoints = ctx.runtime_endpoints()
        progress(Progress.ADMISSION)
        # One flat one-cent admission covers the whole run, however many stages it holds.
        grant = endpoints.admit_stages(AdmitRequest(host=plan.host), resolved_key)
        if grant.grant_token is None:
            raise RuntimeAdmissionNotVerified("grant_token_missing")
        progress(Progress.VERIFYING)
        # The grant is re-read from the backend rather than trusted as returned, and the key
        # hash ties that verification to this exact invocation.
        hashed = RuntimeAdmissionGate.hash_idempotency_key(resolved_key)
        proof = VerifyRequest(grant_token=grant.grant_token, idempotency_key_hash=hashed)
        verified = endpoints.verify_grant(proof)
        verdict = RuntimeAdmissionGate().verify_online(plan, grant, verified)
        if not verdict.admitted:
            raise RuntimeAdmissionNotVerified(verdict.reason)
        progress(Progress.ADMITTED)
        # The executor receives the verified verdict and no endpoints at all, which is what
        # keeps the network out of stage execution.
        result = ctx.runtime_executor().execute_stages(plan, settings, session, verdict)
        # Only the run result reaches stdout; every phase line above went to stderr.
        ctx.output().result(
            OutputDocument(kind="runtime.stages", data=result.model_dump(mode="json")),
            result.text,
        )

    def execute_describe(self, ctx: Ctx) -> None:
        # Prints the option reference agents read before assembling a run.
        ctx.output().result(
            OutputDocument(kind="runtime.stages.reference", data={"reference": _REFERENCE}),
            _REFERENCE,
        )

    def _settings(self, stages: dict[str, object], parallel: bool) -> StagesSettings:
        # Builds the frozen settings by position, so occurrence i of every option is stage i.
        prompts = self._values(stages, "prompts")
        systems = self._aligned(stages, "systems", len(prompts))
        names = self._aligned(stages, "names", len(prompts))
        models = self._aligned(stages, "models", len(prompts))
        efforts = self._aligned(stages, "efforts", len(prompts))
        summaries = self._aligned(stages, "summaries", len(prompts))
        sandboxes = self._aligned(stages, "sandboxes", len(prompts))
        approvals = self._aligned(stages, "approvals", len(prompts))
        personalities = self._aligned(stages, "personalities", len(prompts))
        contexts = self._aligned(stages, "contexts", len(prompts))
        if not prompts or len(prompts) > StagesLimit.MAX_STAGES or not systems:
            raise StagesSettingsInvalid()
        specs = [
            self._spec(
                index,
                prompts[index],
                systems[index],
                names[index] if names else "",
                models[index] if models else "",
                efforts[index] if efforts else StageEffort.MEDIUM.value,
                summaries[index] if summaries else StageSummary.AUTO.value,
                sandboxes[index] if sandboxes else StageSandbox.WORKSPACE_WRITE.value,
                approvals[index] if approvals else StageApproval.AUTO_REVIEW.value,
                personalities[index] if personalities else StagePersonality.NONE.value,
                contexts[index] if contexts else "",
            )
            for index in range(len(prompts))
        ]
        try:
            return StagesSettings(stages=tuple(specs), parallel=parallel)
        except ValueError as error:
            raise StagesSettingsInvalid() from error

    def _spec(
        self,
        index: int,
        prompt: str,
        system_prompt: str,
        name: str,
        model: str,
        effort: str,
        summary: str,
        sandbox: str,
        approval: str,
        personality: str,
        context: str,
    ) -> StageSpec:
        # Names an unnamed stage by position so progress output stays readable either way.
        try:
            return StageSpec(
                name=name or f"stage-{index + 1}",
                prompt=prompt,
                system_prompt=system_prompt,
                model=model,
                effort=StageEffort(effort),
                summary=StageSummary(summary),
                sandbox=StageSandbox(sandbox),
                approval=StageApproval(approval),
                personality=StagePersonality(personality),
                additional_context=context,
            )
        except ValueError as error:
            raise StagesSettingsInvalid() from error

    def _values(self, stages: dict[str, object], key: str) -> tuple[str, ...]:
        # Reads one repeated option as the tuple of strings Click collected for it.
        collected = stages.get(key, ())
        if not isinstance(collected, tuple):
            raise StagesSettingsInvalid()
        return tuple(str(item) for item in collected)

    def _aligned(self, stages: dict[str, object], key: str, count: int) -> tuple[str, ...]:
        # An optional option is legal only when omitted entirely or given once per stage.
        values = self._values(stages, key)
        if values and len(values) != count:
            raise StagesOptionCountMismatch()
        return values

    def _resolve_key(self, key: str | None) -> str:
        # Generates or validates the replay-safe admission key.
        resolved = key or str(uuid4())
        if re.fullmatch(_KEY_PATTERN, resolved) is None:
            raise click.BadParameter("Use 8-128 key chars: letters, digits, ._-:.")
        return resolved

    def _session(self, ctx: Ctx) -> StagesCodexSession:
        # Sanitizes the child environment so only the selected key is inherited.
        credentials = ctx.require_provider_credentials(Provider.OPENAI)
        environment = dict(ctx.environment)
        for name in (*PROVIDER_ENV_VARS.values(), *_SECRET_NAMES):
            environment[name] = ""
        environment["OPENAI_API_KEY"] = credentials.secret_value()
        return StagesCodexSession(environment, ctx.output().diagnostic)
