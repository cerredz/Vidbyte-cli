"""Parses suggest-run options, then invokes the validated suggestion service.

The command owns only argv shape and Click choices. Request and settings
validation complete before the service loads the provider or starts an agent.
"""

from __future__ import annotations

from pathlib import Path

import click

from ....lib.runtime.context import ApplicationContext as Context
from ....services.suggestions.categories import SuggestionCategories
from ....services.suggestions.service import SuggestionService
from .prompts.library import SuggestionHelpLibrary
from .render import SuggestionRenderer
from .request_builder import SuggestionRequestBuilder

_HELP = SuggestionHelpLibrary()
_COMMAND_HELP = _HELP.load("run")
_GOAL_HELP = _HELP.load("goal")
_CONTEXT_HELP = _HELP.load("context")
_FILES_HELP = _HELP.load("files")
_COMPLETED_HELP = _HELP.load("completed")
_IN_PROGRESS_HELP = _HELP.load("in_progress")
_DECISION_HELP = _HELP.load("decision")
_CONSTRAINT_HELP = _HELP.load("constraint")
_AVOID_HELP = _HELP.load("avoid")
_QUESTION_HELP = _HELP.load("question")
_CAPABILITY_HELP = _HELP.load("capability")
_SUCCESS_HELP = _HELP.load("success")
_COUNT_HELP = _HELP.load("count")
_CATEGORY_HELP = _HELP.load("category")
_ALL_CATEGORIES_HELP = _HELP.load("all_categories")
_HORIZON_HELP = _HELP.load("horizon")
_ROUNDS_HELP = _HELP.load("rounds")
_PROVIDER_HELP = _HELP.load("provider")
_CRITIC_MODEL_HELP = _HELP.load("critic_model")
_EXTRA_COMPUTE_HELP = _HELP.load("extra_compute")
_MAX_OUTPUT_TOKENS_HELP = _HELP.load("max_output_tokens")
_MAX_TOTAL_TOKENS_HELP = _HELP.load("max_total_tokens")
_TIMEOUT_HELP = _HELP.load("timeout")
_DRY_RUN_HELP = _HELP.load("dry_run")
_MISTAKES_HELP = _HELP.load("mistakes")
_FORBIDDEN_HELP = _HELP.load("forbidden")
_APPROACHES_HELP = _HELP.load("approaches")
_OUTCOMES_HELP = _HELP.load("outcomes")
_BLOCKERS_HELP = _HELP.load("blockers")
_HYPOTHESES_HELP = _HELP.load("hypotheses")
_RISKS_HELP = _HELP.load("risks")
_TRAJECTORY_HELP = _HELP.load("trajectory")


class SuggestRunCommand:
    """Validates run options ahead of any model call, then renders the result."""

    def register(self, parent: click.Group) -> None:
        # Attaches run with goal, context, generation, and budget controls.
        @parent.command(name="run", help=_COMMAND_HELP)
        @click.option("--goal", default=None, help=_GOAL_HELP)
        @click.option("--context", "context", multiple=True, help=_CONTEXT_HELP)
        @click.option(
            "--files",
            "files",
            multiple=True,
            type=click.Path(path_type=Path),
            help=_FILES_HELP,
        )
        @click.option("--completed", "completed", multiple=True, help=_COMPLETED_HELP)
        @click.option("--in-progress", "in_progress", multiple=True, help=_IN_PROGRESS_HELP)
        @click.option("--decision", "decision", multiple=True, help=_DECISION_HELP)
        @click.option("--constraint", "constraint", multiple=True, help=_CONSTRAINT_HELP)
        @click.option("--avoid", "avoid", multiple=True, help=_AVOID_HELP)
        @click.option("--mistakes", "mistakes", multiple=True, help=_MISTAKES_HELP)
        @click.option("--forbidden", "forbidden", multiple=True, help=_FORBIDDEN_HELP)
        @click.option("--approaches", "approaches", multiple=True, help=_APPROACHES_HELP)
        @click.option("--outcomes", "outcomes", multiple=True, help=_OUTCOMES_HELP)
        @click.option("--blockers", "blockers", multiple=True, help=_BLOCKERS_HELP)
        @click.option("--hypotheses", "hypotheses", multiple=True, help=_HYPOTHESES_HELP)
        @click.option("--risks", "risks", multiple=True, help=_RISKS_HELP)
        @click.option("--trajectory", "trajectory", multiple=True, help=_TRAJECTORY_HELP)
        @click.option("--question", "question", multiple=True, help=_QUESTION_HELP)
        @click.option("--capability", "capability", multiple=True, help=_CAPABILITY_HELP)
        @click.option("--success", "success", multiple=True, help=_SUCCESS_HELP)
        @click.option(
            "--count", type=click.IntRange(2, 15), default=5, show_default=True, help=_COUNT_HELP
        )
        @click.option(
            "--category",
            "categories",
            multiple=True,
            type=click.Choice(SuggestionCategories().ids()),
            help=_CATEGORY_HELP,
        )
        @click.option("--all-categories", is_flag=True, default=False, help=_ALL_CATEGORIES_HELP)
        @click.option(
            "--horizon",
            type=click.Choice(("now", "next", "later", "any")),
            default="any",
            show_default=True,
            help=_HORIZON_HELP,
        )
        @click.option(
            "--rounds", type=click.IntRange(1, 3), default=2, show_default=True, help=_ROUNDS_HELP
        )
        @click.option(
            "--provider",
            type=click.Choice(("openai",)),
            default=None,
            help=_PROVIDER_HELP,
        )
        @click.option("--critic-model", "critic_model", default=None, help=_CRITIC_MODEL_HELP)
        @click.option("--extra-compute", is_flag=True, default=False, help=_EXTRA_COMPUTE_HELP)
        @click.option(
            "--max-output-tokens",
            type=click.IntRange(1, 5000000),
            default=None,
            help=_MAX_OUTPUT_TOKENS_HELP,
        )
        @click.option(
            "--max-total-tokens",
            type=click.IntRange(1, 20000000),
            default=None,
            help=_MAX_TOTAL_TOKENS_HELP,
        )
        @click.option(
            "--timeout-seconds", type=click.IntRange(1, 86400), default=None, help=_TIMEOUT_HELP
        )
        @click.option("--dry-run", is_flag=True, default=False, help=_DRY_RUN_HELP)
        @click.pass_obj
        def _run(ctx: Context, /, **kwargs: object) -> None:
            # Delegates parsed values to the testable execution method.
            self.execute(ctx, kwargs)

    def execute(self, context: Context, raw: dict[str, object]) -> None:
        # Everything invalid fails here, before files are read or models run.
        request = SuggestionRequestBuilder().build(raw)
        result = SuggestionService().run(request)
        SuggestionRenderer().render_result(context, result)
