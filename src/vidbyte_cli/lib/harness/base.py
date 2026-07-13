"""BaseHarness: the boilerplate every harness shares, written once.

A harness author extends this and implements `commands()`. The base owns the two things
that are identical for every harness: turning command definitions into a click command
tree (`register`), and the submit -> (await) -> present -> map-errors lifecycle every
command runs (`dispatch`). Authors never touch click or httpx directly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable

import click

from ...types.api import HarnessRepoRef, HarnessRun, HarnessRunCreateRequest
from ...types.manifest import OptionType
from ..errors.cli_error import CliError, not_implemented
from .context import HarnessContext
from .errors import map_harness_error
from .types import HarnessCommandDef


class BaseHarness(ABC):
    # Every harness declares a namespace and a set of commands; the base does the rest.
    name: str
    description: str

    @abstractmethod
    def commands(self, ctx: HarnessContext) -> list[HarnessCommandDef]:
        # The command surface of this harness (static list, or mapped from a manifest).
        raise NotImplementedError

    def register(self, parent: click.Group, ctx: HarnessContext) -> None:
        # Builds `vidbyte-cli harness <name> <command> ...` under the given parent group.
        group = click.Group(name=self.name, help=self.description)
        for command_def in self.commands(ctx):
            group.add_command(_build_click_command(self, command_def, ctx))
        parent.add_command(group)

    def dispatch(
        self, command_def: HarnessCommandDef, params: dict[str, object], ctx: HarnessContext
    ) -> None:
        # The uniform lifecycle every harness command follows. This is the shared "command
        # structure" made literal: guard -> translate -> submit -> (await) -> present.
        ctx.require_api_key()  # fail fast before any repo/network work
        repo = ctx.repo.as_repo_ref()
        request = self._to_invocation(command_def, params, repo)
        endpoints = ctx.harness_endpoints()
        try:
            submitted = endpoints.create_run(request)
            result = _wait_for_run(submitted) if command_def.mode == "await" else submitted
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
        self, command_def: HarnessCommandDef, params: dict[str, object], repo: HarnessRepoRef
    ) -> HarnessRunCreateRequest:
        # Uses the command's own translation hook, or the pass-through default.
        if command_def.to_invocation is not None:
            return command_def.to_invocation(params, repo)
        return _default_invocation(self.name, command_def, params, repo)


def _default_invocation(
    harness_name: str,
    command_def: HarnessCommandDef,
    params: dict[str, object],
    repo: HarnessRepoRef,
) -> HarnessRunCreateRequest:
    # Splits click's flat kwargs back into declared args vs options by name. click lowercases
    # and underscores param names, so look each spec up by its normalized key.
    def pick(name: str) -> object:
        return params.get(name.replace("-", "_"))

    return HarnessRunCreateRequest(
        harness=harness_name,
        command=command_def.name,
        args={arg.name: pick(arg.name) for arg in command_def.args},
        options={opt.name: pick(opt.name) for opt in command_def.options},
        repo=repo,
    )


def _wait_for_run(run: HarnessRun) -> HarnessRun:
    # Polls the run to a terminal state with backoff; shared by every `await`-mode command.
    raise not_implemented("harness run waiting")


_CLICK_TYPES: dict[OptionType, click.ParamType] = {
    "string": click.STRING,
    "number": click.FLOAT,
    "path": click.Path(),
}


def _build_click_command(
    harness: BaseHarness, command_def: HarnessCommandDef, ctx: HarnessContext
) -> click.Command:
    # Renders one HarnessCommandDef into a click command. Pure: no I/O, so the whole tree
    # (and its --help) builds without touching credentials or the network.
    params: list[click.Parameter] = []
    for arg in command_def.args:
        params.append(click.Argument([arg.name.replace("-", "_")], required=arg.required))
    for opt in command_def.options:
        decl = [f"--{opt.name}"]
        if opt.type == "boolean":
            params.append(
                click.Option(decl, is_flag=True, default=bool(opt.default), help=opt.description)
            )
        elif opt.default is not None:
            params.append(
                click.Option(
                    decl,
                    type=_CLICK_TYPES[opt.type],
                    required=opt.required,
                    default=opt.default,
                    help=opt.description,
                )
            )
        else:
            # Do NOT pass `default` when there is none: giving click an explicit default=None
            # makes it treat the option as defaulted and silently skips the `required` check.
            params.append(
                click.Option(
                    decl,
                    type=_CLICK_TYPES[opt.type],
                    required=opt.required,
                    help=opt.description,
                )
            )

    def callback(**kwargs: object) -> None:
        harness.dispatch(command_def, kwargs, ctx)

    callback_typed: Callable[..., None] = callback
    return click.Command(
        name=command_def.name,
        params=params,
        help=command_def.description,
        callback=callback_typed,
    )
