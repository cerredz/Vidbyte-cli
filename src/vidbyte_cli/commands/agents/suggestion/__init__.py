"""Registers the suggestion agent, its run-side operations, and its project memory.

The package keeps one specialized agent's command adapters together beneath
the broader agents namespace. Registration remains side-effect free so every
help path works without credentials, provider access, or model imports.
"""

from __future__ import annotations

import click


class SuggestionAgentGroup:
    """Attaches run, categories, handoff, and the project and feedback memory groups."""

    def register(self, parent: click.Group) -> None:
        from .suggest import SuggestRunCommand
        from .suggestion_categories import SuggestionCategoriesCommand
        from .suggestion_feedback import SuggestionFeedbackGroup
        from .suggestion_handoff import SuggestionHandoffCommand
        from .suggestion_projects import SuggestionProjectGroup

        suggest = click.Group(name="suggest", help=_SUGGEST_HELP)
        SuggestRunCommand().register(suggest)
        SuggestionCategoriesCommand().register(suggest)
        SuggestionHandoffCommand().register(suggest)
        SuggestionProjectGroup().register(suggest)
        SuggestionFeedbackGroup().register(suggest)
        parent.add_command(suggest)


_SUGGEST_HELP = (
    "The suggestion agent develops concrete next actions for a stated goal and ranks the "
    "ones most worth pursuing. It grounds each idea in the available context, distinguishes "
    "among different kinds of opportunity, and challenges weak or redundant candidates. "
    "Every surviving idea explains why it matters now and carries the structure another "
    "agent needs to evaluate decisions, evidence, considerations, and the proposed action."
)
