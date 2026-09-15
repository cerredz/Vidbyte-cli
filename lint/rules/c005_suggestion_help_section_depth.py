"""C005: dynamic suggestion inputs carry a complete caller-facing specification."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog, SourceFile
from lint.core.registry import Rule

MINIMUM_SENTENCES = 6
MAXIMUM_SENTENCES = 8
MINIMUM_WORDS = 100
_COMMAND_PREFIX = "src/vidbyte_cli/commands/agents/suggestion/"
_PROMPT_PREFIX = f"{_COMMAND_PREFIX}prompts/"
_REQUIRED_PREFIXES = (
    "purpose of ",
    "when not to use ",
    "inputs",
    "defaults and precedence",
    "output contract",
    "how to use",
    "examples",
    "related commands",
    "failure modes",
    "authentication and permissions",
)
_GENERIC_TITLES = frozenset({"title", "description", "why it matters", "influence on output"})
_HEADING = re.compile(r"^\*\*(?P<title>[^*]+)\*\*$")
_SENTENCE_END = re.compile(r"[.!?](?=\s|$)")
_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9'_-]*")


@dataclass(frozen=True, slots=True)
class _HelpSection:
    """One named help heading and the prose beneath it."""

    title: str
    line: int
    body: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _DynamicOption:
    """One dynamic Click option and the Markdown asset named by its help constant."""

    line: int
    option: str
    asset: str | None


class SuggestionHelpSectionAnalyzer:
    """Checks Markdown assets used by dynamic suggestion option help."""

    def analyze(self, catalog: SourceCatalog) -> list[Finding]:
        markdown = {
            source.rel.rsplit("/", 1)[-1].removesuffix(".md"): source
            for source in catalog.markdown_files()
            if source.rel.startswith(_PROMPT_PREFIX)
        }
        findings: list[Finding] = []
        for source in catalog.command_files():
            if not source.rel.startswith(_COMMAND_PREFIX) or source.tree is None:
                continue
            constants = self._help_assets(source)
            for option in self._dynamic_options(source, constants):
                if option.asset is None:
                    findings.append(
                        self._finding(
                            source,
                            option.line,
                            option.option,
                            "help must load a Markdown asset",
                        )
                    )
                    continue
                prompt = markdown.get(option.asset)
                if prompt is None:
                    findings.append(
                        self._finding(
                            source,
                            option.line,
                            option.option,
                            f"missing Markdown asset {option.asset}.md",
                        )
                    )
                    continue
                findings.extend(self._check_asset(prompt))
        return findings

    def _help_assets(self, source: SourceFile) -> dict[str, str]:
        found: dict[str, str] = {}
        if source.tree is None:
            return found
        for node in source.tree.body:
            assignment: ast.expr | None = None
            target: ast.expr | None = None
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target, assignment = node.targets[0], node.value
            elif isinstance(node, ast.AnnAssign):
                target, assignment = node.target, node.value
            if not isinstance(target, ast.Name) or not isinstance(assignment, ast.Call):
                continue
            if not isinstance(assignment.func, ast.Attribute) or assignment.func.attr != "load":
                continue
            if len(assignment.args) == 1 and isinstance(assignment.args[0], ast.Constant):
                name = assignment.args[0].value
                if isinstance(name, str):
                    found[target.id] = name
        return found

    def _dynamic_options(
        self, source: SourceFile, constants: dict[str, str]
    ) -> tuple[_DynamicOption, ...]:
        assert source.tree is not None
        found: list[_DynamicOption] = []
        for node in ast.walk(source.tree):
            if not isinstance(node, ast.Call) or self._callee(node) != "option":
                continue
            if not self._is_dynamic_string(node):
                continue
            option = self._first_flag(node)
            if option is None:
                continue
            help_expr = next(
                (keyword.value for keyword in node.keywords if keyword.arg == "help"),
                None,
            )
            asset = constants.get(help_expr.id) if isinstance(help_expr, ast.Name) else None
            found.append(_DynamicOption(node.lineno, option, asset))
        return tuple(found)

    def _is_dynamic_string(self, node: ast.Call) -> bool:
        is_flag = next(
            (keyword.value for keyword in node.keywords if keyword.arg == "is_flag"), None
        )
        if isinstance(is_flag, ast.Constant) and is_flag.value is True:
            return False
        type_expr = next(
            (keyword.value for keyword in node.keywords if keyword.arg == "type"), None
        )
        if type_expr is None:
            return True
        return (
            isinstance(type_expr, ast.Call)
            and isinstance(type_expr.func, ast.Attribute)
            and type_expr.func.attr == "Path"
        )

    def _check_asset(self, source: SourceFile) -> list[Finding]:
        sections = self._sections(source)
        findings: list[Finding] = []
        if not sections or sections[0].title.lower() in _GENERIC_TITLES:
            findings.append(
                self._finding(source, 1, "title", "the first heading must name the input")
            )
        for prefix in _REQUIRED_PREFIXES:
            section = next(
                (
                    item
                    for item in sections
                    if item.title.lower().startswith(prefix) or f" {prefix}" in item.title.lower()
                ),
                None,
            )
            if section is None:
                findings.append(self._finding(source, 1, prefix.rstrip(), "missing section"))
                continue
            prose = self._prose(section.body)
            sentences = len(_SENTENCE_END.findall(prose))
            words = len(_WORD.findall(prose))
            if not MINIMUM_SENTENCES <= sentences <= MAXIMUM_SENTENCES:
                findings.append(
                    self._finding(source, section.line, section.title, f"sentences={sentences}")
                )
            elif words < MINIMUM_WORDS:
                findings.append(
                    self._finding(source, section.line, section.title, f"words={words}")
                )
        return findings

    def _sections(self, source: SourceFile) -> tuple[_HelpSection, ...]:
        lines = source.text.splitlines()
        headings = [
            (index, match.group("title").strip())
            for index, line in enumerate(lines)
            if (match := _HEADING.match(line.strip()))
        ]
        return tuple(
            _HelpSection(
                title=title,
                line=start + 1,
                body=tuple(
                    lines[
                        start + 1 : headings[position + 1][0]
                        if position + 1 < len(headings)
                        else len(lines)
                    ]
                ),
            )
            for position, (start, title) in enumerate(headings)
        )

    def _prose(self, body: tuple[str, ...]) -> str:
        prose: list[str] = []
        fenced = False
        fence = chr(96) * 3
        for line in body:
            if line.strip().startswith(fence):
                fenced = not fenced
            elif not fenced:
                prose.append(line)
        return " ".join(prose)

    def _first_flag(self, node: ast.Call) -> str | None:
        for argument in node.args:
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                return argument.value
        return None

    def _callee(self, node: ast.Call) -> str:
        if isinstance(node.func, ast.Name):
            return node.func.id
        if isinstance(node.func, ast.Attribute):
            return node.func.attr
        return ""

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
    """Requires complete, named, deep help for dynamic suggestion inputs only."""

    id = "C005"
    name = "suggestion-help-section-depth"
    severity = "blocking"
    summary = "Dynamic suggestion string and path inputs use named, 6-8 sentence help sections."

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        return SuggestionHelpSectionAnalyzer().analyze(catalog)

    def explain(self, finding: Finding) -> Diagnostic:
        observed = str(finding.extra.get("observed", "invalid"))
        return Diagnostic(
            what_happened=(
                f"Dynamic suggestion input {finding.symbol} at {finding.rel_path}:{finding.line} "
                f"does not meet the long-form help contract: {observed}."
            ),
            why_blocked=(
                "Agents choose dynamic text and path values from the help available at "
                "invocation time. "
                "Review comments 4019257315 and 4019262921 asked every such help description to "
                "explain purpose, boundaries, inputs, defaults, output, examples, related "
                "commands, "
                "failures, and authentication in coherent depth. Comment 4019272940 narrowed this "
                "rule to values the agent supplies as dynamic strings, so numeric, enum, float, "
                "list, "
                "and flag options remain governed by their ordinary concise option help."
            ),
            how_to_fix=(
                "Load the option help from a Markdown asset whose first bold heading names the "
                "input. "
                "Add bold named sections for Purpose, When not to use, Inputs, Defaults and "
                "precedence, "
                "Output contract, How to use, Examples, Related commands, Failure modes, and "
                "Authentication and permissions. Give every section six to eight complete "
                "sentences "
                "and "
                "at least 100 words, then put a concrete command under How to use with "
                "brace-delimited placeholders such as {value}. Keep caller help out of model "
                "context."
            ),
            correct_examples=(
                "src/vidbyte_cli/commands/agents/suggestion/prompts/approaches.md",
                "src/vidbyte_cli/commands/agents/suggestion/prompts/files.md",
            ),
            will_not_work=(
                "Renaming a generic heading, padding with fragments, or counting a fenced command "
                "as "
                "prose. Those moves satisfy appearance without giving an agent an actionable "
                "specification.",
                "Moving the text into a Python constant or raising lint/baseline.json. The "
                "Markdown "
                "is the caller-facing contract, and the baseline only freezes pre-existing debt.",
            ),
            verify=self.verify_command(),
        )


RULE = SuggestionHelpSectionDepthRule()
