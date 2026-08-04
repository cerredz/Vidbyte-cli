"""Public process-I/O contracts: streams, terminal capabilities, and prompt input."""

from .prompt import PromptInputResolver
from .streams import IOStreams
from .terminal import TerminalCapabilities, TerminalPolicy

__all__ = ["IOStreams", "PromptInputResolver", "TerminalCapabilities", "TerminalPolicy"]
