"""Loads suggestion-agent help descriptions from packaged Markdown assets.

The loader keeps authored prose out of Python while preserving paragraph
boundaries for Click rendering. It also fails fast when an asset violates the
reviewed three-to-four paragraph shape or embeds command-option syntax.
"""

from __future__ import annotations

from importlib import resources


class SuggestionHelpLibrary:
    """Reads and validates one named help description at a time."""

    def __init__(self) -> None:
        self._cache: dict[str, str] = {}

    def load(self, name: str) -> str:
        if name not in self._cache:
            source = resources.files(__package__).joinpath(f"{name}.md")
            text = source.read_text(encoding="utf-8").strip()
            paragraphs = tuple(part.strip() for part in text.split("\n\n") if part.strip())
            if not 3 <= len(paragraphs) <= 4:
                raise ValueError(f"Suggestion help {name!r} must contain three or four paragraphs.")
            if "--" in text:
                raise ValueError(f"Suggestion help {name!r} must not contain command syntax.")
            self._cache[name] = "\n\n".join(paragraphs)
        return self._cache[name]

    def summary(self, name: str) -> str:
        """Return the first one-to-two-sentence paragraph for a context item."""
        return self.load(name).split("\n\n", 1)[0]


__all__ = ["SuggestionHelpLibrary"]
