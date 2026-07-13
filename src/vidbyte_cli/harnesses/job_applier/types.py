"""Harness-specific data models for job-applier — the "custom dataclasses" a harness owns.

These typed inputs/outputs live with the harness, not in the shared types/ package, because
only this harness understands them. They exist to give the translation and presentation
hooks something typed to work with instead of a raw dict.
"""

from __future__ import annotations

from pydantic import BaseModel


class ApplyInput(BaseModel):
    # Parsed, validated input for `harness job-applier apply`.
    query: str
    resume: str
    limit: int = 10
    dry_run: bool = False
