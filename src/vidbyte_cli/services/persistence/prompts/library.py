"""Loads the Markdown prompts in this package and fills their `{{placeholder}}` slots.

No prompt text lives here — every sentence an agent reads is in a `.md` file beside this one,
so a prompt change is a prose diff. This class only reads those files and substitutes values.

Substitution is a literal replace rather than `str.format`, because a task may contain braces
that a format string would try to interpret.
"""

from __future__ import annotations

from importlib import resources

# The package the `.md` files sit in, named explicitly so resolution does not depend on how
# this module was imported. They ship in the wheel via `[tool.setuptools.package-data]`.
_ANCHOR = "vidbyte_cli.services.persistence.prompts"


class PersistencePrompts:
    """Reads each prompt file once and renders it with the values one run supplies."""

    def __init__(self) -> None:
        # One cache per session; the files are immutable package data, so reading twice is waste.
        self._cache: dict[str, str] = {}

    def system_prompt(self) -> str:
        # The standing instruction the thread keeps across every continuation turn.
        return self._read("persistence_system")

    def turn_prompt(self, original_task: str) -> str:
        # Each continuation restates the exact task, so a long loop cannot drift off it.
        return self._render("persistence_turn", original_task=original_task)

    def _render(self, name: str, **values: str) -> str:
        # A literal replace, because a task holding braces would break a format string.
        rendered = self._read(name)
        for key, value in values.items():
            rendered = rendered.replace("{{" + key + "}}", value)
        return rendered

    def _read(self, name: str) -> str:
        # Read through `importlib.resources` so the prompts resolve from the installed wheel.
        if name not in self._cache:
            source = resources.files(_ANCHOR).joinpath(f"{name}.md")
            self._cache[name] = source.read_text(encoding="utf-8")
        return self._cache[name]
