"""BaseHarness: the boilerplate every harness shares, written once.

A harness author extends this and implements `commands()`. The base owns everything that is
identical for every harness: turning command definitions into a click command tree
(`register`), and the submit -> (await) -> present -> map-errors lifecycle every command runs
(`dispatch`). All of that lives on the class — there are no loose module-level helpers
(resolves the base.py:150 review comment). Authors never touch click or httpx directly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import ClassVar

import click

from ...types.harness import HarnessRepoRef, HarnessRun, HarnessRunCreateRequest
from ...types.manifest import OptionSpec, OptionType
from ..errors.cli_error import CliError, not_implemented
from .context import HarnessContext
from .errors import map_harness_error
from .invocation import InvocationBuilder
from .types import HarnessCommandDef


class BaseHarness(ABC):
    # Every harness declares a namespace and a set of commands; the base does the rest.
    name: str
    description: str
    # Not every harness runs against a git repo (resolves the base.py:47 review comment). A
    # harness that operates on the caller's checkout (e.g. software-engineering) sets this
    # True; dispatch then attaches the repo ref. Others submit with no repo.
    requires_repo: ClassVar[bool] = False

    # The shared translation layer: one instance is enough since it is stateless.
    _invocation: ClassVar[InvocationBuilder] = InvocationBuilder()

    _CLICK_TYPES: ClassVar[dict[OptionType, click.ParamType[object]]] = {
        "string": click.STRING,
        "number": click.FLOAT,
        "path": click.Path(),
    }

    @abstractmethod
    def commands(self, ctx: HarnessContext) -> list[HarnessCommandDef]:
        # The command surface of this harness (static list, or mapped from a manifest).
        raise NotImplementedError

    def register(self, parent: click.Group, ctx: HarnessContext) -> None:
        # Builds `vidbyte-cli harness <name> <command> ...` under the given parent group.
        group = click.Group(name=self.name, help=self.description)
        for command_def in self.commands(ctx):
            group.add_command(self._build_click_command(command_def, ctx))
        parent.add_command(group)

    def dispatch(
        self, command_def: HarnessCommandDef, params: dict[str, object], ctx: HarnessContext
    ) -> None:
        # The uniform lifecycle every harness command follows. This is the shared "command
        # structure" made literal: guard -> translate -> submit -> (await) -> present.
        ctx.require_api_key()  # fail fast before any repo/network work
        repo = ctx.repo.as_repo_ref() if self.requires_repo else None
        request = self._to_invocation(command_def, params, repo)
        endpoints = ctx.harness_endpoints()
        try:
            submitted = endpoints.create_run(request)
            result = self._wait_for_run(submitted) if command_def.mode == "await" else submitted
            output = (
                command_def.present(result, ctx)
                if command_def.present
                else ctx.render.render_status(result)
            )
            ctx.logger.info(output)
        except CliError:
            raise
        except Exception as error:  # noqa: BLE001 - normalize any backend failure
            raise map_harness_error(error) from error

    def _to_invocation(
        self,
        command_def: HarnessCommandDef,
        params: dict[str, object],
        repo: HarnessRepoRef | None,
    ) -> HarnessRunCreateRequest:
        # Uses the command's own translation hook, or the shared invocation layer's default.
        if command_def.to_invocation is not None:
            return command_def.to_invocation(params, repo)
        return self._invocation.build(self.name, command_def, params, repo)

    def _wait_for_run(self, run: HarnessRun) -> HarnessRun:
        # Polls the run to a terminal state with backoff; shared by every `await`-mode command.
        raise not_implemented("harness run waiting")

    def _build_click_command(
        self, command_def: HarnessCommandDef, ctx: HarnessContext
    ) -> click.Command:
        # Renders one HarnessCommandDef into a click command. Pure: no I/O, so the whole tree
        # (and its --help) builds without touching credentials or the network.
        params: list[click.Parameter] = []
        for arg in command_def.args:
            params.append(click.Argument([arg.name.replace("-", "_")], required=arg.required))
        for opt in command_def.options:
            params.append(self._build_click_option(opt))

        def callback(**kwargs: object) -> None:
            self.dispatch(command_def, kwargs, ctx)

        callback_typed: Callable[..., None] = callback
        return click.Command(
            name=command_def.name,
            params=params,
            help=command_def.description,
            callback=callback_typed,
        )

    def _build_click_option(self, opt: OptionSpec) -> click.Option:
        # One manifest OptionSpec -> one click.Option.
        decl = [f"--{opt.name}"]
        if opt.type == "boolean":
            return click.Option(decl, is_flag=True, default=bool(opt.default), help=opt.description)
        if opt.default is not None:
            return click.Option(
                decl,
                type=self._CLICK_TYPES[opt.type],
                required=opt.required,
                default=opt.default,
                help=opt.description,
            )
        # Do NOT pass `default` when there is none: giving click an explicit default=None makes
        # it treat the option as defaulted and silently skips the `required` check.
        return click.Option(
            decl,
            type=self._CLICK_TYPES[opt.type],
            required=opt.required,
            help=opt.description,
        )
