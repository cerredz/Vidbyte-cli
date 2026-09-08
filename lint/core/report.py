"""Renders run outcomes as a scope-first table plus only the detail that is actionable.

The reader is assumed to be a coding agent with this output and nothing else, so a failing
rule prints the consequence, the repair, local precedent, rejected shortcuts, and the exact
command to re-run. Counts always reflect every finding, even when display is truncated.
"""

from __future__ import annotations

import json

from lint.core.diagnostic import Finding
from lint.core.runner import RuleResult


class DiagnosticRenderer:
    """Renders one finding in a stable section order."""

    @classmethod
    def render(cls, result: RuleResult, finding: Finding) -> str:
        # Location, consequence, repair, precedent, rejected shortcuts, then verification.
        diagnostic = result.rule.explain(finding)
        sections = [
            f"CLI-LINT {result.rule.id} {result.rule.name} [{result.rule.severity.upper()}]",
            f"WHERE\n  {finding.location()}\n  {finding.source_line.strip()}",
            cls._section("WHAT HAPPENED", diagnostic.what_happened),
            cls._section("WHY THIS IS BLOCKED", diagnostic.why_blocked),
            cls._section("HOW TO FIX", diagnostic.how_to_fix),
            cls._section(
                "CORRECT EXAMPLES",
                "\n".join(f"- {item}" for item in diagnostic.correct_examples)
                or "No local example exists yet; follow HOW TO FIX.",
            ),
            cls._section(
                "WHAT WILL NOT WORK", "\n".join(f"- {item}" for item in diagnostic.will_not_work)
            ),
            cls._section("VERIFY", diagnostic.verify or result.rule.verify_command()),
        ]
        return "\n\n".join(section for section in sections if section)

    @staticmethod
    def _section(title: str, body: str) -> str:
        # Indents multi-line prose under one stable title, or drops an empty section.
        if not body:
            return ""
        return f"{title}\n" + "\n".join(f"  {line}" for line in body.splitlines())


class RunReport:
    """Aggregates rule results and owns both process status and presentation."""

    def __init__(
        self, results: tuple[RuleResult, ...], truncate: int = 20, expand_all: bool = False
    ) -> None:
        # Keeps complete results; truncation is a display choice, never a counting one.
        self.results = results
        self.truncate = truncate
        self.expand_all = expand_all

    def exit_code(self) -> int:
        # Fails when any selected rule regressed past its allowance or errored.
        return 1 if any(result.failing() for result in self.results) else 0

    def render_text(self) -> str:
        # The summary table first, then only the blocks a reader has to act on.
        blocks = [self._summary()]
        blocks.extend(detail for result in self.results if (detail := self._detail(result)))
        blocks.append("CLI-LINT: PASS" if self.exit_code() == 0 else "CLI-LINT: FAIL")
        return "\n\n".join(blocks)

    def render_json(self) -> str:
        # Serializes every untruncated finding for automation and baseline inspection.
        return json.dumps(
            {
                "exit_code": self.exit_code(),
                "rules": [self._json_rule(result) for result in self.results],
            },
            indent=2,
        )

    def _summary(self) -> str:
        # The rule/count/baseline/verdict table shown ahead of any diagnostic.
        rows = [f"{'RULE':<6} {'NAME':<38} {'FOUND':>6} {'BASE':>6} VERDICT", "-" * 72]
        rows.extend(
            f"{result.rule.id:<6} {result.rule.name[:38]:<38} "
            f"{len(result.findings):>6} {result.allowance:>6} {result.verdict}"
            for result in self.results
        )
        return "\n".join(rows)

    def _detail(self, result: RuleResult) -> str:
        # Expands failures and improvements; known debt stays one line unless asked for.
        if result.error:
            return f"CLI-LINT {result.rule.id} ERRORED\n{result.error}"
        if result.verdict == "IMPROVED":
            return (
                f"{result.rule.id} IMPROVED {result.allowance} -> {len(result.findings)}. "
                f"Lower it with: python lint/run.py --rule {result.rule.id} --update-baseline"
            )
        if result.verdict == "RATCHETED" and not self.expand_all:
            return (
                f"{result.rule.id} RATCHETED: {len(result.findings)} known finding(s). "
                f"Inspect with: python lint/run.py --rule {result.rule.id} --all"
            )
        if result.verdict == "CLEAN":
            return ""
        findings = result.findings if self.expand_all else result.findings[: self.truncate]
        blocks = [
            f"{result.rule.id} {result.verdict}: {len(result.findings)} finding(s), "
            f"allowance {result.allowance}."
        ]
        blocks.extend(DiagnosticRenderer.render(result, finding) for finding in findings)
        return "\n\n".join(blocks)

    def _json_rule(self, result: RuleResult) -> dict[str, object]:
        # One result as a stable machine-readable object.
        return {
            "id": result.rule.id,
            "name": result.rule.name,
            "found": len(result.findings),
            "baseline": result.allowance,
            "verdict": result.verdict,
            "error": result.error or None,
            "findings": [
                {
                    "path": item.rel_path,
                    "line": item.line,
                    "symbol": item.symbol,
                    "source_line": item.source_line,
                    "extra": item.extra,
                }
                for item in result.findings
            ],
        }
