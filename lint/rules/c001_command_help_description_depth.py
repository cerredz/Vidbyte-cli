"""C001: every command and option a caller sees must document itself in real depth.

Detection is entirely static: `help=` strings are resolved through literals, implicit and
explicit concatenation, f-string skeletons, and module-level constants in the same file. A
string this rule cannot resolve is exempted rather than reported, because a false positive
here would teach the next agent to ignore the suite.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog, SourceFile
from lint.core.registry import Rule

MINIMUM_SENTENCES = 4
MINIMUM_AVERAGE_WORDS = 8
_ABBREVIATIONS = ("e.g.", "i.e.", "etc.", "vs.", "approx.", "cf.")
_COMMAND_CALLEES = ("command", "group")
_OPTION_CALLEE = "option"
_ARGUMENT_CALLEE = "argument"


@dataclass(frozen=True, slots=True)
class HelpSite:
    """One resolved `help=` string with the call site it was written at."""

    line: int
    symbol: str
    kind: str
    text: str | None


class HelpTextResolver:
    """Resolves a `help=` expression to its final text when that is statically provable."""

    def __init__(self, source: SourceFile) -> None:
        # Binds resolution to one module, since only same-file constants are followed.
        self._source = source
        self._constants = self._module_constants()

    def resolve(self, expr: ast.expr, depth: int = 0) -> str | None:
        # Dispatches on node shape and returns None whenever the value is not provable.
        if depth > 3:
            return None
        if isinstance(expr, ast.Constant):
            return expr.value if isinstance(expr.value, str) else None
        if isinstance(expr, ast.JoinedStr):
            return self._resolve_joined(expr, depth)
        if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.Add):
            left = self.resolve(expr.left, depth + 1)
            right = self.resolve(expr.right, depth + 1)
            return None if left is None or right is None else left + right
        if isinstance(expr, ast.Name):
            assigned = self._constants.get(expr.id)
            return None if assigned is None else self.resolve(assigned, depth + 1)
        return None

    def _resolve_joined(self, expr: ast.JoinedStr, depth: int) -> str | None:
        # Keeps literal segments and stands a neutral token in for each interpolation.
        parts: list[str] = []
        for value in expr.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
            elif isinstance(value, ast.FormattedValue):
                parts.append("value")
            else:
                return None
        return "".join(parts)

    def _module_constants(self) -> dict[str, ast.expr]:
        # Indexes module-level string assignments so a named help constant resolves.
        found: dict[str, ast.expr] = {}
        if self._source.tree is None:
            return found
        for node in self._source.tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = node.targets[0]
                if isinstance(target, ast.Name):
                    found[target.id] = node.value
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                if node.value is not None:
                    found[node.target.id] = node.value
        return found


class CommandHelpDepthAnalyzer:
    """Finds every click command, option, and argument, and measures its help text."""

    def analyze(self, catalog: SourceCatalog) -> list[Finding]:
        # Walks each command module once; a module that does not parse is reported as such.
        findings: list[Finding] = []
        for source in catalog.command_files():
            if source.tree is None:
                findings.append(self._parse_error(source))
                continue
            findings.extend(self._analyze_module(source))
        return findings

    def _analyze_module(self, source: SourceFile) -> list[Finding]:
        # Commands and options are judged on their own text; arguments on their command's.
        resolver = HelpTextResolver(source)
        sites = self._help_sites(source, resolver)
        findings = [
            self._finding(source, site)
            for site in sites
            if site.kind in {"command", "option"} and not self._is_deep(site.text)
        ]
        commands = " ".join(site.text or "" for site in sites if site.kind == "command").lower()
        findings.extend(
            self._finding(source, site)
            for site in sites
            if site.kind == "argument" and commands and site.symbol.lower() not in commands
        )
        return findings

    def _help_sites(self, source: SourceFile, resolver: HelpTextResolver) -> list[HelpSite]:
        # Matches by callee name, so decorator and functional `click.option(...)(cb)` both count.
        sites: list[HelpSite] = []
        assert source.tree is not None
        for node in ast.walk(source.tree):
            if not isinstance(node, ast.Call):
                continue
            callee = self._callee_name(node)
            if callee in _COMMAND_CALLEES:
                name = self._string_argument(node, "name", 0, resolver) or "<command>"
                sites.append(self._site(node, name, "command", resolver))
            elif callee == _OPTION_CALLEE:
                name = self._first_flag(node) or "<option>"
                sites.append(self._site(node, name, "option", resolver))
            elif callee == _ARGUMENT_CALLEE:
                name = self._string_argument(node, "", 0, resolver) or "<argument>"
                # Click has no `help=` for arguments, so the command's own help must name it.
                sites.append(HelpSite(line=node.lineno, symbol=name, kind="argument", text=None))
        return sites

    def _site(self, node: ast.Call, symbol: str, kind: str, resolver: HelpTextResolver) -> HelpSite:
        # Reads and resolves the `help=` keyword; an absent one is depth zero, not exempt.
        expr = next((kw.value for kw in node.keywords if kw.arg == "help"), None)
        text = "" if expr is None else resolver.resolve(expr)
        return HelpSite(line=node.lineno, symbol=symbol, kind=kind, text=text)

    def _is_deep(self, text: str | None) -> bool:
        # None means unresolvable, which is exempted; "" means the help is genuinely absent.
        if text is None:
            return True
        sentences = self._sentences(text)
        if len(sentences) < MINIMUM_SENTENCES:
            return False
        words = sum(len(sentence.split()) for sentence in sentences)
        return words / len(sentences) >= MINIMUM_AVERAGE_WORDS

    def _sentences(self, text: str) -> list[str]:
        # Splits on terminal punctuation that ends a word, skipping known abbreviations.
        stripped = text.strip()
        if not stripped:
            return []
        sentences: list[str] = []
        start = 0
        for index, char in enumerate(stripped):
            if char in ".!?" and self._is_terminal(stripped, index):
                sentences.append(stripped[start : index + 1])
                start = index + 1
        remainder = stripped[start:].strip()
        if remainder:
            sentences.append(remainder)
        return sentences

    def _is_terminal(self, text: str, index: int) -> bool:
        # A real boundary is followed by whitespace or nothing and is not an abbreviation.
        if index + 1 < len(text) and not text[index + 1].isspace():
            return False
        return not any(
            text[: index + 1].lower().endswith(abbreviation) for abbreviation in _ABBREVIATIONS
        )

    def _first_flag(self, node: ast.Call) -> str | None:
        # An option's identity is its first declared flag, e.g. `--window`.
        for argument in node.args:
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                return argument.value
        return None

    def _string_argument(
        self, node: ast.Call, keyword: str, position: int, resolver: HelpTextResolver
    ) -> str | None:
        # Reads one identifying string from a keyword, else from a positional slot.
        for kw in node.keywords:
            if keyword and kw.arg == keyword:
                return resolver.resolve(kw.value)
        if len(node.args) > position:
            return resolver.resolve(node.args[position])
        return None

    def _callee_name(self, node: ast.Call) -> str:
        # Reads a bare or attribute callee name, so `parent.command` and `command` both match.
        if isinstance(node.func, ast.Name):
            return node.func.id
        if isinstance(node.func, ast.Attribute):
            return node.func.attr
        return ""

    def _parse_error(self, source: SourceFile) -> Finding:
        # A command module that will not parse is a finding, never a silent zero.
        return Finding(
            rule_id=CommandHelpDescriptionDepthRule.id,
            rel_path=source.rel,
            line=1,
            source_line="",
            symbol="<unparsed>",
            extra={"kind": "parse-error", "detail": source.parse_error or "unknown"},
        )

    def _finding(self, source: SourceFile, site: HelpSite) -> Finding:
        # Records the exact call site plus the measured depth for the diagnostic to quote.
        sentences = 0 if site.text is None else len(self._sentences(site.text))
        return Finding(
            rule_id=CommandHelpDescriptionDepthRule.id,
            rel_path=source.rel,
            line=site.line,
            source_line=source.line_at(site.line),
            symbol=site.symbol,
            extra={"kind": site.kind, "sentence_count": str(sentences)},
        )


class CommandHelpDescriptionDepthRule(Rule):
    """Requires at least four substantial sentences of help on every command and option."""

    id = "C001"
    name = "command-help-description-depth"
    severity = "blocking"
    summary = "Every command and option carries 4+ in-depth sentences of help; arguments are named."

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        # Detection lives in the analyzer so this class stays the policy statement.
        return CommandHelpDepthAnalyzer().analyze(catalog)

    def explain(self, finding: Finding) -> Diagnostic:
        # Each kind fails for a different reason, so each gets its own repair instruction.
        kind = finding.extra.get("kind", "option")
        if kind == "parse-error":
            return self._parse_error_diagnostic(finding)
        if kind == "argument":
            return self._argument_diagnostic(finding)
        return self._help_text_diagnostic(finding, kind)

    def _help_text_diagnostic(self, finding: Finding, kind: str) -> Diagnostic:
        # Names the symbol, the measured sentence count, and the exact bar it has to clear.
        count = finding.extra.get("sentence_count", "0")
        subject = "command" if kind == "command" else "option"
        return Diagnostic(
            what_happened=(
                f"The {subject} {finding.symbol} at {finding.rel_path}:{finding.line} has a "
                f"help description of only {count} resolvable sentence(s). This rule requires "
                f"at least {MINIMUM_SENTENCES} full sentences averaging at least "
                f"{MINIMUM_AVERAGE_WORDS} words each."
            ),
            why_blocked=(
                "This help text is the entire specification a caller gets for this "
                f"{subject}. The heaviest callers of this CLI are agents: they read `--help` "
                "once, choose flags from it, and have no transcript, no docs site, and no "
                "person to ask when the wording under-specifies what a flag does. A one-line "
                "label tells a caller a flag exists without telling it what value to pass, "
                "when the flag matters, what it interacts with, or what it costs — so the "
                "flag gets guessed at, misused, or skipped, and the failure surfaces as a "
                "wrong result rather than a usage error. Review of PR #35 asked for this "
                "explicitly and asked for it as a rule rather than a one-file correction."
            ),
            how_to_fix=(
                f"Rewrite the help string as at least {MINIMUM_SENTENCES} full sentences that "
                "answer, in order: what this accepts or does; what the default behavior is "
                "and why it is the default; when a caller should change it; and what it "
                "interacts with, overrides, or costs. Write it as prose addressed to the "
                "caller, in complete sentences with real subjects and verbs. When the string "
                "gets long, lift it to a module-level `_<NAME>_HELP` constant above the class "
                "and pass `help=_<NAME>_HELP` — this rule resolves same-file constants, "
                "implicit concatenation, and `+` concatenation, so none of those hide it."
            ),
            correct_examples=(
                "src/vidbyte_cli/commands/runtime/task_board.py - every option's help lives in "
                "a module-level `_..._HELP` constant written as four to seven sentences.",
                "src/vidbyte_cli/types/runtime.py - the matching `TaskBoardSettings` field "
                "descriptions, which say the same things to the model-facing layer.",
            ),
            will_not_work=(
                "Padding with filler or repeated clauses to reach four sentences: short "
                "fragments fail the average-words check, and a reader gains nothing.",
                "Moving the depth into the function's docstring or a `#` comment. Click sends "
                "the `help=` string to the caller and nothing else.",
                "Building the string from a runtime call so this rule cannot resolve it. The "
                "caller still receives only what that call returns.",
                "Raising this rule's number in lint/baseline.json. The allowance covers help "
                "text that predates the gate, never a command or option changed since.",
            ),
            verify=self.verify_command(),
        )

    def _argument_diagnostic(self, finding: Finding) -> Diagnostic:
        # Click accepts no help= on an argument, so the command's own help is the only place.
        return Diagnostic(
            what_happened=(
                f"The positional argument {finding.symbol!r} at {finding.rel_path}:"
                f"{finding.line} is never named in its command's own help text."
            ),
            why_blocked=(
                "Click provides no `help=` parameter for a positional argument, so the only "
                "place a caller can learn what an argument means is the command's help. An "
                "argument that appears in the usage line and nowhere in the prose leaves a "
                "caller guessing at its meaning, its format, and whether it repeats. Agent "
                "callers guess wrong and then pass a plausible-looking value the command "
                "accepts and misinterprets."
            ),
            how_to_fix=(
                f"Extend the enclosing command's `help=` text so it names {finding.symbol!r} "
                "and says what one value is, whether the argument repeats, what order means "
                "if it does, and how it relates to the options that can replace it. Naming "
                "the argument is the mechanical part of this check; the surrounding sentences "
                "are what actually make it usable."
            ),
            correct_examples=(
                "src/vidbyte_cli/commands/runtime/task_board.py - `_COMMAND_HELP` names TASKS, "
                "says each argument is one whole task, and explains what board order means.",
            ),
            will_not_work=(
                "Documenting the argument only in README.md or a design doc; `--help` is what "
                "the caller reads at invocation time.",
                "Renaming the argument to something the existing help happens to contain.",
            ),
            verify=self.verify_command(),
        )

    def _parse_error_diagnostic(self, finding: Finding) -> Diagnostic:
        # A detector that cannot read a module must say so instead of reporting a clean pass.
        return Diagnostic(
            what_happened=(
                f"{finding.rel_path} is registered as a command module but does not parse: "
                f"{finding.extra.get('detail', 'unknown')}."
            ),
            why_blocked=(
                "An unparsed module is analyzed as zero commands and zero options, which is "
                "indistinguishable from a module that fully complies. This rule fails closed "
                "rather than reporting a clean pass it cannot support."
            ),
            how_to_fix="Fix the syntax error, then re-run this rule.",
            will_not_work=("Baselining this finding; the count would hide every rule below it.",),
            verify=self.verify_command(),
        )


RULE = CommandHelpDescriptionDepthRule()
