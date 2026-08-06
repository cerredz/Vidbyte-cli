"""FILE: src/vidbyte_cli/lib/runtime/application.py

PURPOSE: Orchestrates one complete CLI invocation: parse global policy, build the static
Click tree, lazily attach one requested harness namespace, dispatch arguments, and delegate
all failures to the central handler.

ROLE IN CODEBASE: cli.py creates CliApplication and returns its status. commands/__init__.py
registers the static tree; harnesses/__init__.py, HarnessCatalog, and HarnessRegistry provide
the optional dynamic subtree. ApplicationContext supplies invocation-owned dependencies,
IOStreams receives final diagnostics, and current_version() supplies Click's version.

ARCHITECTURE NOTE: This is the synchronous composition root described in
docs/design/python-cli-research-harness-program.md. It preserves the accepted two-pass
harness algorithm while removing sys.exit and process-global I/O from reusable code.

FUNCTION INVENTORY (reviewed 2026-07-26):
- ArgumentInspector.harness_namespace(argv) -> str | None: identifies a dynamic namespace.
- CliApplication(context) -> CliApplication: composes an invocation runner.
- CliApplication.run(argv) -> int: executes the invocation and returns a process code.
- CliApplication._configure_context(...) -> None: binds validated root option policy.

COMMON MODIFICATION PATTERNS: Add global options in _build_program(), add reusable services
to ApplicationContext, and extend failure policy through ErrorHandler. Command-specific
options and use cases must stay in their owning command or feature slice.

WHAT NOT TO DO IN THIS FILE:
1. Do not implement command business logic; commands and features own that behavior.
2. Do not call sys.exit; cli.py and __main__.py own the process exit boundary.
3. Do not create API clients during command-tree construction.
4. Do not print command results directly; lib/output owns presentation policy.
5. Do not load every dynamic harness; attach only the namespace identified from argv.

KNOWN EDGE CASES: Global flags can appear before the harness group, generic harness verbs
must not be interpreted as namespaces, and Click exceptions need their native exit codes.
Unexpected failures deliberately return EX_SOFTWARE without exposing a traceback.

COMMON ERRORS RAISED BY THIS FILE: Command, dynamic-registration, and Click parsing failures
are allowed to reach the one ErrorHandler boundary.

RELATED DOCS:
- https://github.com/cerredz/Vidbyte-cli/blob/main/docs/design/python-cli-research-harness-program.md
  defines the composition root after this stack merges.
- https://github.com/cerredz/Vidbyte-cli/blob/main/docs/architecture.md explains
  static/dynamic harness registration.

TESTS: No dedicated feature tests are added under the approved no-tests workflow.
scripts/smoke.py exercises the static tree, version, and one static harness namespace.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from contextlib import redirect_stderr, redirect_stdout

import click

from ...commands import register_all_commands
from ...harnesses import static_harness_map
from ..config import ConfigOverrides
from ..errors.cli_error import usage_error
from ..harness.catalog import HarnessCatalog
from ..harness.registry import HarnessRegistry
from ..io import IOStreams
from ..output.formats import ColorMode, OutputFormat
from .context import ApplicationContext, InvocationOptions
from .options import RootInspection, RootOptionInspector, RootOptionValues
from .version import current_version

_GENERIC_HARNESS_VERBS = frozenset({"run", "status", "list", "catalog"})


class ArgumentInspector:
    """Extract routing facts before Click parses the complete command tree."""

    def harness_namespace(self, arguments: Sequence[str]) -> str | None:
        # Root option values cannot be mistaken for the actual top-level harness command.
        if not arguments or arguments[0] != "harness":
            return None
        remaining = arguments[1:]
        return self._first_namespace(remaining)

    def _first_namespace(self, arguments: Sequence[str]) -> str | None:
        # Harness-group options cannot donate their values as dynamic namespace candidates.
        if not arguments or arguments[0].startswith("-"):
            return None
        namespace = arguments[0]
        return None if namespace in _GENERIC_HARNESS_VERBS else namespace


class CliApplication:
    """Testable synchronous runner for one command-line invocation."""

    def __init__(self, context: ApplicationContext | None = None) -> None:
        # The caller may inject one complete graph; otherwise bind system streams once.
        self._context = context or ApplicationContext(IOStreams.system())
        self._streams = self._context.streams
        self._inspector = ArgumentInspector()
        self._root_inspector = RootOptionInspector()

    def run(self, argv: Sequence[str] | None = None) -> int:
        # Orchestrate tree construction, lazy attachment, and Click dispatch in one trap.
        arguments = list(sys.argv if argv is None else argv)
        try:
            program = self._build_program()
            harness_group = register_all_commands(program, self._context.environment)
            inspection = self._preconfigure(arguments)
            if (
                inspection is not None
                and inspection.attach_allowed
                and not inspection.exits_before_command
            ):
                self._attach_harness(inspection.command_arguments, harness_group)
            return self._invoke(program, arguments)
        except KeyboardInterrupt as error:
            return self._context.error_handler().handle(error)
        except Exception as error:  # noqa: BLE001 - the process boundary contains all failures.
            return self._context.error_handler().handle(error)
        finally:
            self._context.close()

    def _build_program(self) -> click.Group:
        # Root callbacks receive ApplicationContext without constructing optional services.
        application_context = self._context

        @click.group(name="vidbyte-cli", help="Universal Vidbyte CLI: auth, harness runs, config")
        @click.version_option(current_version(), "--version")
        @click.option(
            "--format",
            "output_format",
            type=click.Choice([item.value for item in OutputFormat], case_sensitive=False),
        )
        @click.option("--json", "as_json", is_flag=True, help="Alias for --format json.")
        @click.option("--profile", type=str, help="Use a named configuration profile.")
        @click.option("--no-input", is_flag=True, help="Never prompt for interactive input.")
        @click.option(
            "--color",
            type=click.Choice([item.value for item in ColorMode], case_sensitive=False),
            default=None,
        )
        @click.option("--debug", is_flag=True, help="Show redacted internal stack frames.")
        @click.pass_context
        def program(click_context: click.Context, /, **values: object) -> None:
            # Bind root policy only after Click validates all primitive option values.
            self._configure_context(RootOptionValues.from_click(values))
            click_context.obj = application_context

        return program

    def _attach_harness(self, arguments: Sequence[str], harness_group: click.Group) -> None:
        # Load at most one requested harness and keep every unrelated command network-free.
        namespace = self._inspector.harness_namespace(arguments)
        if namespace is None:
            return
        harness_context = self._context.harness_context()
        registry = HarnessRegistry(static_harness_map(), HarnessCatalog(harness_context))
        registry.attach(harness_group, namespace, harness_context)

    def _preconfigure(self, argv: Sequence[str]) -> RootInspection | None:
        # Invalid root syntax stays service-free and is later rendered by Click.
        inspection = self._root_inspector.inspect(argv)
        if inspection is None:
            return None
        if not inspection.exits_before_command:
            self._configure_context(inspection.values)
        return inspection

    def _invoke(self, program: click.Group, argv: Sequence[str]) -> int:
        # Click has process-default streams, so bind them to the invocation-owned channels.
        with redirect_stdout(self._streams.stdout), redirect_stderr(self._streams.stderr):
            program.main(args=list(argv[1:]), prog_name="vidbyte-cli", standalone_mode=False)
        return self._context.exit_code()

    def _configure_context(self, values: RootOptionValues) -> None:
        # --json is a compatibility alias, not an independent output mode.
        explicit_format = self._resolve_output_format(values.output_format, values.as_json)
        explicit_color = ColorMode(values.color) if values.color is not None else None
        resolved = self._context.config_resolver().resolve(
            ConfigOverrides(
                profile=values.profile,
                output_format=explicit_format,
                color=explicit_color,
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

    def _resolve_output_format(
        self,
        value: str | None,
        as_json: bool,
    ) -> OutputFormat | None:
        # Reject only genuinely conflicting values; duplicate JSON intent is harmless.
        if as_json and value not in {None, OutputFormat.JSON.value}:
            raise usage_error(
                "--json conflicts with the selected --format value.",
                "Remove --json or use --format json.",
            )
        if as_json:
            return OutputFormat.JSON
        return OutputFormat(value) if value is not None else None
