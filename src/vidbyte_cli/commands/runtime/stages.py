"""`vidbyte-cli runtime stages` runs caller-defined stages on fresh Codex agents.

Each stages[] entry maps to exactly one new CodexHarnessAgent: entry i is
the full agent configuration for the agent that runs stage i. Sequential
mode is the default and threads the previous reply through {{previous}};
parallel mode fans every stage out at once. Only run charges (one cent);
the helpers stay offline so agents can preview tunables first.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from uuid import uuid4

import click

from ...lib.constants.runtime import StagesProgress as Progress
from ...lib.errors.failures import RuntimeAdmissionNotVerified
from ...lib.output import OutputDocument
from ...lib.runtime.context import ApplicationContext as Ctx
from ...lib.runtime_primitives.gate import RuntimeAdmissionGate
from ...lib.runtime_primitives.stages import StagesCodexSession, StagesFile
from ...types.provider import PROVIDER_ENV_VARS, Provider
from ...types.runtime import RuntimeAdmissionRequest as AdmitRequest
from ...types.runtime import RuntimeGrantVerificationRequest as VerifyRequest
from ...types.runtime import RuntimeHost as Host
from ...types.runtime import StageSpec as Spec

_KEY_HELP = "Reuse only to recover admission."
_FILE_HELP = "JSON file holding stages[] and the parallel flag."
_SECRET_NAMES = (
    "GOOGLE_API_KEY",
    "VIDBYTE_API_KEY",
    "RUNTIME_ADMISSION_SIGNING_KEY",
    "CODEX_API_KEY",
)


class StagesCommand:
    """Owns the stages group: one priced run plus three offline helpers."""

    def register(self, parent: click.Group) -> None:
        # Attaches a subgroup so tunables surface in nested --help.
        group = click.Group(name="stages", help="Staged work, one Codex agent per stage")
        self._register_run(group)
        self._register_add(group)
        self._register_list(group)
        self._register_describe(group)
        parent.add_command(group)

    def _register_run(self, group: click.Group) -> None:
        # Declares the only priced path in this group.
        @group.command(name="run", help="Admit and run stages (1 cent)")
        @click.argument("task")
        @click.option("--stages-file", "file", required=True, help=_FILE_HELP)
        @click.option("--parallel/--sequential", default=False, help="Fan out, or run in order.")
        @click.option("--idempotency-key", "key", default=None, help=_KEY_HELP)
        @click.pass_obj
        def _run(ctx: Ctx, task: str, file: str, parallel: bool, key: str | None) -> None:
            # Delegates without normalizing the task text.
            self.execute_run(ctx, task, file, parallel, key)

    def _register_add(self, group: click.Group) -> None:
        # Declares the offline stage builder with per-agent knobs.
        @group.command(name="add", help="Append one stage to a file (offline)")
        @click.option("--file", "path", required=True, help="File to create or extend.")
        @click.option("--name", required=True, help="Stage and agent name.")
        @click.option("--prompt", required=True, help="Turn prompt; {{previous}} = prior output.")
        @click.option("--system-prompt", "sys", required=True, help="System prompt per stage.")
        @click.option("--model", default="", help="Model id; empty = default.")
        @click.option("--effort", default="medium", help="none|minimal|low|medium|high|xhigh.")
        @click.option("--summary", default="auto", help="none|auto|concise|detailed.")
        @click.option(
            "--sandbox", "box", default="workspace-write", help="Sandbox for the stage agent."
        )
        @click.option("--approval", default="auto_review", help="auto_review|deny_all.")
        @click.option("--personality", "pers", default="none", help="none|friendly|pragmatic.")
        @click.pass_obj
        def _add(ctx: Ctx, /, **opts: str) -> None:
            # Forwards named stage fields to the owned method.
            self.execute_add(ctx, **opts)

    def _register_list(self, group: click.Group) -> None:
        # Declares the offline index reader for a stages file.
        @group.command(name="list", help="Show stage index (offline)")
        @click.option("--stages-file", "file", required=True, help=_FILE_HELP)
        @click.pass_obj
        def _list(ctx: Ctx, file: str) -> None:
            # Delegates rendering to the owned method.
            self.execute_list(ctx, file)

    def _register_describe(self, group: click.Group) -> None:
        # Declares the offline tunable reference for stage authors.
        @group.command(name="describe", help="Explain every tunable (offline)")
        @click.pass_obj
        def _describe(ctx: Ctx) -> None:
            # Delegates reference rendering to the owned method.
            self.execute_describe(ctx)

    def execute_run(self, ctx: Ctx, task: str, file: str, parallel: bool, key: str | None) -> None:
        # Resolves free prerequisites first, then admits, verifies, executes.
        progress = ctx.output().diagnostic
        progress(Progress.PREPARING)
        resolved_key = self._resolve_key(key)
        planner = ctx.runtime_launch_planner()
        plan = planner.build(task, Host.CODEX, Path.cwd(), "runtime.stages@1")
        settings = StagesFile().load(file)
        if parallel:
            settings = settings.model_copy(update={"parallel": True})
        progress(Progress.CREDENTIALS)
        session = self._session(ctx)
        session.prepare(plan, settings)
        endpoints = ctx.runtime_endpoints()
        progress(Progress.ADMISSION)
        grant = endpoints.admit_stages(AdmitRequest(host=plan.host), resolved_key)
        if grant.grant_token is None:
            raise RuntimeAdmissionNotVerified("grant_token_missing")
        progress(Progress.VERIFYING)
        hashed = RuntimeAdmissionGate.hash_idempotency_key(resolved_key)
        proof = VerifyRequest(grant_token=grant.grant_token, idempotency_key_hash=hashed)
        verified = endpoints.verify_grant(proof)
        verdict = RuntimeAdmissionGate().verify_online(plan, grant, verified)
        if not verdict.admitted:
            raise RuntimeAdmissionNotVerified(verdict.reason)
        progress(Progress.ADMITTED)
        result = ctx.runtime_executor().execute_stages(plan, settings, session, verdict)
        ctx.output().result(self._document(result), result.text)

    def execute_add(self, ctx: Ctx, **opts: str) -> None:
        # Appends one validated stage to the JSON file with no network call.
        _ = ctx
        spec = Spec(
            name=opts["name"],
            prompt=opts["prompt"],
            system_prompt=opts["sys"],
            model=opts.get("model", ""),
            effort=opts.get("effort", "medium"),
            summary=opts.get("summary", "auto"),
            sandbox=opts.get("box", "workspace-write"),
            approval=opts.get("approval", "auto_review"),
            personality=opts.get("pers", "none"),
        )
        existing: list[object] = []
        target = Path(opts["path"])
        if target.exists():
            raw = json.loads(target.read_text(encoding="utf-8"))
            existing = list(raw.get("stages", []))
        existing.append(spec.model_dump(mode="json"))
        payload = json.dumps({"stages": existing, "parallel": False}, indent=2)
        target.write_text(payload, encoding="utf-8")

    def execute_list(self, ctx: Ctx, file: str) -> None:
        # Renders one line per stage plus the machine-readable settings.
        settings = StagesFile().load(file)
        rows = [
            self._row(i, s.name, s.model, s.effort, s.sandbox)
            for i, s in enumerate(settings.stages)
        ]
        ctx.output().result(self._index_document(settings), "\n".join(rows))

    def execute_describe(self, ctx: Ctx) -> None:
        # Prints the tunable reference agents read before authoring stages.
        text = StagesFile().describe()
        ctx.output().result(self._reference_document(text), text)

    def _row(self, index: int, name: str, model: str, effort: str, sandbox: str) -> str:
        # Formats one offline index line without quoting stage text.
        resolved = model or "default"
        return f"{index}: {name} (model={resolved}, effort={effort}, sandbox={sandbox})"

    def _document(self, result: object) -> OutputDocument:
        # Wraps the run result for the stdout-only result contract.
        return OutputDocument(kind="runtime.stages", data=result.model_dump(mode="json"))  # type: ignore[attr-defined]

    def _index_document(self, settings: object) -> OutputDocument:
        # Wraps the offline index for the stdout-only result contract.
        return OutputDocument(kind="runtime.stages.index", data=settings.model_dump(mode="json"))  # type: ignore[attr-defined]

    def _reference_document(self, text: str) -> OutputDocument:
        # Wraps the tunable reference for the stdout-only result contract.
        return OutputDocument(kind="runtime.stages.reference", data={"reference": text})

    def _resolve_key(self, key: str | None) -> str:
        # Generates or validates the replay-safe admission key.
        resolved = key or str(uuid4())
        if re.fullmatch(r"[A-Za-z0-9._:-]{8,128}", resolved) is None:
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
