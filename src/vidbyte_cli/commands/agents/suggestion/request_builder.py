"""Builds one strict suggestion request from parsed command values.

The adapter owns source grouping and settings normalization. It completes all
file reads and model-independent validation before the service loads a provider.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from ....lib.errors.failures import (
    SuggestionCategoryUnknown,
    SuggestionContextUnreadable,
    SuggestionInputInvalid,
)
from ....services.suggestions.categories import SuggestionCategories
from ....services.suggestions.context import SuggestionContextBuilder
from ....types.suggestions import (
    SuggestionContextItem,
    SuggestionContextPrimitive,
    SuggestionHorizon,
    SuggestionRequest,
    SuggestionSettings,
)
from .prompts.library import SuggestionHelpLibrary


@dataclass(frozen=True, slots=True)
class ContextFieldSpec:
    """Maps one parsed value collection to its semantic context kind."""

    input_name: str
    context_kind: str
    help_asset: str

    def __post_init__(self) -> None:
        if not all(
            value.strip() for value in (self.input_name, self.context_kind, self.help_asset)
        ):
            raise ValueError("Context field names, kinds, and help assets must be non-empty.")


_CONTEXT_FIELDS = (
    ContextFieldSpec("contexts", "context", "context"),
    ContextFieldSpec("completed", "completed", "completed"),
    ContextFieldSpec("in_progress", "in-progress", "in_progress"),
    ContextFieldSpec("decisions", "decision", "decision"),
    ContextFieldSpec("constraints", "constraint", "constraint"),
    ContextFieldSpec("avoid", "avoid", "avoid"),
    ContextFieldSpec("mistakes", "mistake", "mistakes"),
    ContextFieldSpec("forbidden", "forbidden", "forbidden"),
    ContextFieldSpec("approaches", "approach", "approaches"),
    ContextFieldSpec("outcomes", "outcome", "outcomes"),
    ContextFieldSpec("blockers", "blocker", "blockers"),
    ContextFieldSpec("hypotheses", "hypothesis", "hypotheses"),
    ContextFieldSpec("risks", "risk", "risks"),
    ContextFieldSpec("trajectory", "trajectory", "trajectory"),
    ContextFieldSpec("questions", "question", "question"),
    ContextFieldSpec("capabilities", "capability", "capability"),
    ContextFieldSpec("successes", "success", "success"),
)
_HELP_ASSET_BY_KIND = {
    **{spec.context_kind: spec.help_asset for spec in _CONTEXT_FIELDS},
    "context-file": "context_file",
    "artifact": "artifact",
    "handoff-file": "handoff_file",
    "previous-suggestions": "previous_suggestions",
}
_HELP = SuggestionHelpLibrary()


class SuggestionRequestBuilder:
    """Resolves one authoritative input source into a service request."""

    def build(self, raw: dict[str, object]) -> SuggestionRequest:
        goal = self._goal(raw.get("goal"))
        categories = self._categories(raw.get("categories"))
        try:
            snapshot = SuggestionContextBuilder().build(
                self._context_fields(raw), self._context_files(raw)
            )
        except ValueError as error:
            raise SuggestionContextUnreadable(str(error)) from error
        try:
            settings = SuggestionSettings(
                requested_count=self._required_int(raw.get("count"), 5),
                categories=categories,
                all_categories=bool(raw.get("all_categories")),
                extra_compute=bool(raw.get("extra_compute")),
                horizon=SuggestionHorizon(str(raw.get("horizon") or "any")),
                rounds=self._required_int(raw.get("rounds"), 2),
                provider=self._optional_str(raw.get("provider")),
                model=self._optional_str(raw.get("model")),
                critic_model=self._optional_str(raw.get("critic_model")),
                max_output_tokens=self._optional_int(raw.get("max_output_tokens")),
                max_total_tokens=self._optional_int(raw.get("max_total_tokens")),
                timeout_seconds=self._optional_int(raw.get("timeout_seconds")),
                dry_run=bool(raw.get("dry_run")),
            )
        except (ValidationError, ValueError) as error:
            raise SuggestionInputInvalid() from error
        items = self._describe(snapshot.items)
        context = SuggestionContextPrimitive(
            goal=goal,
            description=_HELP.load("context_primitive"),
            items=items,
            selected_categories=SuggestionCategories().prompt_section(categories),
        )
        try:
            return SuggestionRequest(
                goal=goal,
                context=context,
                context_manifest=snapshot.manifest,
                context_warnings=snapshot.warnings,
                settings=settings,
            )
        except ValidationError as error:
            raise SuggestionInputInvalid() from error

    def _context_fields(self, raw: dict[str, object]) -> dict[str, tuple[str, ...]]:
        fields: dict[str, tuple[str, ...]] = {}
        for spec in _CONTEXT_FIELDS:
            values = raw.get(spec.input_name)
            if isinstance(values, (tuple, list)) and values:
                fields[spec.context_kind] = tuple(str(item) for item in values)
        return fields

    def _context_files(self, raw: dict[str, object]) -> dict[str, tuple[Path, ...]]:
        files: dict[str, tuple[Path, ...]] = {}
        self._add_repeated_paths(files, "context-file", raw.get("context_files"))
        self._add_repeated_paths(files, "artifact", raw.get("artifacts"))
        self._add_single_path(files, "handoff-file", raw.get("handoff_file"))
        self._add_single_path(files, "previous-suggestions", raw.get("previous_suggestions"))
        return files

    def _describe(
        self, items: tuple[SuggestionContextItem, ...]
    ) -> tuple[SuggestionContextItem, ...]:
        return tuple(
            item.model_copy(update={"description": _HELP.load(_HELP_ASSET_BY_KIND[item.kind])})
            for item in items
        )

    def _add_repeated_paths(
        self, files: dict[str, tuple[Path, ...]], kind: str, values: object
    ) -> None:
        if isinstance(values, (tuple, list)) and values:
            files[kind] = tuple(Path(str(item)) for item in values)

    def _add_single_path(
        self, files: dict[str, tuple[Path, ...]], kind: str, value: object
    ) -> None:
        if isinstance(value, (str, Path)) and str(value):
            files[kind] = (Path(str(value)),)

    def _categories(self, value: object) -> tuple[str, ...]:
        listed = tuple(str(item) for item in value) if isinstance(value, (tuple, list)) else ()
        try:
            return SuggestionCategories().require_known(listed)
        except ValueError as error:
            raise SuggestionCategoryUnknown(str(error)) from error

    def _goal(self, value: object) -> str:
        if not isinstance(value, str) or not value.strip():
            raise SuggestionInputInvalid()
        return value.strip()

    def _optional_str(self, value: object) -> str | None:
        if value is None:
            return None
        return str(value).strip() or None

    def _optional_int(self, value: object) -> int | None:
        if value is None or isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.strip().isdigit():
            return int(value.strip())
        return None

    def _required_int(self, value: object, default: int) -> int:
        resolved = self._optional_int(value)
        return default if resolved is None else resolved


__all__ = ["ContextFieldSpec", "SuggestionRequestBuilder"]
