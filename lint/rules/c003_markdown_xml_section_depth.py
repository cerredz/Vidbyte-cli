"""C003: XML-delimited Markdown prompt sections carry focused, usable depth."""

from __future__ import annotations

import re
from dataclasses import dataclass

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog, SourceFile
from lint.core.registry import Rule

MINIMUM_SENTENCES = 6
MAXIMUM_SENTENCES = 8
ITEM_MINIMUM_SENTENCES = 3
ITEM_MAXIMUM_SENTENCES = 4
ENUMERATED_MINIMUM_ITEMS = 2
_TAG = re.compile(r"<(?P<close>/)?(?P<name>[A-Za-z][\w-]*)(?:\s[^<>]*)?>")
_ITEM = re.compile(r"^[ \t]*\d+\.[ \t]+", re.MULTILINE)
_ABBREVIATIONS = ("e.g.", "i.e.", "etc.", "vs.", "approx.", "cf.")


@dataclass(frozen=True, slots=True)
class XmlSection:
    """One balanced Markdown XML section and the prose enclosed by it."""

    tag: str
    line: int
    body: str
    body_start: int


@dataclass(frozen=True, slots=True)
class EnumeratedItem:
    """One numbered step inside an enumerated XML section, without its marker."""

    ordinal: int
    offset: int
    text: str


class MarkdownXmlSectionAnalyzer:
    """Report XML sections outside their shape's sentence band.

    A section written as prose is measured whole; a section written as a numbered
    procedure is measured per step, because review asks those steps to explain
    themselves individually rather than to share one section-wide budget.
    """

    def analyze(self, catalog: SourceCatalog) -> list[Finding]:
        findings: list[Finding] = []
        for source in catalog.markdown_files():
            for section in self._sections(source):
                items = self._items(section.body)
                finding = (
                    self._enumerated_finding(source, section, items)
                    if len(items) >= ENUMERATED_MINIMUM_ITEMS
                    else self._prose_finding(source, section)
                )
                if finding is not None:
                    findings.append(finding)
        return findings

    def _prose_finding(self, source: SourceFile, section: XmlSection) -> Finding | None:
        # Prose sections keep the original whole-section focus band.
        count = self._sentence_count(section.body)
        if MINIMUM_SENTENCES <= count <= MAXIMUM_SENTENCES:
            return None
        return Finding(
            rule_id=MarkdownXmlSectionDepthRule.id,
            rel_path=source.rel,
            line=section.line,
            source_line=source.line_at(section.line),
            symbol=section.tag,
            extra={"shape": "prose", "sentence_count": str(count)},
        )

    def _enumerated_finding(
        self, source: SourceFile, section: XmlSection, items: tuple[EnumeratedItem, ...]
    ) -> Finding | None:
        # One finding per section still, named for the first step that misses the band.
        for item in items:
            count = self._sentence_count(item.text)
            if ITEM_MINIMUM_SENTENCES <= count <= ITEM_MAXIMUM_SENTENCES:
                continue
            line = source.text.count("\n", 0, section.body_start + item.offset) + 1
            return Finding(
                rule_id=MarkdownXmlSectionDepthRule.id,
                rel_path=source.rel,
                line=line,
                source_line=source.line_at(line),
                symbol=f"{section.tag} step {item.ordinal}",
                extra={
                    "shape": "enumerated",
                    "sentence_count": str(count),
                    "items": str(len(items)),
                },
            )
        return None

    def _sections(self, source: SourceFile) -> tuple[XmlSection, ...]:
        stack: list[tuple[str, int, int]] = []
        sections: list[XmlSection] = []
        for match in _TAG.finditer(source.text):
            token = match.group(0)
            name = match.group("name")
            if token.endswith("/>"):
                continue
            if match.group("close"):
                if not stack or stack[-1][0] != name:
                    continue
                tag, start, body_start = stack.pop()
                line = source.text.count("\n", 0, start) + 1
                sections.append(
                    XmlSection(
                        tag=tag,
                        line=line,
                        body=source.text[body_start : match.start()],
                        body_start=body_start,
                    )
                )
            else:
                stack.append((name, match.start(), match.end()))
        return tuple(sections)

    def _items(self, body: str) -> tuple[EnumeratedItem, ...]:
        # A step runs from its own marker to the next one, so wrapped lines stay with it.
        marks = list(_ITEM.finditer(body))
        items: list[EnumeratedItem] = []
        for index, mark in enumerate(marks):
            stop = marks[index + 1].start() if index + 1 < len(marks) else len(body)
            items.append(
                EnumeratedItem(
                    ordinal=index + 1,
                    offset=mark.start(),
                    text=body[mark.end() : stop],
                )
            )
        return tuple(items)

    def _sentence_count(self, text: str) -> int:
        count = 0
        stripped = text.strip()
        for index, char in enumerate(stripped):
            if char not in ".!?":
                continue
            if index + 1 < len(stripped) and not stripped[index + 1].isspace():
                continue
            if any(stripped[: index + 1].lower().endswith(item) for item in _ABBREVIATIONS):
                continue
            count += 1
        return count


