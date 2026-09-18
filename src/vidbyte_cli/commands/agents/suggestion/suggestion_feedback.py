"""Registers explicit accepted and rejected suggestion feedback commands.

Feedback is appended to one project's local JSON memory and never inferred from silence or
implementation. This module owns Click parsing and result rendering; validation and
persistence belong to `SuggestionFeedbackInput` and `SuggestionProject`.
"""

from __future__ import annotations

import click

from ....lib.errors.failures import SuggestionFeedbackInvalid, SuggestionProjectInvalid
from ....lib.output import OutputDocument
from ....lib.runtime.context import ApplicationContext as Context
from ....services.suggestions.project import (
    SuggestionFeedbackInput,
    SuggestionProject,
    SuggestionProjectKey,
)
from ....types.suggestions import FeedbackType
from .prompts.library import SuggestionHelpLibrary

_HELP = SuggestionHelpLibrary()
_GROUP_HELP = _HELP.load("feedback_group")
_ACCEPT_HELP = _HELP.load("feedback_accept")
_REJECT_HELP = _HELP.load("feedback_reject")
_PROJECT_HELP = _HELP.load("feedback_project")
_SUGGESTION_HELP = _HELP.load("feedback_suggestion")
_REASON_HELP = _HELP.load("feedback_reason")


class SuggestionFeedbackGroup:
    """Attaches accepted and rejected feedback verbs below the suggest group."""

    def register(self, parent: click.Group) -> None:
        # Keeps both dispositions on one command family with one persistence implementation.
        feedback = click.Group(name="feedback", help=_GROUP_HELP)
        SuggestionFeedbackCommand(FeedbackType.ACCEPTED).register(feedback)
        SuggestionFeedbackCommand(FeedbackType.REJECTED).register(feedback)
        parent.add_command(feedback)


class SuggestionFeedbackCommand:
    """Validates and appends one explicit accepted or rejected reaction."""

    def __init__(self, feedback_type: FeedbackType) -> None:
        # The disposition is fixed by registration so callers cannot pass arbitrary types.
        self._feedback_type = feedback_type

    def register(self, parent: click.Group) -> None:
        # Adds one verb whose name and help match its fixed disposition.
        accepted = self._feedback_type is FeedbackType.ACCEPTED

        @parent.command(
            name="accept" if accepted else "reject",
            help=_ACCEPT_HELP if accepted else _REJECT_HELP,
        )
        @click.option("--project", required=True, help=_PROJECT_HELP)
        @click.option("--suggestion", required=True, help=_SUGGESTION_HELP)
        @click.option("--reason", default=None, help=_REASON_HELP)
        @click.pass_obj
        def _feedback(ctx: Context, project: str, suggestion: str, reason: str | None) -> None:
            self.execute(ctx, project, suggestion, reason)

    def execute(self, context: Context, project: str, suggestion: str, reason: str | None) -> None:
        # A malformed key and malformed feedback name different options, so they fail apart.
        try:
            key = SuggestionProjectKey(project)
        except (TypeError, ValueError) as error:
            raise SuggestionProjectInvalid(str(error)) from error
        try:
            request = SuggestionFeedbackInput(key, self._feedback_type, suggestion, reason)
        except (TypeError, ValueError) as error:
            raise SuggestionFeedbackInvalid(str(error)) from error
        record = SuggestionProject(context.paths()).record_feedback(request)
        context.output().result(
            OutputDocument(
                kind="suggestions.feedback.recorded",
                data={"project": key.value, "feedback": record.model_dump(mode="json")},
            ),
            f"Recorded {record.type.value} feedback for '{key.value}'.",
        )


__all__ = ["SuggestionFeedbackGroup"]
