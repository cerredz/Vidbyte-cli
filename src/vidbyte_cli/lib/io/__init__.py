"""FILE: src/vidbyte_cli/lib/io/__init__.py

PURPOSE: Publishes the stable process-I/O contracts used by the CLI runtime. Importers use
this boundary instead of depending on implementation filenames. Formatting and terminal
capability policy remain outside this module.

ROLE IN CODEBASE: lib/runtime imports IOStreams from here; streams.py supplies the exported
implementation. This file owns only package exports and has no process side effects.

ARCHITECTURE NOTE: The package facade keeps runtime composition dependent on a small public
contract, following docs/design/python-cli-research-harness-program.md.

FUNCTION INVENTORY (reviewed 2026-07-26):
- IOStreams: invocation-owned stdin, stdout, and stderr channels.

COMMON MODIFICATION PATTERNS: Re-export a new I/O contract only after adding it to the
io/README.md file index and confirming it is useful outside its implementation module.

WHAT NOT TO DO IN THIS FILE:
1. Do not instantiate system streams at import time; lib/runtime/application.py owns that.
2. Do not add formatting functions; lib/output owns presentation.
3. Do not add command behavior; commands and feature slices own it.

KNOWN EDGE CASES: Keeping exports explicit prevents optional terminal dependencies from
loading during basic help and version commands.

RELATED DOCS:
https://github.com/cerredz/Vidbyte-cli/blob/main/docs/design/python-cli-research-harness-program.md
defines this package seam after this stack merges.

TESTS: No dedicated feature tests are added under the approved no-tests workflow.
scripts/smoke.py validates import and command startup.
"""

from .streams import IOStreams

__all__ = ["IOStreams"]
