"""Runs the selected rules over one shared catalogue and compares counts to the baseline.

Rules are isolated from each other: a rule that raises is ERRORED, never treated as zero
findings, because a broken detector and a clean surface would otherwise look identical.
"""

from __future__ import annotations

import traceback
from dataclasses import dataclass

from lint.core.baseline import BaselineStore, Verdict
from lint.core.diagnostic import Finding
from lint.core.discovery import SourceCatalog
from lint.core.registry import Rule


@dataclass(frozen=True, slots=True)
class RuleResult:
    """One rule's complete outcome, before any presentation decision."""

    rule: Rule
    findings: tuple[Finding, ...]
    allowance: int
    verdict: Verdict
    error: str = ""

    def failing(self) -> bool:
        # Only a regression or a broken detector fails the process.
        return self.verdict in {"REGRESSED", "ERRORED"}


class RuleRunner:
    """Executes a rule selection against one catalogue with baseline comparison."""

    def __init__(
        self, rules: tuple[Rule, ...], registered_ids: set[str], validate_baseline: bool = True
    ) -> None:
        # Validates the whole catalogue even when only one rule was selected to run.
        self.rules = rules
        self.catalog = SourceCatalog()
        self.store = BaselineStore()
        self.allowances = self.store.load()
        if validate_baseline:
            self.store.validate(registered_ids)

    def run(self) -> tuple[RuleResult, ...]:
        # Executes each rule independently so one failure stays visible and local.
        return tuple(self._run_one(rule) for rule in self.rules)

    def counts(self, results: tuple[RuleResult, ...]) -> dict[str, int]:
        # Refuses to record a baseline while any selected rule is still erroring.
        errors = [result.rule.id for result in results if result.error]
        if errors:
            raise RuntimeError(f"Cannot update the baseline because rules errored: {errors}.")
        return {result.rule.id: len(result.findings) for result in results}

    def _run_one(self, rule: Rule) -> RuleResult:
        # Sorts findings deterministically and converts any unexpected error to ERRORED.
        allowance = self.allowances.get(rule.id, 0)
        try:
            findings = tuple(
                sorted(
                    rule.check(self.catalog),
                    key=lambda item: (item.rel_path, item.line, item.symbol),
                )
            )
        except Exception:
            return RuleResult(
                rule=rule,
                findings=(),
                allowance=allowance,
                verdict="ERRORED",
                error=traceback.format_exc(),
            )
        return RuleResult(
            rule=rule,
            findings=findings,
            allowance=allowance,
            verdict=BaselineStore.verdict_for(len(findings), allowance),
        )
