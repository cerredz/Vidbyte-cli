"""Builds one validated suggestion request from parsed command values.

The command adapter delegates all source selection, JSON loading, context
grouping, and settings normalization to this collaborator. File reads and
model-independent validation finish before the service can begin reasoning.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

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
_MIXED_SOURCE_FIELDS = (
    "goal",
    *tuple(spec.input_name for spec in _CONTEXT_FIELDS),
    "context_files",
    "handoff_file",
    "artifacts",
    "previous_suggestions",
)
_INPUT_SETTING_DEFAULTS: tuple[tuple[str, object], ...] = (
    ("count", 5),
    ("rounds", 2),
    ("horizon", "any"),
)
_HELP = SuggestionHelpLibrary()


class SuggestionRequestBuilder:
    """Resolves one authoritative input source into a service request."""

    def build(self, raw: dict[str, object]) -> SuggestionRequest:
        input_path = raw.get("input_path")
        if isinstance(input_path, str) and input_path:
            return self._from_input(input_path, raw)
        return self._from_fields(raw)

    def _from_fields(self, raw: dict[str, object]) -> SuggestionRequest:
        goal = self._goal(raw.get("goal"))
        categories = self._categories(raw.get("categories"))
        try:
            snapshot = SuggestionContextBuilder().build(
                self._context_fields(raw), self._context_files(raw)
            )
        except ValueError as error:
            raise SuggestionContextUnreadable(str(error)) from error
        settings = SuggestionSettings(
            requested_count=self._required_int(raw.get("count"), 5),
            categories=categories,
            all_categories=bool(raw.get("all_categories")),
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
        items = self._describe(snapshot.items)
        context = SuggestionContextPrimitive(
            goal=goal,
            description=_HELP.load("context_primitive"),
            items=items,
        )
        return SuggestionRequest(goal=goal, context=context, settings=settings)

    def _from_input(self, input_path: str, raw: dict[str, object]) -> SuggestionRequest:
        self._reject_mixed_sources(raw)
        document = self._read_document(input_path)
        return self._from_fields(self._merge_document(document, raw))

    def _reject_mixed_sources(self, raw: dict[str, object]) -> None:
        if any(bool(raw.get(name)) for name in _MIXED_SOURCE_FIELDS):
            raise SuggestionInputInvalid()

    def _read_document(self, input_path: str) -> dict[str, object]:
        try:
            document = (
                json.load(sys.stdin)
                if input_path == "-"
                else json.loads(Path(input_path).read_text(encoding="utf-8"))
            )
        except (OSError, json.JSONDecodeError) as error:
            raise SuggestionContextUnreadable(str(error)) from error
        if not isinstance(document, dict):
            raise SuggestionInputInvalid()
        if document.get("schema_version", 1) != 1:
            raise SuggestionContextUnreadable("unsupported schema version")
        self._goal(document.get("goal"))
        return document

    def _merge_document(
        self, document: dict[str, object], raw: dict[str, object]
    ) -> dict[str, object]:
        merged = dict(raw)
        merged["goal"] = self._goal(document.get("goal"))
        settings = self._mapping_section(document, "settings")
        for name, default in _INPUT_SETTING_DEFAULTS:
            if merged.get(name) in (None, default) and name in settings:
                merged[name] = settings[name]
        context = self._mapping_section(document, "context")
        for spec in _CONTEXT_FIELDS:
            value = context.get(spec.input_name)
            if isinstance(value, list) and not merged.get(spec.input_name):
                merged[spec.input_name] = tuple(str(item) for item in value)
        return merged

    def _mapping_section(self, document: dict[str, object], name: str) -> dict[str, object]:
        section = document.get(name, {})
        return section if isinstance(section, dict) else {}

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
            item.model_copy(update={"description": _HELP.summary(_HELP_ASSET_BY_KIND[item.kind])})
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
