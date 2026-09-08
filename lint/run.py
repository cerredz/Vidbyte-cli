"""The lint suite's only entry point: `python lint/run.py`, optionally scoped to one rule.

Exit 0 means every selected rule is CLEAN, RATCHETED, or IMPROVED. REGRESSED and ERRORED
fail, as does a baseline that disagrees with the registered catalogue. `--update-baseline`
records current counts and is never run before the new findings have been read.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lint.core.baseline import BaselineContractError
from lint.core.registry import RuleRegistry, RuleSelectionError
from lint.core.report import RunReport
from lint.core.runner import RuleResult, RuleRunner


class ArgumentParserFactory:
    """Builds the stable lint CLI without mixing parsing into execution."""

    @staticmethod
    def build() -> argparse.ArgumentParser:
        # Selection, output shape, expansion, and baseline maintenance — nothing else.
        parser = argparse.ArgumentParser(description="Run the Vidbyte CLI lint suite.")
        parser.add_argument("--rule", help="Run one rule ID, for example C001.")
        parser.add_argument("--format", choices=("text", "json"), default="text")
        parser.add_argument("--all", action="store_true", help="Render every known finding.")
        parser.add_argument(
            "--update-baseline",
            action="store_true",
            help="Record current counts after reviewing the findings.",
        )
        return parser


class LintApplication:
    """Coordinates selection, execution, baseline maintenance, and rendering."""

    def run(self, argv: list[str] | None = None) -> int:
        # Executes one complete request and returns its process status.
        args = ArgumentParserFactory.build().parse_args(argv)
        try:
            registry = RuleRegistry()
            rules = registry.select(args.rule)
            runner = RuleRunner(
                rules,
                {rule.id for rule in registry.all()},
                validate_baseline=not args.update_baseline,
            )
            results = runner.run()
        except (BaselineContractError, RuleSelectionError) as error:
            sys.stderr.write(f"CLI lint setup failed: {error}\n")
            return 2
        if args.update_baseline:
            return self._update(runner, results)
        report = RunReport(results, truncate=20, expand_all=args.all)
        print(report.render_json() if args.format == "json" else report.render_text())
        return report.exit_code()

    def _update(self, runner: RuleRunner, results: tuple[RuleResult, ...]) -> int:
        # Merges the selected rules' counts into the stored catalogue, leaving others alone.
        counts = runner.counts(results)
        stored = runner.store.load()
        stored.update(counts)
        runner.store.write(stored)
        print(f"Updated lint/baseline.json for {', '.join(sorted(counts))}.")
        return 0


def main(argv: list[str] | None = None) -> int:
    # Bridges the class-bound application to the `python lint/run.py` invocation.
    return LintApplication().run(argv)


if __name__ == "__main__":
    raise SystemExit(main())