class MarkdownXmlSectionDepthRule(Rule):
    """Requires each Markdown XML section to hold the depth its own shape calls for."""

    id = "C003"
    name = "markdown-xml-section-depth"
    severity = "blocking"
    summary = "Paired XML sections hold 6-8 sentences as prose, or 3-4 per numbered step."

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        return MarkdownXmlSectionAnalyzer().analyze(catalog)

    def explain(self, finding: Finding) -> Diagnostic:
        count = finding.extra.get("sentence_count", "0")
        enumerated = finding.extra.get("shape") == "enumerated"
        what_happened = (
            f"The <{finding.symbol}> section at {finding.rel_path}:{finding.line} contains "
            f"{count} complete sentence(s); XML-delimited Markdown sections written as prose "
            f"require {MINIMUM_SENTENCES} to {MAXIMUM_SENTENCES}."
        )
        how_to_fix = (
            "Rewrite this section as six to eight complete sentences that all serve the tag's "
            "single purpose. Preserve necessary template variables and structured payloads, "
            "but put operational guidance into explicit prose with terminal punctuation."
        )
        if enumerated:
            what_happened = (
                f"{finding.symbol} at {finding.rel_path}:{finding.line} contains {count} "
                f"complete sentence(s); a numbered step in an XML-delimited Markdown section "
                f"requires {ITEM_MINIMUM_SENTENCES} to {ITEM_MAXIMUM_SENTENCES}."
            )
            how_to_fix = (
                "Explain this step in three to four complete sentences: what to do, why it sits "
                "here, and what a reader would get wrong without it. Keep the numbered marker at "
                "the start of the line, and split a step that needs more than four sentences "
                "into two steps rather than letting one step carry the section."
            )
        return Diagnostic(
            what_happened=what_happened,
            why_blocked=(
                "XML structure can make thin guidance look complete or let one section become "
                "an unfocused essay, so each section is held to the depth its shape can carry. "
                "Review of PR #47, comment 4008681822, required retained prompt sections to "
                "contain six to eight sentences and asked that the contract apply to Markdown "
                "XML sections. Review of PR #68, comment 4031063498, then asked one of those "
                "sections to become a numbered list whose items are each explained in three to "
                "four sentences, which a whole-section band cannot express."
            ),
            how_to_fix=how_to_fix,
            correct_examples=(
                "src/vidbyte_cli/services/suggestions/prompts/generator.md",
                "src/vidbyte_cli/services/suggestions/prompts/revision.md",
            ),
            will_not_work=(
                "Adding empty tags, fragments, or punctuation-only padding; those do not provide "
                "usable prompt guidance.",
                "Numbering a prose section to reach the per-step band; a step that carries no "
                "explanation of its own is measured and reported the same way.",
                "Raising lint/baseline.json to admit a newly edited section; the baseline freezes "
                "pre-existing debt only.",
            ),
            verify=self.verify_command(),
        )


RULE = MarkdownXmlSectionDepthRule()
