"""Loads packaged model prompts and fills only their explicit placeholders."""

from __future__ import annotations

from importlib import resources

_ANCHOR = "vidbyte_cli.services.suggestions.prompts"


class SuggestionPrompts:
    """Reads generator, critic, and category Markdown once per run from the wheel."""

    def __init__(self) -> None:
        # Immutable package data, so one per-run cache is sufficient.
        self._cache: dict[str, str] = {}

    def generator_system(self) -> str:
        # System prompt for generation and revision turns.
        return self._read("generator")

    def critic_system(self) -> str:
        # System prompt for independent review turns.
        return self._read("critic")

    def generator_turn(self, goal: str, count: int, revision: str = "") -> str:
        # The context manager carries the goal, categories, and caller records exactly once.
        return self._render("generator", goal=goal, count=str(count), revision=revision)

    def critic_turn(self, goal: str, candidate_ids: str) -> str:
        # The critic receives candidate handoffs through its own context manager.
        return self._render("critic", goal=goal, candidate_ids=candidate_ids)

    def revision_turn(self, goal: str, count: int, handoff: str) -> str:
        # Revision continues the generator's own thread with one general critic handoff.
        return self._render("revision", goal=goal, count=str(count), handoff=handoff)

    def category_prompt(self, name: str) -> str:
        # Category files are model-facing guidance, never command implementation details.
        return self._read(name, category=True)

    def _render(self, name: str, **values: str) -> str:
        # Literal replacement because prompts contain JSON braces.
        rendered = self._read(name)
        for key, value in values.items():
            rendered = rendered.replace("{{" + key + "}}", value)
        return rendered

    def _read(self, name: str, *, category: bool = False) -> str:
        # Resolves from the installed wheel so cwd never matters.
        if name not in self._cache:
            source = resources.files(_ANCHOR)
            if category:
                source = source.joinpath("categories")
            source = source.joinpath(f"{name}.md")
            self._cache[name] = source.read_text(encoding="utf-8").strip()
        return self._cache[name]
