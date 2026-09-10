"""Registers the agents command family for locally run specialized agents.

The `agents` group is distinct from `runtime` primitives because its commands
are free, local, and return suggestions without executing them. This module
owns the group and its `suggest` subgroup so the three verbs share one home.
"""

from __future__ import annotations

import click


class AgentsGroup:
    """Attaches agents/suggest with run, categories, and handoff verbs."""

    def register(self, parent: click.Group) -> None:
        # Builds nested groups here so commands/__init__.py stays declarative.
        from .suggest import SuggestRunCommand
        from .suggestion_categories import SuggestionCategoriesCommand
        from .suggestion_handoff import SuggestionHandoffCommand

        agents = click.Group(name="agents", help=_AGENTS_HELP)
        suggest = click.Group(name="suggest", help=_SUGGEST_HELP)
        SuggestRunCommand().register(suggest)
        SuggestionCategoriesCommand().register(suggest)
        SuggestionHandoffCommand().register(suggest)
        agents.add_command(suggest)
        parent.add_command(agents)


_AGENTS_HELP = (
    "Run Vidbyte specialized agents locally on this machine. These commands orchestrate "
    "model-assisted workflows inside the CLI process and return structured results for "
    "another agent or a person to act on. They never execute the work they suggest, and "
    "they never touch the research backend, so they stay free of admission and pricing. "
    "Start with the suggest subgroup when you need ranked next actions with handoffs."
)


_SUGGEST_HELP = (
    "Generate ranked next-action ideas with execution-ready handoffs for a goal. The run "
    "verb accepts a goal plus optional caller context and returns a structured batch, "
    "while categories lists the supported taxonomy and handoff extracts one packet. All "
    "three verbs share the same schema version so results flow between them safely. Use "
    "JSON output when another agent consumes the result directly."
)
