"""FILE: src/vidbyte_cli/lib/harness/base.py

PURPOSE: Implements the lifecycle shared by every hand-written and manifest-backed harness:
build a Click subtree, guard execution, translate inputs, submit a backend run, optionally
wait, present the result, and normalize failures. Harness-specific command definitions and
result policy do not belong in this base class.

ROLE IN CODEBASE: harnesses/* and ManifestHarness subclass BaseHarness. HarnessRegistry
calls register(); generated Click callbacks call dispatch(). HarnessContext supplies
credentials, repository inspection, endpoints, logging, and rendering. InvocationBuilder
creates the wire request, while harness/errors.py maps unexpected backend failures.

ARCHITECTURE NOTE: This is the mechanism side of the mechanism/policy split documented in
docs/architecture.md. Static and manifest harnesses intentionally converge here so the
runtime does not branch after namespace resolution.

FUNCTION INVENTORY (reviewed 2026-07-26):
- BaseHarness.commands(ctx) -> list[HarnessCommandDef]: subclass command declaration contract.
- BaseHarness.register(parent, ctx) -> None: builds one side-effect-free Click subtree.
- BaseHarness.dispatch(command_def, params, ctx) -> None: executes the shared backend lifecycle.

COMMON MODIFICATION PATTERNS: Add a concern here only when every harness needs it, then
update HarnessContext, HarnessCommandDef, docs/architecture.md, and this header together.
Add per-harness behavior through command hooks or a policy module instead.

WHAT NOT TO DO IN THIS FILE:
1. Do not define a specific harness's commands; harnesses/* or feature slices own them.
2. Do not call HTTPX directly; HarnessEndpoints and lib/api own transport.
3. Do not print or call sys.exit; output collaborators and runtime own those boundaries.
4. Do not load manifests; HarnessCatalog and HarnessRegistry own resolution.
5. Do not perform service construction while building the Click tree.
6. Do not execute backend-provided code; manifests are data only.

KNOWN EDGE CASES: A harness can be repository-free, boolean options need Click flag
semantics, and required options with no default must omit Click's default parameter.
Backend failures are normalized while an existing CliError is preserved unchanged.

COMMON ERRORS RAISED BY THIS FILE: CliError can come from credential guards, repository
inspection, invocation validation, endpoint calls, waiting, or presentation. Other
exceptions are converted by map_harness_error() before leaving dispatch().

RELATED DOCS:
- https://github.com/cerredz/Vidbyte-cli/blob/main/docs/architecture.md explains the generic
  harness mechanism and policy boundary.
- https://github.com/cerredz/Vidbyte-cli/blob/main/docs/design/harness-runtime-and-cli-scaffold.md
  records the original accepted runtime design.

TESTS: No dedicated feature tests are added under the approved no-tests workflow.
scripts/smoke.py builds a static harness subtree; scripts/run_ci.py runs strict typing.
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any, ClassVar

import click

from ...types.harness import HarnessRepoRef, HarnessRun, HarnessRunCreateRequest
from ...types.manifest import OptionSpec, OptionType
from ..errors.cli_error import CliError
from ..errors.codes import CliErrorCode
from ..operations import PendingOperation
from ..output import OutputDocument
from .context import HarnessContext
from .errors import map_harness_error
from .invocation import InvocationBuilder
from .types import HarnessCommandDef

_CommandDef = HarnessCommandDef
_Context = HarnessContext
_Params = dict[str, object]
_Repo = HarnessRepoRef
_Request = HarnessRunCreateRequest


class BaseHarness(ABC):
    """Common registration and backend-dispatch mechanism for harness policy modules."""

    name: str
    description: str
    requires_repo: ClassVar[bool] = False
    _invocation: ClassVar[InvocationBuilder] = InvocationBuilder()
    # Click 8.4 made ParamType generic while our supported Click 8.1 baseline is not.
    # Keep the compatibility boundary dynamic; all values remain concrete Click types.
    _CLICK_TYPES: ClassVar[dict[OptionType, Any]] = {
        "string": click.STRING,
        "number": click.FLOAT,
        "path": click.Path(),
    }

    @abstractmethod
    def commands(self, ctx: _Context) -> list[_CommandDef]:
        # Subclasses declare policy as data while the base owns registration and execution.
        raise NotImplementedError

    def register(self, parent: click.Group, ctx: _Context) -> None:
        # Tree construction remains free of credential, repository, and network access.
        group = click.Group(name=self.name, help=self.description)
        for command_def in self.commands(ctx):
            group.add_command(self._build_click_command(command_def, ctx))
        parent.add_command(group)

    # @intent backend-harness-dispatch-boundary
    # This method is the client-side boundary for starting a billable, persistent backend
    # harness run. Authentication must fail before repository inspection or network work so
    # an unauthenticated invocation cannot perform surprising local or remote operations.
    #
    # Static and manifest-backed commands must use the same path. A plausible rewrite that
    # lets one source submit directly would bypass generic request translation, waiting,
    # safe presentation, or backend error normalization and make harness behavior depend on
    # how its namespace was discovered.
    #
    # Keep CliError passthrough intact: those errors are already classified as user-safe.
    # Every other exception is normalized at this boundary so the runtime never needs to
    # understand provider- or harness-specific failure classes.
    def dispatch(self, command: _CommandDef, params: _Params, ctx: _Context) -> None:
        # Orchestrate the shared lifecycle while leaf methods own translation and rendering.
        ctx.require_api_key()
        try:
            result = self._submit_run(command, params, ctx)
            self._present_run(command, result, ctx)
        except CliError:
            raise
        except Exception as error:  # noqa: BLE001 - normalize the backend boundary.
            raise map_harness_error(error) from error

    def _submit_run(self, command: _CommandDef, params: _Params, ctx: _Context) -> HarnessRun:
        # Create one request and optionally resolve its backend run before presentation.
        repo = None
        if self.requires_repo:
            repo_info = ctx.repo.inspect()
            if repo_info.is_dirty:
                raise CliError(
                    CliErrorCode.OPERATION_FAILED,
                    "The current repository has uncommitted changes.",
                    hint="Commit or stash changes before running this harness.",
                )
            repo = repo_info.as_ref()
        request = self._to_invocation(command, params, repo)
        idempotency_key = ctx.idempotency.create()
        operation_id = idempotency_key
        fingerprint = hashlib.sha256(request.model_dump_json().encode("utf-8")).hexdigest()
        ctx.journal.begin(
            PendingOperation(
                operation_id=operation_id,
                command=f"harness {self.name} {command.name}",
                idempotency_key=idempotency_key,
                request_fingerprint=fingerprint,
                recovery_command=f"Retry with idempotency key {idempotency_key}",
            )
        )
        submitted = ctx.harness_endpoints().create_run(request, idempotency_key)
        ctx.journal.accepted(
            operation_id,
            submitted.run_id,
            f"vidbyte-cli harness status {submitted.run_id}",
        )
        if command.mode == "await":
            return ctx.watch_run(submitted.run_id)
        return submitted

    def _present_run(self, command: _CommandDef, run: HarnessRun, ctx: _Context) -> None:
        # Prefer a command-specific presenter and otherwise use the shared status renderer.
        if command.present is not None:
            output = command.present(run, ctx)
        else:
            output = ctx.render.render_status(run)
        ctx.output.result(
            OutputDocument(
                kind="harness.run",
                data={
                    "run_id": run.run_id,
                    "harness": run.harness,
                    "command": run.command,
                    "status": run.status,
                },
            ),
            output,
        )

    def _to_invocation(self, command: _CommandDef, params: _Params, repo: _Repo | None) -> _Request:
        # Use a command's translation hook only when the shared envelope mapping is insufficient.
        if command.to_invocation is not None:
            return command.to_invocation(params, repo)
        return self._invocation.build(self.name, command, params, repo)

    def _build_click_command(self, command: _CommandDef, ctx: _Context) -> click.Command:
        # Render one typed definition into Click objects without touching runtime services.
        params: list[click.Parameter] = []
        for argument in command.args:
            name = argument.name.replace("-", "_")
            params.append(click.Argument([name], required=argument.required))
        for option in command.options:
            params.append(self._build_click_option(option))

        def callback(**kwargs: object) -> None:
            self.dispatch(command, kwargs, ctx)

        callback_typed: Callable[..., None] = callback
        return click.Command(
            name=command.name,
            params=params,
            help=command.description,
            callback=callback_typed,
        )

    def _build_click_option(self, option: OptionSpec) -> click.Option:
        # Preserve Click's distinction between no default and an explicit default of None.
        declaration = [f"--{option.name}"]
        if option.type == "boolean":
            return click.Option(
                declaration,
                is_flag=True,
                default=bool(option.default),
                help=option.description,
            )
        if option.default is not None:
            return click.Option(
                declaration,
                type=self._CLICK_TYPES[option.type],
                required=option.required,
                default=option.default,
                help=option.description,
            )
        return click.Option(
            declaration,
            type=self._CLICK_TYPES[option.type],
            required=option.required,
            help=option.description,
        )
