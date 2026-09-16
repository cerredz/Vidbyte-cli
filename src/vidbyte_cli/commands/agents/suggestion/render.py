"""Renders suggestion results for human and machine consumers.

Human output prints ranked titles with categories and first actions; JSON
output emits the versioned envelope. Only results reach stdout, because the
application layer routes diagnostics to stderr before this module ever runs.
"""

from __future__ import annotations

from ....lib.output import OutputDocument
from ....lib.runtime.context import ApplicationContext as Context
from ....types.suggestions import (
    SUGGESTIONS_HANDOFF_KIND,
    SUGGESTIONS_RESULT_KIND,
    SuggestionHandoff,
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
        # Presentation delegates to the same deterministic structured value exposed to callers.
        return result.to_string()
