"""Renders one scan's rules as a single Markdown document.

The document is the product: a person reads it, and an agent can paste parts of it into
CLAUDE.md or AGENTS.md. Rules are grouped by scope (global, project, host) in the order the
batches produced them, each with its instruction, when it applies, why, and the prompt IDs that
support it. The header states what was scanned and spent, and a stopped scan says how to resume.
"""

from __future__ import annotations

from collections.abc import Sequence

from ...types.rules import Rule, RulesBatchRecord, RuleScope, RulesScanManifest, RulesScanStatus

_SCOPE_HEADINGS = {
    RuleScope.GLOBAL: "Rules for every project",
    RuleScope.PROJECT: "Project-specific rules",
    RuleScope.HOST: "Rules for one coding agent",
}


class RulesDocumentRenderer:
    """Builds the Markdown rules document for one stored scan."""

    def render(self, manifest: RulesScanManifest, records: Sequence[RulesBatchRecord]) -> str:
        # Header, one section per scope that has rules, and a resume note when work remains.
        rules = [
            rule
            for record in sorted(records, key=lambda item: item.batch_index)
            for rule in record.result.rules
        ]
        lines = [*self._header(manifest, records, len(rules))]
        for scope in RuleScope:
            scoped = [rule for rule in rules if rule.scope is scope]
            if scoped:
                lines += ["", f"## {_SCOPE_HEADINGS[scope]}", ""]
                lines += [
                    line
                    for index, rule in enumerate(scoped, start=1)
                    for line in self._rule(index, rule)
                ]
        if not rules:
            lines += ["", "No standing rules were found in the prompts scanned so far."]
        lines += self._footer(manifest)
        return "\n".join(lines).rstrip() + "\n"

    @staticmethod
    def _header(
        manifest: RulesScanManifest, records: Sequence[RulesBatchRecord], rule_count: int
    ) -> list[str]:
        # What was scanned, from where, and what it cost.
        scope = manifest.scope
        hosts = ", ".join(host.value for host in scope.hosts)
        start = scope.since.date() if scope.since else "the beginning"
        end = scope.until.date() if scope.until else "now"
        window = f"{start} to {end}"
        flagged = sum(len(record.result.flagged_prompt_ids) for record in records)
        return [
            "# Standing rules from your coding-agent prompts",
            "",
            f"- Scan: `{manifest.scan_id}` ({manifest.status.value})",
            f"- Hosts: {hosts}; window: {window}"
            + (f"; project: `{scope.project}`" if scope.project else ""),
            f"- Batches: {len(manifest.completed_batches)} of {len(manifest.batches)}; prompts "
            f"planned: {manifest.prompt_count}; flagged by Jev: {flagged}",
            f"- Rules: {rule_count}; spent: ${manifest.spent_cents / 100:.2f} of "
            f"${manifest.limits.max_spend_cents / 100:.2f}",
        ]

    @staticmethod
    def _rule(index: int, rule: Rule) -> list[str]:
        # One numbered rule block.
        evidence = ", ".join(f"`{prompt_id}`" for prompt_id in rule.evidence_prompt_ids)
        return [
            f"### {index}. {rule.title}",
            "",
            rule.rule,
            "",
            f"- **Applies when:** {rule.applies_when}",
            f"- **Why:** {rule.rationale}",
            f"- **Evidence:** {evidence}",
            "",
        ]

    @staticmethod
    def _footer(manifest: RulesScanManifest) -> list[str]:
        # A stopped scan tells the reader why and how to continue.
        if manifest.status is not RulesScanStatus.STOPPED or manifest.stop_reason is None:
            return []
        return [
            "",
            "---",
            "",
            f"This scan stopped early ({manifest.stop_reason.value}) with "
            f"{len(manifest.pending_batches)} batches left. "
            f"Continue it with `vidbyte-cli agents rules resume {manifest.scan_id}`.",
        ]
