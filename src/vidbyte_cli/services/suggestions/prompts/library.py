"""Loads suggestion prompts and fills their placeholders."""

from __future__ import annotations

from importlib import resources

_ANCHOR = "vidbyte_cli.services.suggestions.prompts"


class SuggestionPrompts:
    """Reads generator and critic Markdown once per run from the wheel."""

    def __init__(self) -> None:
        # Immutable package data, so one per-run cache is sufficient.
        self._cache: dict[str, str] = {}

    def generator_system(self) -> str:
        # System prompt for generation and revision turns.
        return self._read("generator")

    def critic_system(self) -> str:
        # System prompt for independent review turns.
        return self._read("critic")

    def generator_turn(self, goal: str, categories: str, context: str, count: str) -> str:
        # Builds one generation turn with explicit bounds restated in prose.
        return self._render(
            "generator", goal=goal, categories=categories, context=context, count=count
        )

    def critic_turn(self, goal: str, candidates: str) -> str:
        # Builds one critique turn over the candidate artifact only.
        return self._render("critic", goal=goal, candidates=candidates)

    def _render(self, name: str, **values: str) -> str:
        # Literal replacement because prompts contain JSON braces.
        rendered = self._read(name)
        for key, value in values.items():
            rendered = rendered.replace("{{" + key + "}}", value)
        return rendered

    def _read(self, name: str) -> str:
        # Resolves from the installed wheel so cwd never matters.
        if name not in self._cache:
            source = resources.files(_ANCHOR).joinpath(f"{name}.md")
            self._cache[name] = source.read_text(encoding="utf-8").strip()
        return self._cache[name]
