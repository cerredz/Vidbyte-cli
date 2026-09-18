"""Stop-and-message tools that let one suggestion agent end its turn with a message.

This module owns the CLI side of each tool: its model-facing text, the message
validation, and the stop signal the service waits on. It never imports the SDK;
`sdk.py` wraps each tool as an SDK `BaseTool` so Codex can call it.
"""

from __future__ import annotations

import asyncio
from typing import Literal

from ...types.suggestions import MAX_AGENT_MESSAGE_CHARS
from .prompts.library import SuggestionPrompts

MessageToolName = Literal["message_parent", "message_generator"]


class SuggestionMessageTool:
    """One agent's route to another agent: the first valid message stops its turn."""

    def __init__(self, name: MessageToolName, prompts: SuggestionPrompts) -> None:
        # One instance serves exactly one agent, so its message and signal are never shared.
        self.name = name
        self.description = prompts.message_tool(name)
        self.message_description = prompts.message_argument(name)
        self._receipt = prompts.message_receipt()
        self.message: str | None = None
        self.stopped = asyncio.Event()

    def deliver(self, message: object) -> str:
        """Record the model's message, signal the stop, and return the tool receipt."""
        if not isinstance(message, str) or not message.strip():
            raise ValueError(f"{self.name} requires a non-empty message string.")
        text = message.strip()
        if len(text) > MAX_AGENT_MESSAGE_CHARS:
            raise ValueError(
                f"{self.name} messages must be at most {MAX_AGENT_MESSAGE_CHARS} characters."
            )
        # A second call in the same turn cannot replace the message already being delivered.
        if self.message is None:
            self.message = text
            self.stopped.set()
        return self._receipt


__all__ = ["MessageToolName", "SuggestionMessageTool"]
