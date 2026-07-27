"""One CLI invocation: build the tree, attach at most one harness, dispatch, map failures.

This is the composition root. It replaces the old module-level `main()` that called
`sys.exit`: `run()` returns a status so the application can be embedded in another Python
process. Everything else — command behavior, formatting, transport — lives elsewhere.

The two-pass argv inspection is unchanged from the accepted design: click builds its tree
synchronously but a manifest arrives over the network, so pass 1 registers the static
surface and pass 2 attaches only the harness namespace argv actually names.
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

# Static verbs under `harness`; a token matching one of these is not a harness namespace, so
# we must never try to load a manifest for it.
_GENERIC_HARNESS_VERBS = frozenset({"run", "status", "list", "catalog"})
_INTERNAL_ERROR_EXIT_CODE = 70


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
            self._attach_harness(arguments, register_all_commands(program))
            # standalone_mode=False hands click's exceptions back to the trap below.
            program.main(args=arguments[1:], prog_name="vidbyte-cli", standalone_mode=False)
            return 0
        except CliError as error:
            # Already classified as user-safe; richer structured rendering lands in PR 2.
            self._streams.write_error(str(error))
            return error.exit_code
        except click.ClickException as error:
            # Keep click's familiar usage rendering, but route it to the injected stderr.
            error.show(file=self._streams.stderr)
            return error.exit_code
        except click.exceptions.Abort:
            self._streams.write_error("Aborted.")
            return 1
        except Exception:  # noqa: BLE001 - the process boundary must contain internal bugs.
            self._streams.write_error("Unexpected internal error.")
            return _INTERNAL_ERROR_EXIT_CODE

    def _build_program(self) -> click.Group:
        # The root group; its callback publishes the invocation context to every command.
        application_context = self._context

        @click.group(name="vidbyte-cli", help="Universal Vidbyte CLI: auth, harness runs, config")
        @click.version_option(current_version(), "--version")
        @click.option("--json", "as_json", is_flag=True, help="machine-readable output (reserved)")
        @click.pass_context
        def program(click_context: click.Context, as_json: bool) -> None:
            del as_json  # Output-format policy lands in PR 2.
            click_context.obj = application_context

        return program

    def _attach_harness(self, argv: Sequence[str], harness_group: click.Group) -> None:
        # Load at most the one requested harness, keeping every other command network-free.
        namespace = self._harness_namespace(argv)
        if namespace is None:
            return
        ctx = self._context.harness_context()
        HarnessRegistry(static_harness_map(), HarnessCatalog(ctx)).attach(
            harness_group, namespace, ctx
        )

    def _harness_namespace(self, argv: Sequence[str]) -> str | None:
        # `harness <namespace> ...` needs a dynamic subtree; global flags and generic verbs
        # do not. Skip options, then judge the first positional token after `harness`.
        arguments = list(argv[1:])
        if "harness" not in arguments:
            return None
        for token in arguments[arguments.index("harness") + 1 :]:
            if token.startswith("-"):
                continue
            return None if token in _GENERIC_HARNESS_VERBS else token
        return None
