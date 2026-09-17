"""Registers explicit accepted and rejected suggestion feedback commands.

Feedback is appended to one project's local JSON memory and never inferred from silence or
implementation. This module owns Click parsing and result rendering; persistence remains in
the suggestion project store.
"""

from __future__ import annotations

import click
from pydantic import ValidationError

from ...lib.errors.failures import (
    StateWriteFailed,
    SuggestionFeedbackInvalid,
    SuggestionProjectNotFound,
    SuggestionProjectStateUnreadable,
    SuggestionProjectWriteFailed,
)
from ...lib.output import OutputDocument
from ...lib.runtime.context import ApplicationContext
from ...lib.runtime.context import ApplicationContext as Context
from ...services.suggestions.project_store import (
    ProjectNotFoundError,
    ProjectStateError,
    SuggestionProjectStore,
)
from ...types.suggestions import FeedbackType

_GROUP_HELP = (
    "Record clear user reactions to suggestions for a local project. The group accepts an "
    "explicitly accepted or rejected suggestion and appends it to that project's memory. "
    "It never calls a model and it never treats silence, implementation, or ambiguity as a "
    "reaction. Use the optional reason to preserve why the user made the choice."
)

_ACCEPT_HELP = (
    "Record a suggestion that the user explicitly accepted for a project. The suggestion "
    "text is appended with its optional user-supplied reason, so later runs can recognize "
    "which directions or qualities were useful. Call this only when the user's acceptance is "
    "clear; do not infer it from silence or from the user implementing unrelated work. The "
    "command is local, deterministic, and does not execute the suggestion."
)

_REJECT_HELP = (
    "Record a suggestion that the user explicitly rejected for a project. The suggestion "
    "text and optional reason are appended so later runs can avoid repeating the same "
    "unwanted direction. Call this only when the user's rejection is clear; do not infer it "
    "from silence, a topic change, or the absence of implementation. The command is local, "
    "deterministic, and does not remove earlier feedback."
)

_PROJECT_HELP = (
    "The existing project key that should receive this feedback. The key must come from a "
    "previously created local project and is not created automatically. It selects exactly "
    "one per-project JSON memory file for the append. An unknown key fails before any file is "
    "changed, so run project list to repair the invocation."
)

_SUGGESTION_HELP = (
    "The suggestion the user accepted or rejected. Preserve enough of the original wording "
    "for a future generator to recognize the direction without needing the old run. The "
    "value is stored as preference history and is never treated as an instruction to execute. "
    "It must be nonempty and may be supplied independently of any saved result file."
)

_REASON_HELP = (
    "The user's explanation for the reaction, when one was provided. Preserve the user's "
    "meaning rather than inventing a summary or adding a rationale. The option is optional "
    "because a clear like or dislike can still be recorded without an explanation. It is "
    "stored with the suggestion and used as project context on later runs."
)


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
        command_name = "accept" if self._feedback_type is FeedbackType.ACCEPTED else "reject"
        command_help = (
            _ACCEPT_HELP if self._feedback_type is FeedbackType.ACCEPTED else _REJECT_HELP
        )

        @parent.command(name=command_name, help=command_help)
        @click.option("--project", required=True, help=_PROJECT_HELP)
        @click.option("--suggestion", required=True, help=_SUGGESTION_HELP)
        @click.option("--reason", default=None, help=_REASON_HELP)
        @click.pass_obj
        def _feedback(ctx: Context, project: str, suggestion: str, reason: str | None) -> None:
            # Delegates to the testable command boundary.
            self.execute(ctx, project, suggestion, reason)

    def execute(
        self, context: ApplicationContext, project: str, suggestion: str, reason: str | None
    ) -> None:
        # Rejects blank caller text before reading or writing project state.
        if not isinstance(suggestion, str) or not suggestion.strip():
            raise SuggestionFeedbackInvalid("suggestion must be nonempty")
        if len(suggestion) > 8192:
            raise SuggestionFeedbackInvalid("suggestion must be 8192 characters or fewer")
        if reason is not None and (not isinstance(reason, str) or len(reason) > 8192):
            raise SuggestionFeedbackInvalid("reason must be 8192 characters or fewer")
        try:
            record = SuggestionProjectStore(context.paths()).append_feedback(
                project, self._feedback_type, suggestion, reason
            )
        except ProjectNotFoundError as error:
            raise SuggestionProjectNotFound(project) from error
        except ProjectStateError as error:
            raise SuggestionProjectStateUnreadable("the project memory is invalid") from error
        except StateWriteFailed as error:
            raise SuggestionProjectWriteFailed(error) from error
        except (OSError, UnicodeError, ValueError, ValidationError) as error:
            raise SuggestionProjectStateUnreadable("the project memory is invalid") from error
        context.output().result(
            OutputDocument(
                kind="suggestions.feedback.recorded",
                data={"project": project, "feedback": record.model_dump(mode="json")},
            ),
            f"Recorded {record.type.value} feedback for '{project}'.",
        )
