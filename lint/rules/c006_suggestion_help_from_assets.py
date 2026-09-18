"""C006: every suggestion-agent help text is loaded from its own Markdown asset."""

from __future__ import annotations

import ast

from lint.core.diagnostic import Diagnostic, Finding
from lint.core.discovery import SourceCatalog, SourceFile
from lint.core.registry import Rule

_COMMAND_PREFIX = "src/vidbyte_cli/commands/agents/suggestion/"


class SuggestionHelpAssetAnalyzer:
    """Finds `help=` values in the suggestion command package that are not asset-loaded."""

    def analyze(self, catalog: SourceCatalog) -> list[Finding]:
        findings: list[Finding] = []
        for source in catalog.command_files():
            if not source.rel.startswith(_COMMAND_PREFIX) or source.tree is None:
                continue
            loaded = self._asset_constants(source.tree)
            for node in ast.walk(source.tree):
                if not isinstance(node, ast.Call):
                    continue
                for keyword in node.keywords:
                    if keyword.arg == "help" and not self._is_loaded(keyword.value, loaded):
                        findings.append(self._finding(source, node, keyword.value))
        return findings

    def _asset_constants(self, tree: ast.Module) -> frozenset[str]:
        # Module-level names bound directly to `<library>.load("<asset>")`.
        names: set[str] = set()
        for node in tree.body:
            target: ast.expr | None = None
            value: ast.expr | None = None
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target, value = node.targets[0], node.value
            elif isinstance(node, ast.AnnAssign):
                target, value = node.target, node.value
            if (
                isinstance(target, ast.Name)
                and isinstance(value, ast.Call)
                and isinstance(value.func, ast.Attribute)
                and value.func.attr == "load"
                and len(value.args) == 1
                and isinstance(value.args[0], ast.Constant)
                and isinstance(value.args[0].value, str)
            ):
                names.add(target.id)
        return frozenset(names)

    def _is_loaded(self, value: ast.expr, loaded: frozenset[str]) -> bool:
        # A conditional help picks between two assets, so both branches must be asset-loaded.
        if isinstance(value, ast.IfExp):
            return self._is_loaded(value.body, loaded) and self._is_loaded(value.orelse, loaded)
        return isinstance(value, ast.Name) and value.id in loaded

    def _finding(self, source: SourceFile, node: ast.Call, value: ast.expr) -> Finding:
        symbol = ast.unparse(value) if len(ast.unparse(value)) <= 60 else "inline help"
        return Finding(
            rule_id=SuggestionHelpFromAssetsRule.id,
            rel_path=source.rel,
            line=node.lineno,
            source_line=source.line_at(node.lineno),
            symbol=symbol,
        )


class SuggestionHelpFromAssetsRule(Rule):
    """Requires suggestion group, command, and option help to come from Markdown assets."""

    id = "C006"
    name = "suggestion-help-from-assets"
    severity = "blocking"
    summary = "Suggestion-agent help= values are module constants loaded from a Markdown asset."

    def check(self, catalog: SourceCatalog) -> list[Finding]:
        return SuggestionHelpAssetAnalyzer().analyze(catalog)

    def explain(self, finding: Finding) -> Diagnostic:
        return Diagnostic(
            what_happened=(
                f"`help={finding.symbol}` at {finding.rel_path}:{finding.line} is not a "
                "module-level constant bound to SuggestionHelpLibrary().load(...), so this "
                "suggestion-agent help text lives in Python instead of its own Markdown asset."
            ),
            why_blocked=(
                "Review on PR #84 asked, three times, for suggestion help to live in its own file "
                "and to follow the existing suggestion help assets for content and structure "
                "(comments 4050090959, 4050114470, 4050120530). Inline strings drift from the "
                "packaged assets, escape the depth rules that read those assets (C005), and are "
                "invisible to anyone editing the prompts/ folder. This covers group, command, "
                "flag, and numeric help too, which C005 does not."
            ),
            how_to_fix=(
                "Move the prose into "
                "src/vidbyte_cli/commands/agents/suggestion/prompts/<name>.md, bind it at module "
                'level with `_NAME_HELP = SuggestionHelpLibrary().load("<name>")` (or through a '
                "shared `_HELP = SuggestionHelpLibrary()`), pass `help=_NAME_HELP`, and add "
                "`<name>` to the wheel asset list in scripts/run_ci.py. A command whose help "
                "depends on a registration value may use `_A_HELP if flag else _B_HELP` when "
                "both names are asset-loaded."
            ),
            correct_examples=(
                "src/vidbyte_cli/commands/agents/suggestion/suggest.py",
                "src/vidbyte_cli/commands/agents/suggestion/suggestion_feedback.py",
            ),
            will_not_work=(
                "Assigning the inline string to a module constant: the rule accepts only names "
                "bound to a .load(...) call, because the asset file is the contract.",
                "Raising lint/baseline.json. The allowance only freezes help that predated this "
                "rule.",
            ),
            verify=self.verify_command(),
        )


RULE = SuggestionHelpFromAssetsRule()
