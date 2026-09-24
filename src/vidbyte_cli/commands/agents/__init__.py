"""Registers the agents command family for locally run specialized agents.

The `agents` group is distinct from `runtime` primitives because its commands
are free, local, and return suggestions without executing them. This module
owns the group and its `suggest` subgroup so the three verbs share one home.
"""

from __future__ import annotations

import click


class AgentsGroup:
    """Attaches the suggestion agent and the rules agent."""

    def register(self, parent: click.Group) -> None:
        # Builds nested groups here so commands/__init__.py stays declarative.
        from .rules import RulesAgentGroup
        from .suggestion import SuggestionAgentGroup

        agents = click.Group(name="agents", help=_AGENTS_HELP)
        SuggestionAgentGroup().register(agents)
        RulesAgentGroup().register(agents)
        parent.add_command(agents)


_AGENTS_HELP = (
    "Vidbyte specialized agents focus on a defined reasoning role and produce a structured "
    "work product for a person or another agent. Each agent interprets the supplied goal "
    "and context through the perspective needed for its specialty. The resulting analysis "
    "makes its conclusions, supporting context, and recommended follow-up explicit. Choose "
    "a specialized agent when a general response would leave the next decision underspecified."
)
