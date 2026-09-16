"""Builds minimal, stage-specific context windows for suggestion agents."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

from ...types.suggestions import (
    SuggestionContextItem,
    SuggestionContextPrimitive,
    SuggestionCritique,
    SuggestionIdea,
    SuggestionRequest,
)
from .categories import SuggestionCategories

_IDEA_FIELDS = (
    "id",
    "title",
    "summary",
    "primary_category",
    "secondary_categories",
    "horizon",
    "relationship",
    "readiness",
    "why_now",
    "expected_benefit",
    "evidence_refs",
    "assumptions",
    "dependencies",
    "alternative_to",
    "first_action",
    "suggested_actions",
    "decision_points",
    "considerations",
    "completion_criteria",
    "effort_estimate",
)


class SuggestionContextBridge:
    """Projects one rich request snapshot into the data each stage needs."""

    def __init__(self, categories: SuggestionCategories | None = None) -> None:
        # The registry is injected so category rendering remains deterministic and testable.
        self._categories = categories or SuggestionCategories()

    def generator(
        self, request: SuggestionRequest, category_ids: tuple[str, ...]
    ) -> SuggestionContextPrimitive:
        # Generation needs category guidance and evidence, but no candidate state.
        return self._base(request, category_ids)

    def critic(
        self,
        request: SuggestionRequest,
        category_ids: tuple[str, ...],
        ideas: tuple[SuggestionIdea, ...],
    ) -> SuggestionContextPrimitive:
        # Critique gets a compact allowlisted candidate packet for evidence and comparison.
        return self._base(request, category_ids, {"candidates": self._ideas(ideas)})

    def revision(
        self,
        request: SuggestionRequest,
        category_ids: tuple[str, ...],
        revisions: tuple[tuple[SuggestionIdea, SuggestionCritique], ...],
    ) -> SuggestionContextPrimitive:
        # Revision receives only candidates needing repair and their matching critiques.
        payload = {
            "candidates": self._ideas(tuple(idea for idea, _ in revisions)),
            "critiques": [self._critique(critique) for _, critique in revisions],
        }
        return self._base(request, category_ids, payload)

    def _base(
        self,
        request: SuggestionRequest,
        category_ids: tuple[str, ...],
        payload: dict[str, Any] | None = None,
    ) -> SuggestionContextPrimitive:
        # Rebuilds the primitive without mutating the caller-owned rich snapshot.
        return replace(
            request.context,
            items=self._items(request.context.items),
            selected_categories=self._categories.prompt_section(category_ids),
            candidate_handoffs=self._json(payload) if payload else "",
        )

    def _items(self, items: tuple[SuggestionContextItem, ...]) -> tuple[SuggestionContextItem, ...]:
        # Stable refs and bodies survive; caller-facing metadata is replaced by inert values.
        return tuple(
            SuggestionContextItem(
                ref=item.ref,
                kind=item.kind,
                label=item.kind,
                description="Evidence supplied for this run.",
                content=item.content,
                source="context",
                caller_supplied=True,
            )
            for item in items
        )

    def _ideas(self, ideas: tuple[SuggestionIdea, ...]) -> list[dict[str, Any]]:
        # Allowlisting prevents ranks, revisions, handoffs, and execution authority from leaking.
        return [
            {field: self._json_value(getattr(idea, field)) for field in _IDEA_FIELDS}
            for idea in ideas
        ]

    def _critique(self, critique: SuggestionCritique) -> dict[str, Any]:
        # Critique repair instructions are useful; no provider or workflow metadata is included.
        return {
            key: self._json_value(value) for key, value in critique.model_dump(mode="json").items()
        }

    def _json(self, value: Any) -> str:
        # Compact sorted JSON makes repeated model context deterministic and inexpensive.
        return json.dumps(value, sort_keys=True, separators=(",", ":"))

    def _json_value(self, value: Any) -> Any:
        # Pydantic enums and tuples need JSON-compatible values in the projection.
        if hasattr(value, "value"):
            return value.value
        if isinstance(value, tuple):
            return [self._json_value(item) for item in value]
        if isinstance(value, list):
            return [self._json_value(item) for item in value]
        return value


__all__ = ["SuggestionContextBridge"]
