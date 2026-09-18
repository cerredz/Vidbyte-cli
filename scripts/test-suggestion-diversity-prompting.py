"""Verification for the suggestion diversity prompting change.

Run with `python scripts/test-suggestion-diversity-prompting.py`. Every case reads the packaged
generator and critic prompts through the real SuggestionPrompts loader, measures them with the
real C003 analyzer, and checks every schema name the new prose relies on against the real types.
No model is called.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from lint.rules.c003_markdown_xml_section_depth import (  # noqa: E402
    MarkdownXmlSectionAnalyzer,
)
from vidbyte_cli.services.suggestions.prompts.library import SuggestionPrompts  # noqa: E402
from vidbyte_cli.types.suggestions import (  # noqa: E402
    CritiqueConfidence,
    CritiqueEvidenceCheck,
    CritiqueIssueSeverity,
    CritiqueVerdict,
    SuggestionCritique,
    SuggestionCritiqueIssue,
    SuggestionCritiqueRubric,
    SuggestionCritiqueRubricItem,
    SuggestionCritiqueSignals,
    SuggestionDraft,
)

PROMPTS = ROOT / "src" / "vidbyte_cli" / "services" / "suggestions" / "prompts"
_STEP = re.compile(r"^(\d+)\. (.+)$", re.MULTILINE)

# Pre-change step bodies, keyed by their new step number, which must survive verbatim.
_GENERATOR_KEPT = {
    1: "Restate the goal to yourself as an outcome an observer could check",
    2: "Read the selected category block and settle which single category",
    3: "Sort every context item into supported, assumed, missing",
    6: "Ask what would have to be true for each draft idea to work",
    7: "Hold the drafts against one another and against work the context records",
    8: "Decide how many candidates the evidence genuinely supports",
}
_CRITIC_KEPT = {
    1: "Read each candidate against the goal, the selected categories",
    2: "Trace every evidence reference back to the context snapshot",
    3: "Ask whether the action sequence, decision points, considerations",
    4: "Hold the candidates against one another and against work the context records",
    6: "Apply every section of the general suggestion rubric below independently",
    7: "Use the section readings to locate what is actually wrong",
    8: "Decide the verdict for yourself, then record it against the identifier",
}


class PromptFile:
    """One packaged prompt read from disk, split into its XML sections and numbered steps."""

    def __init__(self, name: str) -> None:
        # Reads the source file so section order and raw text can be inspected exactly.
        self.name = name
        self.text = (PROMPTS / f"{name}.md").read_text(encoding="utf-8")

    def section(self, tag: str) -> str:
        # Returns the body of one paired tag, or an empty string when the tag is absent.
        match = re.search(rf"<{tag}>\n(.*?)\n</{tag}>", self.text, re.DOTALL)
        return match.group(1) if match else ""

    def section_order(self) -> list[str]:
        # Lists opening tags in document order so placement can be asserted.
        return re.findall(r"^<([A-Z][A-Za-z]+)>$", self.text, re.MULTILINE)

    def steps(self, tag: str = "Algorithm") -> dict[int, str]:
        # Maps each numbered step in a section to its full single-line text.
        return {int(n): body for n, body in _STEP.findall(self.section(tag))}


class DiversityPromptVerifier:
    """Runs every design-doc test case against the real prompts, analyzer, and schema."""

    def __init__(self) -> None:
        # Loads both prompts once and prepares the result ledger.
        self.generator = PromptFile("generator")
        self.critic = PromptFile("critic")
        self.results: list[tuple[bool, str]] = []

    def run(self) -> int:
        # Executes all groups, prints the summary line, and returns a process status.
        self.check_generator_prompt()
        self.check_critic_prompt()
        self.check_both_prompts()
        self.check_schema_contracts()
        passed = sum(ok for ok, _ in self.results)
        print(f"{passed}/{len(self.results)} tests passed")
        return 0 if passed == len(self.results) else 1

    def record(self, name: str, ok: bool) -> None:
        # Stores one labeled outcome and prints it immediately.
        self.results.append((ok, name))
        print(f"{'PASS' if ok else 'FAIL'} {name}")

    def check_generator_prompt(self) -> None:
        # Covers step order, numbering, verbatim survival, and the new goal and output sentences.
        steps = self.generator.steps()
        self.record(
            "generator has eight algorithm steps numbered 1..8", sorted(steps) == list(range(1, 9))
        )
        self.record(
            "generator orders directions, then titles, then what-must-be-true",
            "broad directions" in steps.get(4, "")
            and "one-line titles" in steps.get(5, "")
            and steps.get(6, "").startswith("Ask what would have to be true"),
        )
        self.record(
            "generator keeps every pre-existing step verbatim under its new number",
            all(steps.get(n, "").startswith(prefix) for n, prefix in _GENERATOR_KEPT.items()),
        )
        self.record(
            "generator step 4 uses ordinary stakeholder lenses rather than archetypes",
            "stakeholder lens is an ordinary, specific position" in steps.get(4, "")
            and "rather than an archetype" in steps.get(4, ""),
        )
        self.record(
            "generator states the typicality estimate appears in no field",
            "never a prediction that the idea will succeed" in steps.get(5, "")
            and "appears in no field" in steps.get(5, ""),
        )
        self.record(
            "generator goal carries the population-referential sentence",
            "stand out from what other capable generators" in self.generator.section("Goal"),
        )
        self.record(
            "generator output spreads across directions without trading support for novelty",
            "Spread the returned candidates across the directions you mapped"
            in self.generator.section("Output")
            and "never trade a supported familiar candidate" in self.generator.section("Output"),
        )
        bullets = [
            line
            for line in self.generator.section("Prohibitions").splitlines()
            if line.startswith("- ")
        ]
        self.record("generator prohibitions keep their eight bullets", len(bullets) == 8)
        self.record(
            "packaged loader serves this checkout's generator and critic text",
            SuggestionPrompts().generator_system() == self.generator.text.strip()
            and SuggestionPrompts().critic_system() == self.critic.text.strip(),
        )
        rendered = SuggestionPrompts().generator_turn("Ship the export", 6)
        self.record(
            "generator turn renders goal and count and introduces no new token",
            "Generate up to 6 candidates" in rendered
            and "Goal: Ship the export" in rendered
            and set(re.findall(r"\{\{(\w+)\}\}", rendered)) == {"categories", "context"},
        )

    def check_critic_prompt(self) -> None:
        # Covers the Diversity section's placement and claims and the new algorithm step.
        order = self.critic.section_order()
        self.record(
            "critic places Diversity between CriticOutput and Algorithm",
            "Diversity" in order
            and order.index("CriticOutput") + 1 == order.index("Diversity")
            and order.index("Diversity") + 1 == order.index("Algorithm"),
        )
        steps = self.critic.steps()
        self.record(
            "critic has eight algorithm steps numbered 1..8", sorted(steps) == list(range(1, 9))
        )
        self.record(
            "critic keeps every pre-existing step verbatim under its new number",
            all(steps.get(n, "").startswith(prefix) for n, prefix in _CRITIC_KEPT.items()),
        )
        self.record(
            "critic settles both readings before the rubric step",
            "default answer" in steps.get(5, "")
            and "before the rubric" in steps.get(5, "")
            and steps.get(6, "").startswith("Apply every section of the general suggestion rubric"),
        )
        diversity = self.critic.section("Diversity")
        self.record(
            "critic keeps originality from lifting and familiarity from sinking a verdict",
            "originality never lifts a candidate" in diversity
            and "familiarity never sinks a candidate" in diversity,
        )
        self.record(
            "critic forbids rejecting a sound candidate for crowding alone",
            "rather than rejecting a sound candidate" in diversity,
        )
        self.record(
            "critic keeps ten rubric sections with ten Rating guidelines",
            len(re.findall(r"^## \d+\. ", self.critic.text, re.MULTILINE)) == 10
            and self.critic.text.count("### Rating guidelines") == 10,
        )
        rendered = SuggestionPrompts().critic_turn("Ship the export", "idea-001, idea-002")
        self.record(
            "critic turn renders goal and identifiers with no unreplaced token",
            "Candidate identifiers: idea-001, idea-002" in rendered
            and not re.findall(r"\{\{\w+\}\}", rendered),
        )

    def check_both_prompts(self) -> None:
        # Measures both prompts with the real C003 analyzer and scans for stray tag-like text.
        analyzer = MarkdownXmlSectionAnalyzer()
        catalog = SimpleNamespace(
            markdown_files=lambda: [self._source(p) for p in (self.generator, self.critic)]
        )
        findings = analyzer.analyze(catalog)
        self.record("generator and critic pass C003 with zero findings", findings == [])
        stray = [
            tag
            for prompt in (self.generator, self.critic)
            for tag in re.findall(r"<([A-Za-z][\w-]*)>", prompt.text)
            if not re.search(rf"</{tag}>", prompt.text)
        ]
        self.record("no unpaired tag-like text that C003 would misparse", stray == [])

    def check_schema_contracts(self) -> None:
        # Confirms every schema name the new prose relies on exists and validates.
        diversity = self.critic.section("Diversity")
        rubric_names = set(SuggestionCritiqueRubric.model_fields)
        signal_names = set(SuggestionCritiqueSignals.model_fields)
        self.record(
            "critic names only rubric and signal fields that exist",
            {"suggestion_substance", "distinctness_non_redundancy"} <= rubric_names
            and "distinctness" in signal_names
            and "suggestion_substance" in diversity
            and "distinctness_non_redundancy" in diversity,
        )
        codes = re.findall(r"log a (\S+) issue at (\S+) severity", diversity)
        self.record(
            "the issue code and severity the critic is told to log are schema-valid",
            len(codes) == 1
            and re.fullmatch(r"^[a-z][a-z0-9_]*$", codes[0][0]) is not None
            and codes[0][1] in {level.value for level in CritiqueIssueSeverity},
        )
        self.record(
            "a keep critique carrying a slate_crowding note validates",
            self._crowded_critique_validates(),
        )
        self.record(
            "SuggestionDraft still has no probability field and forbids one",
            "probability" not in SuggestionDraft.model_fields
            and SuggestionDraft.model_config.get("extra") == "forbid",
        )

    def _crowded_critique_validates(self) -> bool:
        # Builds the exact artifact shape the Diversity section asks for and validates it.
        item = SuggestionCritiqueRubricItem(score=88, explanation="Shares the export-queue lever.")
        issue = SuggestionCritiqueIssue(
            code="slate_crowding",
            severity=CritiqueIssueSeverity.NOTE,
            explanation="Four of five candidates retry the same export queue.",
        )
        critique = SuggestionCritique(
            idea_id="idea-002",
            verdict=CritiqueVerdict.KEEP,
            confidence=CritiqueConfidence.HIGH,
            evidence_check=CritiqueEvidenceCheck.SUPPORTED,
            review_summary="Sound and next, though crowded with its siblings.",
            issues=(issue,),
            rubric=SuggestionCritiqueRubric(
                **{name: item for name in SuggestionCritiqueRubric.model_fields}
            ),
        )
        return critique.issues[0].code == "slate_crowding"

    def _source(self, prompt: PromptFile) -> SimpleNamespace:
        # Adapts a prompt to the minimal SourceFile surface the C003 analyzer reads.
        lines = prompt.text.splitlines()
        return SimpleNamespace(
            text=prompt.text,
            rel=f"prompts/{prompt.name}.md",
            line_at=lambda n: lines[n - 1] if 0 < n <= len(lines) else "",
        )


if __name__ == "__main__":
    raise SystemExit(DiversityPromptVerifier().run())
