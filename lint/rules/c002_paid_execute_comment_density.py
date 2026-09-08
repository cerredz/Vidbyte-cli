"""C002: the method that buys an admission must explain itself line by line.

A paid command method is found structurally: it is the function that calls an `admit_*`
endpoint method. Comments are counted as blocks, so a two-line comment counts once and a
run of consecutive `#` lines counts once, and they are read from the tokenizer rather than
from raw text so a `#` inside a string is never mistaken for a comment.
"""

from __future__ import annotations

import ast
import io
import tokenize
from dataclasses import dataclass

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog, SourceFile
from lint.core.registry import Rule

MINIMUM_COMMENT_BLOCKS = 10
_ADMISSION_PREFIX = "admit_"


@dataclass(frozen=True, slots=True)
class PaidMethod:
    """One method that purchases an admission, with the comment blocks inside it."""

    line: int
    symbol: str
    blocks: int


class CommentBlockIndex:
    """Maps a module to the first line of every run of consecutive comment lines."""

    def __init__(self, source: SourceFile) -> None:
        # Tokenizing once per module keeps every method lookup a set intersection.
        self._starts = self._block_starts(source)

    def blocks_within(self, start: int, end: int) -> int:
        # Counts comment blocks whose first line falls inside the method's own span.
        return sum(1 for line in self._starts if start <= line <= end)

    def _block_starts(self, source: SourceFile) -> tuple[int, ...]:
        # A comment line that directly follows another comment line continues its block.
        lines: list[int] = []
        try:
            tokens = tokenize.generate_tokens(io.StringIO(source.text).readline)
            for token in tokens:
                if token.type == tokenize.COMMENT:
                    lines.append(token.start[0])
        except (tokenize.TokenError, IndentationError, SyntaxError):
            return ()
        seen = set(lines)
        return tuple(line for line in lines if line - 1 not in seen)


class PaidExecuteAnalyzer:
    """Finds every admission-purchasing method and measures its comment density."""

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
        # Only the method that actually buys the admission is judged, not its callers.
        index = CommentBlockIndex(source)
        assert source.tree is not None
        methods = [
            self._measure(node, index)
            for node in ast.walk(source.tree)
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and self._is_paid(node)
        ]
        return [
            self._finding(source, method)
            for method in methods
            if method.blocks < MINIMUM_COMMENT_BLOCKS
        ]

    def _is_paid(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
        # A paid method is the one that calls an `admit_*` endpoint method directly.
        for inner in ast.walk(node):
            if not isinstance(inner, ast.Call):
                continue
            callee = inner.func
            if isinstance(callee, ast.Attribute) and callee.attr.startswith(_ADMISSION_PREFIX):
                return True
        return False

    def _measure(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef, index: CommentBlockIndex
    ) -> PaidMethod:
        # The span starts at the signature so a leading intent comment still counts.
        end = node.end_lineno or node.lineno
        return PaidMethod(
            line=node.lineno,
            symbol=node.name,
            blocks=index.blocks_within(node.lineno, end),
        )

    def _finding(self, source: SourceFile, method: PaidMethod) -> Finding:
        # Records the measured density so the diagnostic can quote the exact shortfall.
        return Finding(
            rule_id=PaidExecuteCommentDensityRule.id,
            rel_path=source.rel,
            line=method.line,
            source_line=source.line_at(method.line),
            symbol=method.symbol,
            extra={"kind": "density", "comment_blocks": str(method.blocks)},
        )

    def _parse_error(self, source: SourceFile) -> Finding:
        # A command module that will not parse is a finding, never a silent zero.
        return Finding(
            rule_id=PaidExecuteCommentDensityRule.id,
            rel_path=source.rel,
            line=1,
            source_line="",
            symbol="<unparsed>",
            extra={"kind": "parse-error", "detail": source.parse_error or "unknown"},
        )


class PaidExecuteCommentDensityRule(Rule):
    """Requires ten commented steps in the method that purchases a paid admission."""

    id = "C002"
    name = "paid-execute-comment-density"
    severity = "blocking"
    summary = "The method that calls an admit_* endpoint carries 10+ comment blocks."

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        # Detection lives in the analyzer so this class stays the policy statement.
        return PaidExecuteAnalyzer().analyze(catalog)

    def explain(self, finding: Finding) -> Diagnostic:
        # A module that will not parse fails for a different reason than a thin method.
        if finding.extra.get("kind") == "parse-error":
            return self._parse_error_diagnostic(finding)
        return self._density_diagnostic(finding)

    def _density_diagnostic(self, finding: Finding) -> Diagnostic:
        # Names the method, its measured density, and the exact bar it has to clear.
        blocks = finding.extra.get("comment_blocks", "0")
        return Diagnostic(
            what_happened=(
                f"The method {finding.symbol} at {finding.rel_path}:{finding.line} purchases a "
                f"paid admission but carries only {blocks} comment block(s). This rule requires "
                f"at least {MINIMUM_COMMENT_BLOCKS}."
            ),
            why_blocked=(
                "This is the one method in the repository where a mistake spends a user's "
                "money. Its steps are ordered for a reason that the code itself does not "
                "state: everything a caller can get wrong is validated while the run is still "
                "free, the wallet is charged exactly once, the grant is re-read from the "
                "backend rather than trusted as returned, and no agent starts until that "
                "verdict is in hand. An agent editing this method later sees a sequence of "
                "calls with no record of which ordering constraints are load-bearing, moves a "
                "validation below the admission or drops the re-verification, and the failure "
                "is a charged wallet rather than a test failure. Review of PR #36 asked for "
                "this density explicitly, and asked for it as a rule rather than one fix."
            ),
            how_to_fix=(
                "Write one comment above each meaningful step of the method saying why that "
                "step is where it is, not what the next line does. The steps worth naming are: "
                "why everything before admission is free; why the idempotency key is validated "
                "first; what each local validation fails closed on; why the plan carries no "
                "caller content to the backend; why building the session must precede payment; "
                "what the one admission actually buys; why the grant is verified again; what "
                "binds that verification to this invocation; why the executor receives a "
                "verdict and no endpoints; and why only the result reaches stdout. A two-line "
                "comment counts once, so splitting one comment across lines does not help."
            ),
            correct_examples=(
                "src/vidbyte_cli/commands/runtime/stages.py - execute_run comments each ordered "
                "step of the free-then-admit-then-verify-then-run sequence.",
            ),
            will_not_work=(
                "Restating the next line in English. A comment that says what the call does "
                "adds a line and no information; say why the step sits where it sits.",
                "Moving the explanation into the method's docstring or the module header. "
                "Neither sits next to the step whose ordering an editor is about to change.",
                "Splitting one comment across several lines to raise the count. Consecutive "
                "comment lines are one block.",
                "Raising this rule's number in lint/baseline.json. The allowance covers paid "
                "methods that predate the gate, never one changed since.",
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
                "An unparsed module is analyzed as zero paid methods, which is "
                "indistinguishable from a module that fully complies. This rule fails closed "
                "rather than reporting a clean pass it cannot support."
            ),
            how_to_fix="Fix the syntax error, then re-run this rule.",
            will_not_work=("Baselining this finding; the count would hide every rule below it.",),
            verify=self.verify_command(),
        )


RULE = PaidExecuteCommentDensityRule()
