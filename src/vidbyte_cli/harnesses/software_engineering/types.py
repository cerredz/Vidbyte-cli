"""Harness-specific data models for software-engineering — the "custom dataclasses" it owns.

These typed inputs live with the harness, not in the shared types/ package, because only
this harness understands them. They give the translation and presentation hooks something
typed and validated to work with instead of a raw dict.
"""

from __future__ import annotations

from pydantic import BaseModel


class FixInput(BaseModel):
    # Parsed, validated input for `harness software-engineering fix`.
    task: str
    issue: int | None = None
    base: str = "main"
    dry_run: bool = False
