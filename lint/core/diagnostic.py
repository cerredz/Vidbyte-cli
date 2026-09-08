"""The two output contracts every rule shares: where a violation is, and how to repair it.

A `Finding` carries only facts, so it can be counted against the baseline without rendering
anything. A `Diagnostic` carries the prose an agent reads once a rule actually fails; it is
built on demand and never enters the ratchet.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Finding:
    """One rule violation at a stable, clickable repository location."""

    rule_id: str
    rel_path: str
    line: int
    source_line: str = ""
    symbol: str = ""
    extra: dict[str, str] = field(default_factory=dict)

    def location(self) -> str:
        # Renders `path:line` so terminal output links straight to the violation.
        return f"{self.rel_path}:{max(1, self.line)}"


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """Complete consequence and repair guidance for one finding."""

    what_happened: str
    why_blocked: str
    how_to_fix: str
    correct_examples: tuple[str, ...] = ()
    will_not_work: tuple[str, ...] = ()
    verify: str = ""
