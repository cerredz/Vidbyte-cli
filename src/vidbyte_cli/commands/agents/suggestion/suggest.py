"""Parses suggest-run options, then invokes the validated suggestion service.

The command owns only argv shape and Click choices. Request and settings
validation complete before the service loads the provider or starts an agent.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from pathlib import Path
from typing import Final
from uuid import uuid4

import click

from ....lib.constants.runtime import SuggestionAdmissionLimit
from ....lib.constants.runtime import SuggestionAdmissionProgress as Progress
from ....lib.errors.failures import RuntimeAdmissionNotVerified
from ....lib.runtime.context import ApplicationContext as Context
from ....lib.runtime_primitives.gate import RuntimeAdmissionGate
from ....services.suggestions.categories import SuggestionCategories
from ....services.suggestions.sdk import SuggestionSdk
from ....services.suggestions.service import SuggestionService
from ....types.runtime import RuntimeGrantVerificationRequest as VerifyRequest
from ....types.runtime import RuntimeHost as Host
from ....types.runtime import RuntimeSuggestionAdmissionRequest as AdmitRequest
from ....types.suggestions import SuggestionAdmissionReceipt, SuggestionRequest
from ...agent_options import AgentAttachmentOptions
from .prompts.library import SuggestionHelpLibrary
from .render import SuggestionRenderer
from .request_builder import SuggestionRequestBuilder

_HELP = SuggestionHelpLibrary()
_COMMAND_HELP = _HELP.load("run")
_GOAL_HELP = _HELP.load("goal")
_PROJECT_HELP = _HELP.load("project")
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
_MAX_MESSAGES_HELP = _HELP.load("max_messages")
_PROVIDER_HELP = _HELP.load("provider")
_CRITIC_MODEL_HELP = _HELP.load("critic_model")
_EXTRA_COMPUTE_HELP = _HELP.load("extra_compute")
_MAX_OUTPUT_TOKENS_HELP = _HELP.load("max_output_tokens")
_MAX_TOTAL_TOKENS_HELP = _HELP.load("max_total_tokens")
_TIMEOUT_HELP = _HELP.load("timeout")
_DRY_RUN_HELP = _HELP.load("dry_run")
_IDEMPOTENCY_KEY_HELP = _HELP.load("idempotency_key")
_MISTAKES_HELP = _HELP.load("mistakes")
_FORBIDDEN_HELP = _HELP.load("forbidden")
_APPROACHES_HELP = _HELP.load("approaches")
_OUTCOMES_HELP = _HELP.load("outcomes")
_BLOCKERS_HELP = _HELP.load("blockers")
_HYPOTHESES_HELP = _HELP.load("hypotheses")
_RISKS_HELP = _HELP.load("risks")
_TRAJECTORY_HELP = _HELP.load("trajectory")
_ATTACHMENT_OPTIONS = AgentAttachmentOptions()
_KEY_PATTERN = r"[A-Za-z0-9._:-]{8,128}"
_CAPABILITY: Final = "runtime.suggestion@1"


class SuggestRunCommand:
    """Validates run options ahead of any model call, then renders the result."""

    def __init__(self, sdk_loader: Callable[[], SuggestionSdk] = SuggestionSdk.load) -> None:
        # The loader is injectable so offline checks can prove the SDK loads before payment.
        self._sdk_loader = sdk_loader

    def register(self, parent: click.Group) -> None:
        # Attaches run with goal, context, generation, and budget controls.
        @parent.command(name="run", help=_COMMAND_HELP)
        @click.option("--goal", default=None, help=_GOAL_HELP)
        @click.option("--project", default=None, help=_PROJECT_HELP)
        @click.option("--context", "context", multiple=True, help=_CONTEXT_HELP)
        @click.option(
            "--files",
            "files",
            multiple=True,
            type=click.Path(path_type=Path),
            help=_FILES_HELP,
        )
        @_ATTACHMENT_OPTIONS.apply
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
            "--rounds", type=click.IntRange(1, 8), default=2, show_default=True, help=_ROUNDS_HELP
        )
        @click.option(
            "--max-messages",
            "max_messages",
            type=click.IntRange(0, 8),
            default=2,
            show_default=True,
            help=_MAX_MESSAGES_HELP,
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
        @click.option("--idempotency-key", "key", default=None, help=_IDEMPOTENCY_KEY_HELP)
        @click.pass_obj
        def _run(ctx: Context, /, **kwargs: object) -> None:
            # Delegates parsed values to the testable execution method.
            self.execute(ctx, kwargs)

    def execute(self, context: Context, raw: dict[str, object]) -> None:
        # Everything invalid fails here, before files are read, models run, or money moves.
        values = dict(raw)
        key = values.pop("key", None)
        request = SuggestionRequestBuilder().build(values, context.paths())
        if request.settings.dry_run:
            # A dry run never calls a model, so it is never admitted and never charged.
            SuggestionRenderer().render_result(context, SuggestionService().run(request))
            return
        receipt, sdk = self.admit(context, request, key if isinstance(key, str) else None)
        result = SuggestionService(sdk).run(request)
        SuggestionRenderer().render_result(
            context, result.model_copy(update={"admission": receipt})
        )

    def admit(
        self, context: Context, request: SuggestionRequest, key: str | None
    ) -> tuple[SuggestionAdmissionReceipt, SuggestionSdk]:
        # Everything before ADMISSION is free, so every rejection a caller can cause happens
        # before the wallet is touched, and no model is called until the grant is verified.
        progress = context.output().diagnostic
        progress(Progress.PREPARING)
        # The key is validated first because a bad one would otherwise surface only after the
        # SDK import and host discovery had already run.
        resolved_key = key or str(uuid4())
        if re.fullmatch(_KEY_PATTERN, resolved_key) is None:
            raise click.BadParameter("Use 8-128 key chars: letters, digits, ._-:.")
        # Loading the SDK proves the Codex integration imports while the run is still free,
        # and the same bindings are reused by the service so they cannot differ after payment.
        sdk = self._sdk_loader()
        # The plan resolves Codex on PATH; it carries only the goal, which stays on this machine
        # because the admission request below holds nothing but the host and the unit count.
        plan = context.runtime_launch_planner().build(
            request.goal, Host.CODEX, Path.cwd(), _CAPABILITY
        )
        # One unit buys up to ten requested ideas, so a count of 2-10 is one unit and 11-15 is
        # two. Categories, rounds, and extra compute change model usage, never the unit count.
        units = math.ceil(
            request.settings.requested_count / SuggestionAdmissionLimit.SUGGESTIONS_PER_UNIT
        )
        # Binding the endpoints needs a stored Vidbyte key, so a caller who never logged in
        # stops here, still before any purchase exists.
        endpoints = context.runtime_endpoints()
        progress(Progress.ADMISSION)
        # One idempotency-keyed purchase covers the whole run; a retry with the same key
        # recovers this purchase instead of buying a second one.
        grant = endpoints.admit_suggestion(AdmitRequest(host=plan.host, units=units), resolved_key)
        if grant.grant_token is None:
            raise RuntimeAdmissionNotVerified("grant_token_missing")
        progress(Progress.VERIFYING)
        # The grant is re-read from the backend rather than trusted as returned, and the key
        # hash ties that verification to this exact invocation.
        hashed = RuntimeAdmissionGate.hash_idempotency_key(resolved_key)
        verified = endpoints.verify_grant(
            VerifyRequest(grant_token=grant.grant_token, idempotency_key_hash=hashed)
        )
        # The gate expects the per-unit price times the units bought, so a receipt priced for
        # another quantity is refused before any model runs.
        verdict = RuntimeAdmissionGate().verify_online(plan, grant, verified, units)
        if not verdict.admitted:
            raise RuntimeAdmissionNotVerified(verdict.reason)
        progress(Progress.ADMITTED)
        # The caller sees what the run cost in the result itself, without asking the backend.
        receipt = SuggestionAdmissionReceipt(
            admission_id=grant.admission_id, charged_cents=grant.charged_cents, units=units
        )
        return receipt, sdk
