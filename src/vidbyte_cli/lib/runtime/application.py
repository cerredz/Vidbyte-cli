"""One CLI invocation: read root policy, build the command tree, dispatch.

This is the composition root. `run()` returns a status instead of calling `sys.exit`, so the
application can be embedded in another Python process, and every failure — Click's included —
leaves through the single ErrorHandler boundary rather than being printed here.

Root options are inspected before Click parses, because `--format` and `--debug` decide how a
parse failure is rendered and Click's own errors leave through that same boundary. They are
overrides, not the final answer: the resolver layers them over the environment and the
selected profile. An invocation that exits before running a command skips that resolution
entirely, so `--help` never reads a file.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from contextlib import redirect_stderr, redirect_stdout

import click

from ...commands import register_all_commands
from ..config import ConfigOverrides
from ..errors.failures import ConflictingOutputFormat
from ..io import IOStreams
from ..output.formats import ColorMode, OutputFormat
from .context import ApplicationContext, InvocationOptions
from .options import RootOptionInspector, RootOptionValues
from .version import current_version


class CliApplication:
    """Runs one command-line invocation and returns its process status."""

    def __init__(self, context: ApplicationContext | None = None) -> None:
        # A caller may inject a complete graph; otherwise bind the process streams once.
        self._context = context or ApplicationContext(IOStreams.system())
        self._streams = self._context.streams

    def run(self, argv: Sequence[str] | None = None) -> int:
        # Build, configure, and dispatch inside one trap so every exit path is a return code.
        arguments = list(sys.argv if argv is None else argv)
        try:
            program = self._build_program()
            register_all_commands(program)
            self._preconfigure(arguments)
            return self._invoke(program, arguments)
        except (Exception, KeyboardInterrupt) as error:  # noqa: BLE001 - the process boundary.
            return self._context.error_handler().handle(error)
        finally:
            # After the handler has rendered, so a failure still reports before teardown.
            self._context.close()

    def _build_program(self) -> click.Group:
        # The root group; its callback publishes the invocation context to every command.
        application_context = self._context

        @click.group(
            name="vidbyte-cli",
            help="Vidbyte CLI: authenticate and run Vidbyte research threads",
        )
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
            # No Click default: an unset flag must stay distinguishable from an explicit
            # `--color auto`, or the option would outrank the stored profile every time.
            default=None,
        )
        @click.option("--debug", is_flag=True, help="Show redacted internal stack frames.")
        @click.pass_context
        def program(click_context: click.Context, /, **values: object) -> None:
            # Rebind root policy from Click, the authoritative parser, then publish context.
            self._configure_context(RootOptionValues.from_click(values))
            click_context.obj = application_context

        return program

    def _preconfigure(self, argv: Sequence[str]) -> None:
        # Invalid root syntax stays service-free and is later rendered by Click.
        inspection = RootOptionInspector(argv).inspect()
        if inspection is None:
            return
        # Help and version exit before any command, and resolving configuration would read
        # the filesystem on their behalf.
        if not inspection.exits_before_command:
            self._configure_context(inspection.values)

    def _invoke(self, program: click.Group, argv: Sequence[str]) -> int:
        # Click writes to the process streams, so bind them to the invocation-owned channels.
        # standalone_mode=False hands click's exceptions back to the trap in run().
        with redirect_stdout(self._streams.stdout), redirect_stderr(self._streams.stderr):
            program.main(args=list(argv[1:]), prog_name="vidbyte-cli", standalone_mode=False)
        return 0

    def _configure_context(self, values: RootOptionValues) -> None:
        # Root options are the highest-precedence layer, not the whole answer: the resolver
        # fills every unset field from the environment, the profile, then built-ins.
        resolved = self._context.config_resolver().resolve(
            ConfigOverrides(
                profile=values.profile,
                output_format=self._resolve_output_format(values.output_format, values.as_json),
                color=ColorMode(values.color) if values.color is not None else None,
            )
        )
        self._context.configure(
            InvocationOptions(
                output_format=resolved.output_format,
                profile=resolved.profile,
                api_url=resolved.api_url,
                request_timeout_seconds=resolved.request_timeout_seconds,
                no_input=values.no_input,
                color=resolved.color,
                debug=values.debug,
            ),
            resolved,
        )

    def _resolve_output_format(self, value: str | None, as_json: bool) -> OutputFormat | None:
        # --json is an alias, not an independent mode; duplicate JSON intent is harmless.
        if as_json and value not in {None, OutputFormat.JSON.value}:
            raise ConflictingOutputFormat()
        if as_json:
            return OutputFormat.JSON
        return OutputFormat(value) if value is not None else None
