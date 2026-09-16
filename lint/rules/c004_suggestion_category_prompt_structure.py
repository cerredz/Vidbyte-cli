"""C004: suggestion category prompts use one stable, bounded Markdown shape."""

from __future__ import annotations

import re
from dataclasses import dataclass

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog, SourceFile
from lint.core.registry import Rule

DESCRIPTION_PARAGRAPHS = 2
MINIMUM_PARAGRAPH_SENTENCES = 6
MAXIMUM_PARAGRAPH_SENTENCES = 8
MINIMUM_WHY_USE_PARAGRAPHS = 2
MINIMUM_USE_CASES = 10
MAXIMUM_USE_CASES = 15
MINIMUM_EXCLUSION_BULLETS = 4
MAXIMUM_EXCLUSION_BULLETS = 8
_CATEGORY_PREFIX = "src/vidbyte_cli/services/suggestions/prompts/categories/"
_RETIRED_SECTIONS = {"timeline", "checklist", "things to consider", "why use / use cases"}
_HEADING = re.compile(r"^(?P<level>#{1,2})\s+(?P<text>\S.*)$")
_BULLET = re.compile(r"^\s*-\s+\S")
_SENTENCE_END = re.compile(r"[.!?](?=\s|$)")


@dataclass(frozen=True, slots=True)
class _Section:
    """One canonical level-two category section."""

    line: int
    body: tuple[str, ...]

    def paragraphs(self) -> tuple[str, ...]:
        # Joins consecutive prose lines and drops the blank lines separating them.
        blocks: list[list[str]] = []
        for line in self.body:
            if not line.strip():
                blocks.append([])
                continue
            if not blocks:
                blocks.append([])
            blocks[-1].append(line.strip())
        return tuple(" ".join(block) for block in blocks if block)

    def bullets(self) -> tuple[str, ...]:
        # Returns only list items, so prose around a list never inflates its count.
        return tuple(line for line in self.body if _BULLET.match(line))

    def trailing_prose(self) -> str:
        # Returns the prose block that follows the section's last bullet, if any.
        last_bullet = max(
            (index for index, line in enumerate(self.body) if _BULLET.match(line)),
            default=-1,
        )
        if last_bullet < 0:
            return ""
        return " ".join(line.strip() for line in self.body[last_bullet + 1 :] if line.strip())


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
        findings.extend(self._check_title(source, lines))
        findings.extend(self._check_retired(source, lines))
        findings.extend(self._check_description(source, lines))
        findings.extend(self._check_why_use(source, lines))
        findings.extend(self._check_use_cases(source, lines))
        findings.extend(self._check_exclusions(source, lines))
        return findings

    def _check_title(self, source: SourceFile, lines: list[str]) -> list[Finding]:
        # One level-one heading names the category the registry maps onto this asset.
        h1s = [
            (index + 1, match.group("text").strip())
            for index, line in enumerate(lines)
            if (match := _HEADING.match(line)) and match.group("level") == "#"
        ]
        if len(h1s) != 1 or not h1s[0][1]:
            return [self._finding(source, 1, "title", f"count={len(h1s)}")]
        return []

    def _check_retired(self, source: SourceFile, lines: list[str]) -> list[Finding]:
        # Retired headings are reported by name so the repair is a deletion, not a rename.
        findings: list[Finding] = []
        for index, line in enumerate(lines):
            match = _HEADING.match(line)
            if not match or match.group("level") != "##":
                continue
            heading = match.group("text").strip().lower()
            if heading in _RETIRED_SECTIONS:
                findings.append(self._finding(source, index + 1, "retired-section", heading))
        return findings

    def _check_description(self, source: SourceFile, lines: list[str]) -> list[Finding]:
        # Two paragraphs separate what the category is from how its suggestion must behave.
        section = self._section(lines, "Description")
        if section is None:
            return [self._finding(source, 1, "description", "missing")]
        paragraphs = section.paragraphs()
        if len(paragraphs) != DESCRIPTION_PARAGRAPHS:
            return [
                self._finding(source, section.line, "description", f"paragraphs={len(paragraphs)}")
            ]
        findings: list[Finding] = []
        for position, paragraph in enumerate(paragraphs, start=1):
            count = len(_SENTENCE_END.findall(paragraph))
            if not MINIMUM_PARAGRAPH_SENTENCES <= count <= MAXIMUM_PARAGRAPH_SENTENCES:
                findings.append(
                    self._finding(
                        source,
                        section.line,
                        "description",
                        f"paragraph={position} sentences={count}",
                    )
                )
        return findings

    def _check_why_use(self, source: SourceFile, lines: list[str]) -> list[Finding]:
        # Prose, not a list: the rationale has to argue this category against its neighbours.
        section = self._section(lines, "Why use")
        if section is None:
            return [self._finding(source, 1, "why-use", "missing")]
        bullets = section.bullets()
        if bullets:
            return [self._finding(source, section.line, "why-use", f"bullets={len(bullets)}")]
        paragraphs = section.paragraphs()
        if len(paragraphs) < MINIMUM_WHY_USE_PARAGRAPHS:
            return [self._finding(source, section.line, "why-use", f"paragraphs={len(paragraphs)}")]
        return []

    def _check_use_cases(self, source: SourceFile, lines: list[str]) -> list[Finding]:
        # A list long enough to cover the category's situations, short enough to stay read.
        section = self._section(lines, "Use cases")
        if section is None:
            return [self._finding(source, 1, "use-cases", "missing")]
        count = len(section.bullets())
        if not MINIMUM_USE_CASES <= count <= MAXIMUM_USE_CASES:
            return [self._finding(source, section.line, "use-cases", f"items={count}")]
        return []

    def _check_exclusions(self, source: SourceFile, lines: list[str]) -> list[Finding]:
        # Bullets name each disqualifying signal; closing prose routes to the right category.
        section = self._section(lines, "When not to use")
        if section is None:
            return [self._finding(source, 1, "when-not-to-use", "missing")]
        count = len(section.bullets())
        if not MINIMUM_EXCLUSION_BULLETS <= count <= MAXIMUM_EXCLUSION_BULLETS:
            return [self._finding(source, section.line, "when-not-to-use", f"bullets={count}")]
        if not section.trailing_prose():
            return [self._finding(source, section.line, "when-not-to-use", "no-closing-paragraph")]
        return []

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
    """Requires the title, description, rationale, use case, and exclusion contract."""

    id = "C004"
    name = "suggestion-category-prompt-structure"
    severity = "blocking"
    summary = "Category prompts pair a two-paragraph description with Why use and Use cases."

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
                "the category inspection command. Review of PR #55 comments 4029507830, "
                "4029511046, 4029517649, 4029521514, 4029525685, and 4029527568 replaced the "
                "single-paragraph description and the generic `Things to consider` list with "
                "a two-paragraph description, a prose `Why use` rationale argued for this "
                "category rather than suggestions in general, a ten-to-fifteen item `Use "
                "cases` list, and a `When not to use` list closed by a routing paragraph."
            ),
            how_to_fix=(
                "Keep one level-one title. Write `## Description` as exactly two paragraphs "
                "of six to eight complete sentences each. Write `## Why use` as at least two "
                "prose paragraphs with no bullets. List ten to fifteen items under `## Use "
                "cases`. Close with `## When not to use` as four to eight bullets followed by "
                "one paragraph naming the categories that fit instead. Delete `Things to "
                "consider`, `Why use / use cases`, `Timeline`, and `Checklist` rather than "
                "renaming them."
            ),
            correct_examples=(
                "src/vidbyte_cli/services/suggestions/prompts/categories/verification.md",
                "src/vidbyte_cli/services/suggestions/prompts/categories/goal_clarification.md",
            ),
            will_not_work=(
                "Moving the missing structure into a README or runtime help validator; the "
                "prompt asset itself is what the agent receives.",
                "Reusing one category's rationale in another; `Why use` must argue the "
                "boundary between this category and the neighbours it is confused with.",
                "Raising lint/baseline.json to admit a changed category prompt; the baseline "
                "freezes pre-existing debt and must not hide a regression.",
            ),
            verify=self.verify_command(),
        )


RULE = SuggestionCategoryPromptStructureRule()
