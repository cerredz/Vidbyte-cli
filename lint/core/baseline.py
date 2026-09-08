"""The per-rule debt ratchet: existing violations are frozen, new ones fail the build.

An allowance records how many violations predated a rule's gate. It may be lowered after a
real repair and may never be raised to make a regression pass. A missing or stale key is a
contract error, so a registered rule cannot quietly escape enforcement.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from lint.core.discovery import SourceCatalog

Verdict = Literal["CLEAN", "RATCHETED", "IMPROVED", "REGRESSED", "ERRORED"]


class BaselineContractError(RuntimeError):
    """The baseline file is malformed or disagrees with the registered rule catalogue."""


class BaselineStore:
    """Reads, validates, and deterministically rewrites `lint/baseline.json`."""

    def __init__(self, path: Path | None = None) -> None:
        # Binds the store to the repository's own baseline unless a test overrides it.
        self.path = path or SourceCatalog.repository_root() / "lint" / "baseline.json"

    @staticmethod
    def verdict_for(found: int, allowance: int) -> Verdict:
        # Classifies one complete finding count against its frozen ceiling.
        if found > allowance:
            return "REGRESSED"
        if found == allowance == 0:
            return "CLEAN"
        if found == allowance:
            return "RATCHETED"
        return "IMPROVED"

    def load(self) -> dict[str, int]:
        # Parses non-negative integer allowances with actionable file context on failure.
        if not self.path.is_file():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise BaselineContractError(
                f"Could not read valid JSON from the baseline {self.path}: {error}. "
                "Restore a sorted object mapping each rule ID to a count."
            ) from error
        if not isinstance(payload, dict) or any(
            not isinstance(key, str) or not isinstance(value, int) or value < 0
            for key, value in payload.items()
        ):
            raise BaselineContractError(
                f"The baseline {self.path} must map every rule ID to a non-negative integer."
            )
        return dict(payload)

    def validate(self, registered: set[str]) -> None:
        # Rejects both missing and stale IDs, in either direction.
        actual = set(self.load())
        if actual != registered:
            raise BaselineContractError(
                f"Baseline catalogue mismatch at {self.path}: "
                f"missing={sorted(registered - actual)}, stale={sorted(actual - registered)}. "
                "Run --update-baseline only after reviewing every new finding."
            )

    def write(self, counts: dict[str, int]) -> None:
        # Rewrites the complete sorted catalogue with UTF-8 and a trailing newline.
        ordered = {key: counts[key] for key in sorted(counts)}
        self.path.write_text(json.dumps(ordered, indent=2) + "\n", encoding="utf-8")
