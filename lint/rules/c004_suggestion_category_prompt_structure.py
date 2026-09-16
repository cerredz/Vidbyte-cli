"""C004: suggestion category prompts use one stable, bounded Markdown shape."""

from __future__ import annotations

import re
from dataclasses import dataclass

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog, SourceFile
from lint.core.registry import Rule

MINIMUM_DESCRIPTION_SENTENCES = 6
MAXIMUM_DESCRIPTION_SENTENCES = 8
MINIMUM_CONSIDERATIONS = 8
MAXIMUM_CONSIDERATIONS = 10
# The generator prompt and the handoff already render the candidate field shape and the
# mechanism catalogue, so an asset that restates either makes one contract editable twice.
REMOVED_SECTIONS = frozenset(
    {"timeline", "checklist", "candidate shape", "valid suggestion directions"}
)
_CATEGORY_PREFIX = "src/vidbyte_cli/services/suggestions/prompts/categories/"
_HEADING = re.compile(r"^(?P<level>#{1,2})\s+(?P<text>\S.*)$")
_BULLET = re.compile(r"^\s*-\s+\S")
_SENTENCE_END = re.compile(r"[.!?](?=\s|$)")


@dataclass(frozen=True, slots=True)
class _Section:
    """One canonical level-two category section."""

    line: int
    body: tuple[str, ...]


class SuggestionCategoryPromptAnalyzer:
    """Measures category prompt structure without judging its prose meaning."""

    def analyze(self, catalog: SourceCatalog) -> list[Finding]:
        findings: list[Finding] = []
        for source in catalog.markdown_files():
            if source.rel.startswith(_CATEGORY_PREFIX) and source.rel.endswith(".md"):
                findings.extend(self._analyze_file(source))
        return findings

    def _analyze_file(self, source: SourceFile) -> list[Finding]:
        lines = source.text.splitlines()
        findings: list[Finding] = []
        h1s = [
            (index + 1, match.group("text").strip())
            for index, line in enumerate(lines)
            if (match := _HEADING.match(line)) and match.group("level") == "#"
        ]
        if len(h1s) != 1 or not h1s[0][1]:
            findings.append(self._finding(source, 1, "title", f"count={len(h1s)}"))
        removed_line = next(
            (
                index + 1
                for index, line in enumerate(lines)
                if (match := _HEADING.match(line))
                and match.group("level") == "##"
                and match.group("text").strip().lower() in REMOVED_SECTIONS
            ),
            None,
        )
        if removed_line is not None:
            findings.append(
                self._finding(
                    source,
                    removed_line,
                    "removed-section",
                    lines[removed_line - 1].strip(),
                )
            )
        description = self._section(lines, "Description")
        if description is None:
            findings.append(self._finding(source, 1, "description", "missing"))
        else:
            count = len(_SENTENCE_END.findall(" ".join(description.body)))
            if not MINIMUM_DESCRIPTION_SENTENCES <= count <= MAXIMUM_DESCRIPTION_SENTENCES:
                findings.append(
                    self._finding(source, description.line, "description", f"sentences={count}")
                )
        # The alignment check explains what alignment means for the category. A bullet list
        # there collapses back into the reroute table the explanatory paragraphs replaced.
        alignment = self._section(lines, "Alignment check")
        if alignment is None:
            findings.append(self._finding(source, 1, "alignment-check", "missing"))
        elif bullets := sum(bool(_BULLET.match(line)) for line in alignment.body):
            findings.append(
                self._finding(source, alignment.line, "alignment-check", f"bullets={bullets}")
            )
        considerations = self._section(lines, "Things to consider")
        if considerations is None:
            findings.append(self._finding(source, 1, "considerations", "missing"))
        else:
            count = sum(bool(_BULLET.match(line)) for line in considerations.body)
            if not MINIMUM_CONSIDERATIONS <= count <= MAXIMUM_CONSIDERATIONS:
                findings.append(
                    self._finding(source, considerations.line, "considerations", f"bullets={count}")
                )
        return findings

    def _section(self, lines: list[str], title: str) -> _Section | None:
        start = next(
            (
                index
                for index, line in enumerate(lines)
                if line.strip().lower() == f"## {title}".lower()
            ),
            None,
        )
        if start is None:
            return None
        end = next(
            (
                index
                for index in range(start + 1, len(lines))
                if (match := _HEADING.match(lines[index])) and match.group("level") in {"#", "##"}
            ),
            len(lines),
        )
        return _Section(start + 1, tuple(lines[start + 1 : end]))

    def _finding(self, source: SourceFile, line: int, symbol: str, observed: str) -> Finding:
        return Finding(
            rule_id=SuggestionCategoryPromptStructureRule.id,
            rel_path=source.rel,
            line=line,
            source_line=source.line_at(line),
            symbol=symbol,
            extra={"observed": observed},
        )


class SuggestionCategoryPromptStructureRule(Rule):
    """Requires the stable title, description, and considerations contract."""

    id = "C004"
    name = "suggestion-category-prompt-structure"
    severity = "blocking"
    summary = (
        "Category prompts have a title, 6-8 sentence description, 8-10 considerations, "
        "and a prose alignment check, with no candidate-shape or directions section."
    )

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        return SuggestionCategoryPromptAnalyzer().analyze(catalog)

    def explain(self, finding: Finding) -> Diagnostic:
        return Diagnostic(
            what_happened=(
                f"{finding.rel_path}:{finding.line} violates the category prompt structure "
                f"for {finding.symbol}; observed {finding.extra.get('observed', 'invalid')}."
            ),
            why_blocked=(
                "Category definitions are model-facing contracts shared by the registry and "
                "the category inspection command. Review of PR #50 comments 4011897902, "
                "4011903868, 4012189021, 4012190247, and 4012194075 required one title, a "
                "focused six-to-eight sentence description, and eight-to-ten tailored things "
                "to consider, while removing the old timeline and checklist split. Review "
                "of PR #59 comments 4029573712, 4029584165, and 4029594274 further removed "
                "the `Candidate shape` and `Valid suggestion directions` sections, because "
                "the handoff already generates the structured shape, and required the "
                "alignment check to be prose explaining what alignment means for the "
                "category rather than a bulleted reroute table."
            ),
            how_to_fix=(
                "Keep one level-one title, add exactly the level-two headings `Description` "
                "and `Things to consider`, write six-to-eight complete description sentences, "
                "and provide eight-to-ten specific bullet points. Write `Alignment check` as "
                "one or two paragraphs of prose with no bullets. Delete a `Timeline`, "
                "`Checklist`, `Candidate shape`, or `Valid suggestion directions` section "
                "instead of padding it; candidate fields belong to the generator prompt in "
                "src/vidbyte_cli/services/suggestions/prompts/generator.md."
            ),
            correct_examples=(
                "src/vidbyte_cli/services/suggestions/prompts/categories/verification.md",
                "src/vidbyte_cli/services/suggestions/prompts/categories/goal_clarification.md",
            ),
            will_not_work=(
                "Moving the missing structure into a README or runtime help validator; the "
                "prompt asset itself is what the agent receives.",
                "Raising lint/baseline.json to admit a changed category prompt; the baseline "
                "freezes pre-existing debt and must not hide a regression.",
            ),
            verify=self.verify_command(),
        )


RULE = SuggestionCategoryPromptStructureRule()
