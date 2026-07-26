"""FILE: src/vidbyte_cli/lib/runtime/application.py

PURPOSE: Orchestrates one complete CLI invocation: build the static Click tree, lazily attach
one requested harness namespace, dispatch arguments, and translate failures into return
codes. This file owns lifecycle and process-boundary policy; individual command behavior
and output formatting belong elsewhere.

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

COMMON MODIFICATION PATTERNS: Add global options in _build_program(), add reusable services
to ApplicationContext, and extend failure policy in the centralized exception branches.
Command-specific options and use cases must stay in their owning command or feature slice.

WHAT NOT TO DO IN THIS FILE:
1. Do not implement command business logic; commands and features own that behavior.
2. Do not call sys.exit; cli.py and __main__.py own the process exit boundary.
3. Do not create API clients during command-tree construction.
4. Do not print command results directly; lib/output owns presentation policy.
5. Do not load every dynamic harness; attach only the namespace identified from argv.

KNOWN EDGE CASES: Global flags can appear before the harness group, generic harness verbs
must not be interpreted as namespaces, and Click exceptions need their native exit codes.
Unexpected failures deliberately return EX_SOFTWARE without exposing a traceback.

COMMON ERRORS RAISED BY THIS FILE: CliError represents safe user-facing failures from
commands or dynamic registration. ClickException represents parsing/usage failures.

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

import click

from ...commands import register_all_commands
from ...harnesses import static_harness_map
from ..errors.cli_error import CliError
from ..harness.catalog import HarnessCatalog
from ..harness.registry import HarnessRegistry
from ..io import IOStreams
from .context import ApplicationContext
from .version import current_version

_GENERIC_HARNESS_VERBS = frozenset({"run", "status", "list", "catalog"})
_INTERNAL_ERROR_EXIT_CODE = 70


class ArgumentInspector:
    """Extract routing facts before Click parses the complete command tree."""

    def harness_namespace(self, argv: Sequence[str]) -> str | None:
        # Dynamic attachment is needed only for `harness <namespace>`, never generic verbs.
        arguments = list(argv[1:])
        if "harness" not in arguments:
            return None
        remaining = arguments[arguments.index("harness") + 1 :]
        return self._first_namespace(remaining)

    def _first_namespace(self, arguments: Sequence[str]) -> str | None:
        # Skip options before choosing the first positional token after the harness group.
        for token in arguments:
            if token.startswith("-"):
                continue
            if token in _GENERIC_HARNESS_VERBS:
                return None
            return token
        return None


class CliApplication:
    """Testable synchronous runner for one command-line invocation."""

    def __init__(self, context: ApplicationContext | None = None) -> None:
        # The caller may inject one complete graph; otherwise bind system streams once.
        self._context = context or ApplicationContext(IOStreams.system())
        self._streams = self._context.streams
        self._inspector = ArgumentInspector()

    def run(self, argv: Sequence[str] | None = None) -> int:
        # Orchestrate tree construction, lazy attachment, and Click dispatch in one trap.
        arguments = list(sys.argv if argv is None else argv)
        try:
            program = self._build_program()
            harness_group = register_all_commands(program)
            self._attach_harness(arguments, harness_group)
            return self._invoke(program, arguments)
        except CliError as error:
            return self._render_cli_error(error)
        except click.ClickException as error:
            return self._render_click_error(error)
        except click.exceptions.Abort:
            self._streams.write_error("Aborted.")
            return 1
        except Exception:  # noqa: BLE001 - the process boundary must contain internal bugs.
            self._streams.write_error("Unexpected internal error.")
            return _INTERNAL_ERROR_EXIT_CODE

    def _build_program(self) -> click.Group:
        # Root callbacks receive ApplicationContext without constructing optional services.
        application_context = self._context

        @click.group(name="vidbyte-cli", help="Universal Vidbyte CLI: auth, harness runs, config")
        @click.version_option(current_version(), "--version")
        @click.option("--json", "as_json", is_flag=True, help="machine-readable output (reserved)")
        @click.pass_context
        def program(click_context: click.Context, as_json: bool) -> None:
            # JSON policy lands in PR 2; the invocation context is available immediately.
            del as_json
            click_context.obj = application_context

        return program

    def _attach_harness(self, argv: Sequence[str], harness_group: click.Group) -> None:
        # Load at most one requested harness and keep every unrelated command network-free.
        namespace = self._inspector.harness_namespace(argv)
        if namespace is None:
            return
        harness_context = self._context.harness_context()
        registry = HarnessRegistry(static_harness_map(), HarnessCatalog(harness_context))
        registry.attach(harness_group, namespace, harness_context)

    def _invoke(self, program: click.Group, argv: Sequence[str]) -> int:
        # standalone_mode=False lets the application map every failure to a return code.
        program.main(args=list(argv[1:]), prog_name="vidbyte-cli", standalone_mode=False)
        return 0

    def _render_cli_error(self, error: CliError) -> int:
        # CliError is explicitly safe for users; richer structured rendering arrives in PR 2.
        self._streams.write_error(str(error))
        return error.exit_code

    def _render_click_error(self, error: click.ClickException) -> int:
        # Preserve Click's familiar usage rendering while directing it to injected stderr.
        error.show(file=self._streams.stderr)
        return error.exit_code
