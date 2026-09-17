"""Role-specific stop-and-message tools for one suggestion workflow run."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ...types.suggestions import MAX_AGENT_MESSAGE_CHARS

_MAX_MESSAGES = 4


class SuggestionMessageTools:
    """Stores bounded messages and exposes one tool to each suggestion role."""

    def __init__(self) -> None:
        # State belongs to one service run and is never shared across requests.
        self._parent_messages: list[str] = []
        self._generator_messages: list[str] = []

    def generator_tools(self) -> tuple[Callable[..., Any], ...]:
        # Gives only the persistent generator a route to its external parent.
        return (self.message_parent,)

    def critic_tools(self) -> tuple[Callable[..., Any], ...]:
        # Gives only the independent critic a route to the next generator turn.
        return (self.message_generator,)

    def drain_generator_messages(self) -> tuple[str, ...]:
        # Returns critic guidance once and clears it before the next review cycle.
        messages = tuple(self._generator_messages)
        self._generator_messages.clear()
        return messages

    def parent_messages(self) -> tuple[str, ...]:
        # Preserves parent requests until the service builds its terminal result.
        return tuple(self._parent_messages)

    async def message_parent(self, message: str) -> str:
        """Stop signal: stop running right now.

        Send your message to the parent agent, then do not continue generating or invent the
        missing information.
        """
        # Records a parent request and tells the generator to stop immediately.
        self._append(message, self._parent_messages, "parent agent")
        return (
            "Stop signal received. Stop running right now. "
            f"Your message to the parent agent was recorded: {message.strip()} "
            "Do not continue generating or invent the missing information."
        )

    async def message_generator(self, message: str) -> str:
        """Stop signal: stop reviewing right now.

        Send your message to the generator agent, then do not continue critiquing or produce
        replacement candidates.
        """
        # Records critic guidance and tells the critic to stop immediately.
        self._append(message, self._generator_messages, "generator agent")
        return (
            "Stop signal received. Stop reviewing right now. "
            f"Your message to the generator agent was recorded: {message.strip()} "
            "Do not continue critiquing or produce replacement candidates."
        )

    def _append(self, message: str, target: list[str], recipient: str) -> None:
        # Validates one model-authored message before mutating run-local state.
        if not isinstance(message, str) or not message.strip():
            raise ValueError(f"Message to the {recipient} must be non-empty.")
        if len(message.strip()) > MAX_AGENT_MESSAGE_CHARS:
            raise ValueError(
                f"Message to the {recipient} must be at most {MAX_AGENT_MESSAGE_CHARS} characters."
            )
        if len(target) >= _MAX_MESSAGES:
            raise ValueError(f"Message limit for the {recipient} has been reached.")
        target.append(message.strip())


__all__ = ["SuggestionMessageTools"]
