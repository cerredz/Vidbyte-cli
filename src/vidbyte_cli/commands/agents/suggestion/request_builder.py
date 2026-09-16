"""Builds one strict suggestion request from parsed command values.

The input dataclass owns argv validation and the builder owns file resolution.
Caller-facing help is kept at the CLI boundary and never copied into agent context.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from pydantic import ValidationError

from ....lib.errors.failures import (
    SuggestionContextUnreadable,
    SuggestionInputInvalid,
)
from ....services.suggestions.categories import SuggestionCategories
from ....services.suggestions.context import SuggestionContextBuilder
from ....types.suggestions import (
    SuggestionContextPrimitive,
    SuggestionHorizon,
    SuggestionRequest,
    SuggestionSettings,
)

_CONTEXT_FIELD_NAMES = (
    "context",
    "completed",
    "in_progress",
    "decision",
    "constraint",
    "avoid",
    "mistakes",
    "forbidden",
    "approaches",
    "outcomes",
    "blockers",
    "hypotheses",
    "risks",
    "trajectory",
    "question",
    "capability",
    "success",
)
_HORIZONS = frozenset(item.value for item in SuggestionHorizon)
_PROVIDERS = frozenset({"openai"})


@dataclass(frozen=True, slots=True)
class SuggestionRunInput:
    """Strict, canonical representation of one Click invocation."""

    goal: str = ""
    context: tuple[str, ...] = ()
    completed: tuple[str, ...] = ()
    in_progress: tuple[str, ...] = ()
    decision: tuple[str, ...] = ()
    constraint: tuple[str, ...] = ()
    avoid: tuple[str, ...] = ()
    mistakes: tuple[str, ...] = ()
    forbidden: tuple[str, ...] = ()
    approaches: tuple[str, ...] = ()
    outcomes: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    hypotheses: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    trajectory: tuple[str, ...] = ()
    question: tuple[str, ...] = ()
    capability: tuple[str, ...] = ()
    success: tuple[str, ...] = ()
    files: tuple[Path, ...] = ()
    count: int = 5
    categories: tuple[str, ...] = ()
    all_categories: bool = False
    extra_compute: bool = False
    horizon: str = "any"
    rounds: int = 2
    provider: str | None = None
    critic_model: str | None = None
    max_output_tokens: int | None = None
    max_total_tokens: int | None = None
    timeout_seconds: int | None = None
    max_agent_calls: int = 64
    max_tool_calls: int = 64
    dry_run: bool = False

    def __post_init__(self) -> None:
        self._validate_goal()
        self._validate_context_values()
        self._validate_files()
        self._validate_selection()
        self._validate_execution_settings()
        self._validate_limits()

    def _validate_goal(self) -> None:
        if not self.goal.strip() or len(self.goal) > 4096:
            raise ValueError("goal must be a non-empty string of at most 4096 characters")

    def _validate_context_values(self) -> None:
        for name in _CONTEXT_FIELD_NAMES:
            values = getattr(self, name)
            if not isinstance(values, tuple) or any(
                type(value) is not str or not value.strip() for value in values
            ):
                raise ValueError(f"{name} must contain only non-empty strings")

    def _validate_files(self) -> None:
        if not isinstance(self.files, tuple) or any(
            not isinstance(path, Path) for path in self.files
        ):
            raise TypeError("files must contain only pathlib.Path values")

    def _validate_selection(self) -> None:
        if type(self.count) is not int or not 2 <= self.count <= 50:
            raise ValueError("suggestions number must be between 2 and 50")
        if not isinstance(self.categories, tuple) or any(
            type(category) is not str or not category.strip() for category in self.categories
        ):
            raise ValueError("categories must contain only non-empty strings")
        if len(set(self.categories)) != len(self.categories):
            raise ValueError("categories must not contain duplicates")
        SuggestionCategories().require_known(self.categories)
        if type(self.all_categories) is not bool or type(self.extra_compute) is not bool:
            raise TypeError("all_categories and extra_compute must be booleans")
        if self.all_categories and self.categories:
            raise ValueError("all_categories and categories cannot both be selected")

    def _validate_execution_settings(self) -> None:
        if type(self.horizon) is not str or self.horizon not in _HORIZONS:
            raise ValueError("horizon must be now, next, later, or any")
        if type(self.rounds) is not int or not 1 <= self.rounds <= 3:
            raise ValueError("rounds must be between 1 and 3")
        if type(self.provider) is not str and self.provider is not None:
            raise TypeError("provider must be omitted or a string")
        if self.provider is not None and self.provider not in _PROVIDERS:
            raise ValueError("provider must be openai or omitted")
        if self.critic_model is not None and (
            type(self.critic_model) is not str or not self.critic_model.strip()
        ):
            raise ValueError("critic_model must be omitted or a non-empty string")

    def _validate_limits(self) -> None:
        if any(
            value is not None and (type(value) is not int or value <= 0)
            for value in (self.max_output_tokens, self.max_total_tokens, self.timeout_seconds)
        ):
            raise ValueError("token and timeout limits must be positive integers")
        if self.max_output_tokens is not None and self.max_output_tokens > 5_000_000:
            raise ValueError("max_output_tokens cannot exceed 5000000")
        if self.max_total_tokens is not None and self.max_total_tokens > 20_000_000:
            raise ValueError("max_total_tokens cannot exceed 20000000")
        if self.timeout_seconds is not None and self.timeout_seconds > 86_400:
            raise ValueError("timeout_seconds cannot exceed 86400")
        if type(self.max_agent_calls) is not int or not 1 <= self.max_agent_calls <= 128:
            raise ValueError("max_agent_calls must be between 1 and 128")
        if type(self.max_tool_calls) is not int or not 1 <= self.max_tool_calls <= 256:
            raise ValueError("max_tool_calls must be between 1 and 256")
        if type(self.dry_run) is not bool:
            raise TypeError("dry_run must be a boolean")


class SuggestionRequestBuilder:
    """Resolves one validated invocation into a service request."""

    def build(self, raw: dict[str, object]) -> SuggestionRequest:
        try:
            values = SuggestionRunInput(**cast(dict[str, Any], raw))
        except (TypeError, ValueError) as error:
            raise SuggestionInputInvalid() from error
        fields = {
            name: getattr(values, name) for name in _CONTEXT_FIELD_NAMES if getattr(values, name)
        }
        try:
            snapshot = SuggestionContextBuilder().build(fields, values.files)
        except ValueError as error:
            raise SuggestionContextUnreadable(str(error)) from error
        try:
            settings = SuggestionSettings(
                suggestions_number=values.count,
                categories=values.categories,
                all_categories=values.all_categories,
                extra_compute=values.extra_compute,
                horizon=SuggestionHorizon(values.horizon),
                rounds=values.rounds,
                provider=values.provider,
                critic_model=values.critic_model,
                max_output_tokens=values.max_output_tokens,
                max_total_tokens=values.max_total_tokens,
                timeout_seconds=values.timeout_seconds,
                max_agent_calls=values.max_agent_calls,
                max_tool_calls=values.max_tool_calls,
                dry_run=values.dry_run,
            )
            return SuggestionRequest(
                goal=values.goal,
                context=SuggestionContextPrimitive(
                    goal=values.goal,
                    description="Caller-supplied task data for this suggestion run.",
                    items=snapshot.items,
                    selected_categories=SuggestionCategories().prompt_section(values.categories),
                ),
                context_manifest=snapshot.manifest,
                context_warnings=snapshot.warnings,
                settings=settings,
            )
        except (ValidationError, ValueError) as error:
            raise SuggestionInputInvalid() from error


__all__ = ["SuggestionRequestBuilder", "SuggestionRunInput"]
