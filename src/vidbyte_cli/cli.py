"""Program bootstrap, the central error trap, and the two-pass argv peek.

Pass 1 (synchronous): register the static command surface. Pass 2 (only when the invocation
is `harness <name> ...`): peek argv, load just that harness, and attach its subtree before
parsing. This keeps `vidbyte-cli login` off the network entirely and loads only the harness
actually invoked (resolves the index.ts:16 review comment).
"""

from __future__ import annotations

import sys

import click

from .commands import register_all_commands
from .harnesses import static_harness_map
from .lib.errors.cli_error import CliError
from .lib.harness.catalog import HarnessCatalog
from .lib.harness.context import HarnessContext
from .lib.harness.registry import HarnessRegistry
from .lib.output.logger import logger

CLI_VERSION = "0.1.0"

# Generic verbs that live statically under `harness`; a token matching one of these is NOT a
# harness namespace, so we never try to dynamically load a manifest for it.
_GENERIC_HARNESS_VERBS = {"run", "status", "list", "catalog"}


def build_program() -> click.Group:
    @click.group(name="vidbyte-cli", help="Universal Vidbyte CLI: auth, harness runs, config")
    @click.version_option(CLI_VERSION, "--version")
    @click.option("--json", "as_json", is_flag=True, help="machine-readable output (reserved)")
    def program(as_json: bool) -> None:
        pass

    return program


def peek_harness_namespace(argv: list[str]) -> str | None:
    # Cheap scan of argv for `harness <name>` where <name> is a real harness namespace (not a
    # global flag and not one of the generic verbs). Returns None otherwise.
    args = argv[1:]
    if "harness" not in args:
        return None
    rest = args[args.index("harness") + 1 :]
    for token in rest:
        if token.startswith("-"):
            continue
        return None if token in _GENERIC_HARNESS_VERBS else token
    return None


def main(argv: list[str] | None = None) -> None:
    # Builds the program, does the two-pass harness attach, dispatches, and owns process exit.
    argv = list(sys.argv if argv is None else argv)
    program = build_program()
    harness_group = register_all_commands(program)

    namespace = peek_harness_namespace(argv)
    if namespace is not None:
        ctx = HarnessContext.default()
        registry = HarnessRegistry(static_harness_map(), HarnessCatalog(ctx))
        try:
            registry.attach(harness_group, namespace, ctx)
        except CliError as error:
            logger.error(str(error))
            sys.exit(error.exit_code)

    try:
        program.main(args=argv[1:], prog_name="vidbyte-cli", standalone_mode=False)
    except CliError as error:
        # User-facing failure (including every `not_implemented` stub): render and exit.
        logger.error(str(error))
        sys.exit(error.exit_code)
    except click.ClickException as error:
        # Usage errors etc. keep click's own formatting and exit code.
        error.show()
        sys.exit(error.exit_code)
    except click.exceptions.Abort:
        logger.error("Aborted.")
        sys.exit(1)
    except Exception as error:  # noqa: BLE001 - anything else is an internal bug.
        logger.error(str(error))
        sys.exit(70)


if __name__ == "__main__":
    main()
