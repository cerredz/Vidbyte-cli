"""C005: caller-facing suggestion context help has the required titled depth."""

from __future__ import annotations

import re
from dataclasses import dataclass

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog, SourceFile
from lint.core.registry import Rule

MINIMUM_SENTENCES = 6
MAXIMUM_SENTENCES = 8
_HELP_PREFIX = "src/vidbyte_cli/commands/agents/suggestion/prompts/"
_HELP_NAMES = frozenset(
    {
        "context",
        "context_file",
        "completed",
        "in_progress",
        "decision",
        "constraint",
        "avoid",
        "question",
        "capability",
        "success",
        "mistakes",
        "forbidden",
        "approaches",
        "outcomes",
        "blockers",
        "hypotheses",
        "risks",
        "trajectory",
        "context_primitive",
        "artifact",
        "handoff_file",
        "previous_suggestions",
    }
)
_SECTION = re.compile(r"^\*\*(?P<title>[^*]+)\*\*$")
_SENTENCE_END = re.compile(r"[.!?](?=\s|$)")
_REQUIRED = ("Title", "Description", "Why it matters", "Influence on output")


@dataclass(frozen=True, slots=True)
class _HelpSection:
    """One bold help heading and the prose beneath it."""

    line: int
    body: tuple[str, ...]


class SuggestionHelpSectionAnalyzer:
    """Measures authored help sections without judging their content."""

    def analyze(self, catalog: SourceCatalog) -> list[Finding]:
        findings: list[Finding] = []
        for source in catalog.markdown_files():
            name = source.rel.rsplit("/", 1)[-1].removesuffix(".md")
            if source.rel.startswith(_HELP_PREFIX) and name in _HELP_NAMES:
                findings.extend(self._analyze_file(source))
        return findings

    def _analyze_file(self, source: SourceFile) -> list[Finding]:
        lines = source.text.splitlines()
        sections = self._sections(lines)
        findings: list[Finding] = []
        for title in _REQUIRED:
            section = sections.get(title.lower())
            if section is None:
                findings.append(self._finding(source, 1, title, "missing"))
                continue
            count = len(_SENTENCE_END.findall(" ".join(section.body)))
            if not MINIMUM_SENTENCES <= count <= MAXIMUM_SENTENCES:
                findings.append(self._finding(source, section.line, title, f"sentences={count}"))
        return findings

    def _sections(self, lines: list[str]) -> dict[str, _HelpSection]:
        headings = [
            (index, match.group("title").strip().lower())
            for index, line in enumerate(lines)
            if (match := _SECTION.match(line.strip()))
        ]
        sections: dict[str, _HelpSection] = {}
        for position, (start, title) in enumerate(headings):
            end = headings[position + 1][0] if position + 1 < len(headings) else len(lines)
            sections[title] = _HelpSection(start + 1, tuple(lines[start + 1 : end]))
        return sections

    def _finding(self, source: SourceFile, line: int, symbol: str, observed: str) -> Finding:
        return Finding(
            rule_id=SuggestionHelpSectionDepthRule.id,
            rel_path=source.rel,
            line=line,
            source_line=source.line_at(line),
            symbol=symbol,
            extra={"observed": observed},
        )


class SuggestionHelpSectionDepthRule(Rule):
    """Requires six-to-eight sentences under each bold context-help heading."""

    id = "C005"
    name = "suggestion-help-section-depth"
    severity = "blocking"
    summary = "Suggestion context help has four bold sections, each containing 6-8 sentences."

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        return SuggestionHelpSectionAnalyzer().analyze(catalog)

    def explain(self, finding: Finding) -> Diagnostic:
        return Diagnostic(
            what_happened=(
                f"{finding.rel_path}:{finding.line} has an invalid {finding.symbol} help "
                f"section; observed {finding.extra.get('observed', 'invalid')}."
            ),
            why_blocked=(
                "Caller-facing context help is the specification an agent reads before it "
                "chooses what state to supply. PR #50 comment 4011964934 asked every context "
                "input to explain its title, description, reason for use, and influence on "
                "output in six-to-eight sentence sections with bold titles. Comment "
                "4011939173 asked for this contract to live in the repository lint suite "
                "rather than in a runtime help validator."
            ),
            how_to_fix=(
                "Add the bold headings `Title`, `Description`, `Why it matters`, and "
                "`Influence on output`. Write six-to-eight complete, caller-facing sentences "
                "under each heading and keep implementation mechanics out of the explanation."
            ),
            correct_examples=(
                "src/vidbyte_cli/commands/agents/suggestion/prompts/context.md",
                "src/vidbyte_cli/commands/agents/suggestion/prompts/trajectory.md",
            ),
            will_not_work=(
                "Counting a one-line label as a section or moving the prose into Python; the "
                "asset itself is what Click and the caller receive.",
                "Raising lint/baseline.json to admit a shallow help asset; the baseline freezes "
                "old debt and cannot be used for a new review contract.",
            ),
            verify=self.verify_command(),
        )


RULE = SuggestionHelpSectionDepthRule()
