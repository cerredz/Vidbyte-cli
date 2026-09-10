"""Renders suggestion results for human and machine consumers.

Human output prints ranked titles with categories and first actions; JSON
output emits the versioned envelope. Only results reach stdout, because the
application layer routes diagnostics to stderr before this module ever runs.
"""

from __future__ import annotations

from ...lib.output import OutputDocument
from ...lib.runtime.context import ApplicationContext as Context
from ...types.suggestions import (
    SUGGESTIONS_HANDOFF_KIND,
    SUGGESTIONS_RESULT_KIND,
    SuggestionHandoff,
    SuggestionIdea,
    SuggestionResult,
)


class SuggestionRenderer:
    """Formats batches and handoffs without touching provider or filesystem state."""

    def __init__(self) -> None:
        # Stateless; formatting depends only on the documents passed per call.
        pass

    def render_result(self, context: Context, result: SuggestionResult) -> None:
        # Emits the envelope for machines and a ranked list for humans.
        context.output().result(
            OutputDocument(kind=SUGGESTIONS_RESULT_KIND, data=result.model_dump(mode="json")),
            self._human_result(result),
        )

    def render_handoff(self, context: Context, handoff: SuggestionHandoff) -> None:
        # Emits the handoff envelope plus its copyable execution prompt.
        context.output().result(
            OutputDocument(kind=SUGGESTIONS_HANDOFF_KIND, data=handoff.model_dump(mode="json")),
            handoff.execution_prompt,
        )

    def _human_result(self, result: SuggestionResult) -> str:
        # One block per idea so a person can scan ranks without parsing JSON.
        if not result.ideas:
            return f"No suggestions for: {result.goal}"
        blocks: list[str] = []
        for idea in result.ideas:
            blocks.append(self._human_idea(idea))
        header = self._human_header(result)
        return header + "\n\n" + "\n\n".join(blocks)

    def _human_idea(self, idea: SuggestionIdea) -> str:
        # One ranked line plus its first action on a second line.
        lead = f"#{idea.rank} {idea.id} [{idea.primary_category}]"
        return f"{lead} {idea.title}\n  First action: {idea.first_action}"

    def _human_header(self, result: SuggestionResult) -> str:
        # Counts plus goal plus status so shortfalls read plainly.
        counts = f"{result.returned_count}/{result.requested_count}"
        return f"{counts} ideas for: {result.goal} [{result.status.value}]"
