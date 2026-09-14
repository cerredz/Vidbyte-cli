"""The rule contract and the fixed, ordered catalogue of registered rules.

Adding a rule means one new module under `lint/rules/`, one entry in `_RULE_MODULES`, one
row in `lint/README.md`, and one seeded key in `lint/baseline.json`. The registry imports
rule modules but never scans source itself.
"""

from __future__ import annotations

import importlib

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog

_RULE_MODULES = (
    "lint.rules.c001_command_help_description_depth",
    "lint.rules.c002_paid_execute_comment_density",
)


class RuleSelectionError(RuntimeError):
    """A requested rule ID does not exist, or the catalogue contains a duplicate."""


class Rule:
    """The contract every independently baselined rule implements."""

    id = ""
    name = ""
    severity = "blocking"
    summary = ""

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        # Returns every finding without mutating source or importing the CLI.
        raise NotImplementedError

    def explain(self, finding: Finding) -> Diagnostic:
        # Returns self-contained repair guidance for one finding.
        raise NotImplementedError

    def verify_command(self) -> str:
        # The exact focused command to re-run after repairing this rule.
        return f"python lint/run.py --rule {self.id}"


class RuleRegistry:
    """Loads the fixed catalogue once and serves stable selections from it."""

    def __init__(self) -> None:
        # Imports every registered module and validates non-empty, unique IDs.
        self._rules = self._load()

    def all(self) -> tuple[Rule, ...]:
        # Returns every rule in stable lexical ID order.
        return self._rules

    def select(self, rule_id: str | None) -> tuple[Rule, ...]:
        # Returns one named rule, or the whole catalogue, naming valid IDs on failure.
        if rule_id is None:
            return self.all()
        wanted = rule_id.upper()
        chosen = tuple(rule for rule in self._rules if rule.id == wanted)
        if not chosen:
            valid = ", ".join(rule.id for rule in self._rules)
            raise RuleSelectionError(f"Unknown lint rule {wanted!r}. Valid rules: {valid}.")
        return chosen

    def _load(self) -> tuple[Rule, ...]:
        # Reads each module's exported RULE and rejects duplicate or blank identifiers.
        rules: tuple[Rule, ...] = tuple(
            importlib.import_module(path).RULE for path in _RULE_MODULES
        )
        seen: set[str] = set()
        for rule in rules:
            if not rule.id or rule.id in seen:
                raise RuleSelectionError(
                    f"Duplicate or blank lint rule ID {rule.id!r} in the registered catalogue."
                )
            seen.add(rule.id)
        return tuple(sorted(rules, key=lambda item: item.id))
