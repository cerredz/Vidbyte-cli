"""Loads caller-facing suggestion help from packaged Markdown assets.

The loader keeps authored prose out of Python and leaves content standards to
the repository lint suite, so help rendering never becomes a hidden validator.
"""

from __future__ import annotations

from importlib import resources


class SuggestionHelpLibrary:
    """Reads one named help description at a time."""

    def __init__(self) -> None:
        self._cache: dict[str, str] = {}

    def load(self, name: str) -> str:
        if name not in self._cache:
            source = resources.files(__package__).joinpath(f"{name}.md")
            self._cache[name] = source.read_text(encoding="utf-8").strip()
        return self._cache[name]

    def summary(self, name: str) -> str:
        """Return the first authored help section for a context item."""
        return self.load(name).split("\n\n", 1)[0]


__all__ = ["SuggestionHelpLibrary"]
