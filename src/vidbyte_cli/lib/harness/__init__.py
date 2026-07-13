"""The harness runtime: the protocol and machinery for integrating a harness into the CLI.

`lib/harness` is mechanism; `vidbyte_cli.harnesses` is the actual harnesses (policy).
"""

from .base import BaseHarness
from .context import HarnessContext
from .module import HarnessModule
from .types import HarnessCommandDef

__all__ = ["BaseHarness", "HarnessCommandDef", "HarnessContext", "HarnessModule"]
