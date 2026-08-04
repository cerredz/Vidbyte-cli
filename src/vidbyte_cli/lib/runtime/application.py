"""One CLI invocation: read root policy, build the tree, attach one harness, dispatch.

This is the composition root. `run()` returns a status instead of calling `sys.exit`, so the
application can be embedded in another Python process, and every failure — Click's included
— leaves through the single ErrorHandler boundary rather than being printed here.

The two-pass argv inspection is unchanged from the accepted design: click builds its tree
synchronously but a manifest arrives over the network, so pass 1 registers the static
surface and pass 2 attaches only the harness namespace argv actually names. Root options are
read before pass 2 so help, version, and invalid syntax never construct a harness context.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from contextlib import redirect_stderr, redirect_stdout

import click

from ...commands import register_all_commands
from ...harnesses import static_harness_map
from ..errors.failures import ConflictingOutputFormat
from ..harness.catalog import HarnessCatalog
from ..harness.registry import HarnessRegistry
from ..io import IOStreams
from ..output.formats import ColorMode, OutputFormat
from .context import ApplicationContext, InvocationOptions
from .options import RootInspection, RootOptionInspector, RootOptionValues
from .version import current_version

# Static verbs under `harness`; a token matching one of these is not a harness namespace, so
# we must never try to load a manifest for it.
_GENERIC_HARNESS_VERBS = frozenset({"run", "status", "list", "catalog"})


class CliApplication:
    """Runs one command-line invocation and returns its process status."""

    def __init__(self, context: ApplicationContext | None = None) -> None:
        # A caller may inject a complete graph; otherwise bind the process streams once.
        self._context = context or ApplicationContext(IOStreams.system())
        self._streams = self._context.streams

    def run(self, argv: Sequence[str] | None = None) -> int:
        # Build, attach, and dispatch inside one trap so every exit path is a return code.
        arguments = list(sys.argv if argv is None else argv)
        try:
            program = self._build_program()
            harness_group = register_all_commands(program)
            inspection = self._preconfigure(arguments)
            if inspection is not None and inspection.attach_allowed:
                self._attach_harness(inspection, harness_group)
            return self._invoke(program, arguments)
        except (Exception, KeyboardInterrupt) as error:  # noqa: BLE001 - the process boundary.
            return self._context.error_handler().handle(error)

    def _build_program(self) -> click.Group:
        # The root group; its callback publishes the invocation context to every command.
        application_context = self._context

        @click.group(name="vidbyte-cli", help="Universal Vidbyte CLI: auth, harness runs, config")
        @click.version_option(current_version(), "--version")
        @click.option(
            "--format",
            "output_format",
            type=click.Choice([item.value for item in OutputFormat], case_sensitive=False),
            help="Select human, one-document, streaming, or suppressed result output.",
        )
        @click.option("--json", "as_json", is_flag=True, help="Alias for --format json.")
        @click.option("--profile", type=str, help="Use a named configuration profile.")
        @click.option("--no-input", is_flag=True, help="Never prompt for interactive input.")
        @click.option(
            "--color",
            type=click.Choice([item.value for item in ColorMode], case_sensitive=False),
            default=ColorMode.AUTO.value,
            show_default=True,
        )
        @click.option("--debug", is_flag=True, help="Show redacted internal stack frames.")
        @click.pass_context
        def program(click_context: click.Context, /, **values: object) -> None:
            # Rebind root policy from Click, the authoritative parser, then publish context.
            self._configure_context(RootOptionValues.from_click(values))
            click_context.obj = application_context

        return program

    def _preconfigure(self, argv: Sequence[str]) -> RootInspection | None:
        # Invalid root syntax stays service-free and is later rendered by Click.
        inspection = RootOptionInspector(argv).inspect()
        if inspection is None:
            return None
        self._configure_context(inspection.values)
        return inspection

    def _attach_harness(self, inspection: RootInspection, harness_group: click.Group) -> None:
        # Load at most the one requested harness, keeping every other command network-free.
        namespace = self._harness_namespace(inspection)
        if namespace is None:
            return
        ctx = self._context.harness_context()
        HarnessRegistry(static_harness_map(), HarnessCatalog(ctx)).attach(
            harness_group, namespace, ctx
        )

    def _harness_namespace(self, inspection: RootInspection) -> str | None:
        # Only the command suffix is searched, so a root option value such as
        # `--profile harness` can never be mistaken for a namespace. Generic verbs and the
        # harness group's own options are not namespaces either.
        if inspection.exits_before_command:
            return None
        arguments = inspection.command_arguments
        if len(arguments) < 2 or arguments[0] != "harness":
            return None
        namespace = arguments[1]
        if namespace.startswith("-") or namespace in _GENERIC_HARNESS_VERBS:
            return None
        return namespace

    def _invoke(self, program: click.Group, argv: Sequence[str]) -> int:
        # Click writes to the process streams, so bind them to the invocation-owned channels.
        # standalone_mode=False hands click's exceptions back to the trap in run().
        with redirect_stdout(self._streams.stdout), redirect_stderr(self._streams.stderr):
            program.main(args=list(argv[1:]), prog_name="vidbyte-cli", standalone_mode=False)
        return 0

    def _configure_context(self, values: RootOptionValues) -> None:
        self._context.configure(
            InvocationOptions(
                output_format=self._resolve_output_format(values.output_format, values.as_json),
                profile=values.profile,
                no_input=values.no_input,
                color=ColorMode(values.color),
                debug=values.debug,
            )
        )

    def _resolve_output_format(self, value: str | None, as_json: bool) -> OutputFormat:
        # --json is an alias, not an independent mode; duplicate JSON intent is harmless.
        if as_json and value not in {None, OutputFormat.JSON.value}:
            raise ConflictingOutputFormat()
        if as_json:
            return OutputFormat.JSON
        return OutputFormat(value or OutputFormat.HUMAN.value)
