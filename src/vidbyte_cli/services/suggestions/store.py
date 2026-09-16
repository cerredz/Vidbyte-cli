"""Owns one suggestion run's validated, run-local candidate state and tools."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from ...types.suggestions import SuggestionDraft, SuggestionIdea, SuggestionRequest
from .handoff import SuggestionHandoffBuilder


class ToolCallLimitReached(Exception):
    """Signals that a curation pass exhausted its run-local tool budget."""


class SuggestionStore:
    """Provides copy-on-write suggestion state to the tool-enabled generator."""

    def __init__(self, request: SuggestionRequest, categories: tuple[str, ...]) -> None:
        # Limits are deliberately local until the guardrail feature exposes caller settings.
        self._request = request
        self._categories = frozenset(categories)
        self._allowed_evidence = self._evidence_refs(request)
        self._max_tool_calls = request.settings.max_tool_calls
        self._handoffs = SuggestionHandoffBuilder()
        self._ideas: dict[str, SuggestionIdea] = {}
        self._tool_calls = 0
        self._more_requests = 0
        self._mutations = 0
        self._next_id = 1

    def seed(self, ideas: tuple[SuggestionIdea, ...]) -> None:
        """Seeds the committed store with host-assigned initial ideas."""
        if len(ideas) > 40:
            raise ValueError("suggestion store cannot contain more than 40 ideas")
        self._ideas = {idea.id: idea for idea in ideas}
        self._next_id = self._next_identifier(ideas)

    def snapshot(self) -> tuple[SuggestionIdea, ...]:
        """Returns the active ideas in deterministic insertion order."""
        return tuple(self._ideas.values())

    def working_copy(self) -> SuggestionStore:
        """Returns an isolated copy whose mutations are not yet committed."""
        copied = SuggestionStore(self._request, tuple(self._categories))
        copied._ideas = dict(self._ideas)
        copied._max_tool_calls = self._max_tool_calls
        copied._tool_calls = self._tool_calls
        copied._more_requests = self._more_requests
        copied._mutations = self._mutations
        copied._next_id = self._next_id
        return copied

    def commit_from(self, working: SuggestionStore) -> None:
        """Commits a completed working copy as the store's new active snapshot."""
        if working._request is not self._request:
            raise ValueError("working store belongs to another suggestion request")
        self._ideas = dict(working._ideas)
        self._tool_calls = working._tool_calls
        self._more_requests = working._more_requests
        self._mutations = working._mutations
        self._next_id = working._next_id

    def add_suggestion(self, category_id: str, suggestion: SuggestionDraft) -> str:
        """Adds or updates one validated suggestion and returns its stable ID."""
        self._begin_tool_call()
        if not isinstance(suggestion, SuggestionDraft):
            raise ValueError("suggestion must match the SuggestionDraft schema")
        if category_id not in self._categories:
            raise ValueError(f"unknown suggestion category: {category_id}")
        if suggestion.primary_category != category_id:
            raise ValueError("category_id must match suggestion.primary_category")
        if not set(suggestion.secondary_categories) <= self._categories:
            raise ValueError("suggestion contains an unknown secondary category")
        if not set(suggestion.evidence_refs) <= self._allowed_evidence:
            raise ValueError("suggestion cites an unavailable context reference")

        existing = self._existing_update(suggestion)
        if existing is None and len(self._ideas) >= 40:
            raise ValueError("suggestion store capacity is full")
        fingerprint = self._fingerprint(suggestion)
        if any(
            self._fingerprint_from_idea(idea) == fingerprint
            and idea.id != (existing.id if existing else "")
            for idea in self._ideas.values()
        ):
            raise ValueError("suggestion duplicates an active idea")

        idea_id = existing.id if existing else self._allocate_id()
        revision = existing.revision + 1 if existing else 1
        rank = existing.rank if existing else len(self._ideas) + 1
        values = suggestion.model_dump(exclude={"idea_id"})
        idea = SuggestionIdea(
            **values,
            id=idea_id,
            revision=revision,
            rank=rank,
            review_summary="Updated by the generator after critique."
            if existing
            else "Added by the generator after critique.",
            handoff=self._handoffs.build_draft(suggestion, self._request, idea_id, revision),
        )
        if existing:
            self._ideas[idea_id] = idea
        else:
            self._ideas[idea_id] = idea
        self._mutations += 1
        return f"Stored suggestion {idea_id} in category {category_id}."

    def remove_suggestion(self, suggestion_id: str) -> str:
        """Removes one stable suggestion ID without renumbering other ideas."""
        self._begin_tool_call()
        if not isinstance(suggestion_id, str) or not suggestion_id.strip():
            raise ValueError("suggestion_id must be a non-empty stable ID")
        if suggestion_id not in self._ideas:
            return f"No active suggestion exists with ID {suggestion_id}."
        del self._ideas[suggestion_id]
        self._mutations += 1
        return f"Removed suggestion {suggestion_id}."

    def more_suggestions(self) -> str:
        """Returns bounded guidance for whether the generator may add more ideas."""
        self._begin_tool_call()
        if self._more_requests >= 3:
            raise ValueError("more_suggestions request cap reached")
        self._more_requests += 1
        active_categories = {idea.primary_category for idea in self._ideas.values()}
        missing = sorted(self._categories - active_categories)
        gap_text = ", ".join(missing[:8]) or "none"
        remaining = max(40 - len(self._ideas), 0)
        return (
            f"You may add up to {remaining} more suggestions. Missing categories: {gap_text}. "
            "Add only distinct, evidence-grounded ideas, then finish when the slate is useful."
        )

    def tools(self) -> tuple[Callable[..., Any], ...]:
        """Returns exactly the state tools exposed to the curation agent."""

        def add_tool(category_id: str, suggestion: SuggestionDraft) -> str:
            return self.add_suggestion(category_id, suggestion)

        def remove_tool(number: str | int) -> str:
            if isinstance(number, int):
                active = tuple(self._ideas)
                if number < 1 or number > len(active):
                    return f"No active suggestion exists at number {number}."
                number = active[number - 1]
            return self.remove_suggestion(number)

        def more_tool() -> str:
            return self.more_suggestions()

        # These public model-facing names match the workflow contract while the
        # snake-case methods remain convenient for local tests and callers.
        add_tool.__name__ = "AddSuggestionType"
        remove_tool.__name__ = "RemoveSuggestion"
        more_tool.__name__ = "MoreSuggestions"
        return (add_tool, remove_tool, more_tool)

    @property
    def mutation_count(self) -> int:
        """Reports successful state mutations for early no-progress stopping."""
        return self._mutations

    def _begin_tool_call(self) -> None:
        """Counts an attempted tool call and enforces the run-local cap."""
        if self._tool_calls >= self._max_tool_calls:
            raise ToolCallLimitReached("suggestion tool-call cap reached")
        self._tool_calls += 1

    def _existing_update(self, suggestion: SuggestionDraft) -> SuggestionIdea | None:
        """Resolves an optional existing ID for an in-place generator update."""
        if suggestion.idea_id is None:
            return None
        existing = self._ideas.get(suggestion.idea_id)
        if existing is None:
            raise ValueError("suggestion.idea_id must name an active suggestion")
        return existing

    def _allocate_id(self) -> str:
        """Allocates the next host-owned stable idea identifier."""
        idea_id = f"idea-{self._next_id:03d}"
        self._next_id += 1
        return idea_id

    def _next_identifier(self, ideas: tuple[SuggestionIdea, ...]) -> int:
        """Finds the first identifier after the seeded ideas."""
        numbers = [int(idea.id.removeprefix("idea-")) for idea in ideas]
        return max(numbers, default=0) + 1

    def _fingerprint(self, suggestion: SuggestionDraft) -> str:
        """Builds a stable duplicate key from the suggestion's actionable content."""
        values = {
            "title": suggestion.title,
            "summary": suggestion.summary,
            "first_action": suggestion.first_action,
            "suggested_actions": suggestion.suggested_actions,
        }
        return json.dumps(values, sort_keys=True, separators=(",", ":")).lower()

    def _fingerprint_from_idea(self, idea: SuggestionIdea) -> str:
        """Builds the same duplicate key for an active idea snapshot."""
        values = {
            "title": idea.title,
            "summary": idea.summary,
            "first_action": idea.first_action,
            "suggested_actions": idea.suggested_actions,
        }
        return json.dumps(values, sort_keys=True, separators=(",", ":")).lower()

    def _evidence_refs(self, request: SuggestionRequest) -> frozenset[str]:
        """Resolves evidence IDs from the manifest, falling back to context items."""
        refs = {entry.ref for entry in request.context_manifest if entry.status != "omitted"}
        return frozenset(refs or {item.ref for item in request.context_items})


__all__ = ["SuggestionStore", "ToolCallLimitReached"]
