"""C003: XML-delimited Markdown prompt sections carry focused, usable depth."""

from __future__ import annotations

import re
from dataclasses import dataclass

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog, SourceFile
from lint.core.registry import Rule

MINIMUM_SENTENCES = 6
MAXIMUM_SENTENCES = 8
_TAG = re.compile(r"<(?P<close>/)?(?P<name>[A-Za-z][\w-]*)(?:\s[^<>]*)?>")
_ABBREVIATIONS = ("e.g.", "i.e.", "etc.", "vs.", "approx.", "cf.")


@dataclass(frozen=True, slots=True)
class XmlSection:
    """One balanced Markdown XML section and the prose enclosed by it."""

    tag: str
    line: int
    body: str


class MarkdownXmlSectionAnalyzer:
    """Find balanced XML sections and report those outside the six-to-eight sentence band."""

    def analyze(self, catalog: SourceCatalog) -> list[Finding]:
        findings: list[Finding] = []
        for source in catalog.markdown_files():
            for section in self._sections(source):
                count = self._sentence_count(section.body)
                if MINIMUM_SENTENCES <= count <= MAXIMUM_SENTENCES:
                    continue
                findings.append(
                    Finding(
                        rule_id=MarkdownXmlSectionDepthRule.id,
                        rel_path=source.rel,
                        line=section.line,
                        source_line=source.line_at(section.line),
                        symbol=section.tag,
                        extra={"sentence_count": str(count)},
                    )
                )
        return findings

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
                    )
                )
            else:
                stack.append((name, match.start(), match.end()))
        return tuple(sections)

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
    """Requires six to eight complete sentences in every paired Markdown XML section."""

    id = "C003"
    name = "markdown-xml-section-depth"
    severity = "blocking"
    summary = "Every paired XML section in Markdown contains 6-8 complete sentences."

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        return MarkdownXmlSectionAnalyzer().analyze(catalog)

    def explain(self, finding: Finding) -> Diagnostic:
        count = finding.extra.get("sentence_count", "0")
        return Diagnostic(
            what_happened=(
                f"The <{finding.symbol}> section at {finding.rel_path}:{finding.line} contains "
                f"{count} complete sentence(s); XML-delimited Markdown sections require "
                f"{MINIMUM_SENTENCES} to {MAXIMUM_SENTENCES}."
            ),
            why_blocked=(
                "XML headings make a prompt look structured even when the enclosed guidance is "
                "too thin to govern an agent or too long to keep one concern focused. Review of "
                "PR #47, comment 4008681822, required retained prompt sections to contain six to "
                "eight sentences and asked that the contract apply to Markdown XML sections."
            ),
            how_to_fix=(
                "Rewrite this section as six to eight complete sentences that all serve the tag's "
                "single purpose. Preserve necessary template variables and structured payloads, "
                "but put operational guidance into explicit prose with terminal punctuation."
            ),
            correct_examples=(
                "src/vidbyte_cli/services/suggestions/prompts/generator.md",
                "src/vidbyte_cli/services/suggestions/prompts/critic.md",
            ),
            will_not_work=(
                "Adding empty tags, fragments, or punctuation-only padding; those do not provide "
                "usable prompt guidance.",
                "Raising lint/baseline.json to admit a newly edited section; the baseline freezes "
                "pre-existing debt only.",
            ),
            verify=self.verify_command(),
        )


RULE = MarkdownXmlSectionDepthRule()
