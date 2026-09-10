"""Parses and validates suggest-run options, then invokes the service.

The command validates everything a caller can get wrong before any model or
provider work starts. Context flags are all optional; only the goal is
required, either from `--goal` or from the structured `--input` document.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from ...lib.errors.failures import (
    SuggestionCategoryUnknown,
    SuggestionContextUnreadable,
    SuggestionInputInvalid,
)
from ...lib.runtime.context import ApplicationContext as Context
from ...services.suggestions.categories import SuggestionCategories
from ...services.suggestions.context import SuggestionContextBuilder
from ...services.suggestions.service import SuggestionService
from ...types.suggestions import SuggestionHorizon, SuggestionRequest, SuggestionSettings
from .render import SuggestionRenderer

_COMMAND_HELP = (
    "Generate ranked next-action ideas with execution-ready handoffs for one goal. "
    "Pass the goal with --goal for a minimal call, or pass --input with a JSON document "
    "or a dash for stdin when another agent supplies substantial structured context. "
    "Optional flags add completed work, constraints, decisions, artifacts, and other "
    "background so the ideas stay concrete instead of generic. The command returns up "
    "to --count worthwhile ideas with handoffs, and it explains shortfalls explicitly."
)

_GOAL_HELP = (
    "The objective the ideas must advance, written as one plain sentence. This value "
    "decides what the generator and critic optimize for, so keep it specific about the "
    "outcome rather than the method. It is required unless --input supplies the goal, "
    "and it cannot be combined with --input in the same invocation. An empty string "
    "fails before any model call so callers get a usage error instead of vague ideas."
)

_INPUT_HELP = (
    "Path to a JSON request document, or a single dash to read it from stdin. The "
    "document carries the goal plus optional context lists and generation settings in "
    "one structure, which suits agent callers passing substantial context. It is "
    "mutually exclusive with individual goal and context flags, while --count and "
    "similar generation controls may still override the document values. Malformed "
    "JSON, missing files, and unsupported schema versions fail before any model call."
)

_CONTEXT_HELP = (
    "General background prose about the task, repeatable once per statement. Each "
    "value becomes one labeled context item the generator can ground ideas in, with "
    "its own stable reference in the manifest. Use this for facts that fit no narrower "
    "flag, and prefer the narrower flags when one applies. Values are used verbatim "
    "as task data and never as instructions that override the system prompt."
)

_CONTEXT_FILE_HELP = (
    "Path to one UTF-8 text or Markdown file whose contents become background prose. "
    "Repeat the option once per file when notes are too long for shell arguments, and "
    "each file receives its own stable reference with hashing and truncation reported. "
    "Files are read whole up to a per-file cap, and directories, missing paths, and "
    "unsupported suffixes fail before any model call. Contents are task data, never "
    "instruction overrides for the agent."
)

_HANDOFF_FILE_HELP = (
    "Path to one versioned structured handoff JSON file describing current task state. "
    "The file is parsed and its salient fields become labeled context, so a downstream "
    "agent can hand its state to this one without retyping it. A missing file, a "
    "directory, malformed JSON, or an unsupported schema version fails before any "
    "model call. Omit this flag when there is no prior handoff, which means not "
    "supplied rather than an empty state."
)

_COMPLETED_HELP = (
    "Work already finished that ideas must not repeat, repeatable once per statement. "
    "Each value is preserved verbatim so the critic can penalize overlapping ideas, "
    "which is what keeps suggestions from restating done work. Use short declarative "
    "sentences naming the outcome, not the process. Omitting this flag means no "
    "completed work was supplied, not that nothing is complete."
)

_IN_PROGRESS_HELP = (
    "Work currently underway that ideas must avoid duplicating, repeatable per item. "
    "The generator treats these as occupied territory and the critic checks overlap "
    "against them, so parallel agents do not propose each other's active tasks. Keep "
    "each value to one statement about who is doing what. A statement identical to a "
    "--completed value is preserved with a contradiction warning rather than dropped."
)

_DECISION_HELP = (
    "A settled decision suggestions must respect, repeatable once per decision. "
    "Decisions constrain generation the way walls constrain a room: ideas that violate "
    "them are cut during critique rather than ranked. State the decision and its scope "
    "in one sentence each. Omit this flag when no decisions were supplied, which the "
    "manifest records as not supplied."
)

_CONSTRAINT_HELP = (
    "A boundary every suggestion must respect, repeatable once per constraint. The "
    "critic checks feasibility against these first, so violated ideas never reach the "
    "final slate regardless of their novelty. Write each as a testable limit on scope, "
    "technology, or cost. Missing constraints are reported as missing context, never "
    "assumed to be absent."
)

_AVOID_HELP = (
    "A previously rejected or unwanted direction to exclude, repeatable per direction. "
    "Matching ideas are suppressed deterministically before ranking, which is how the "
    "caller teaches the agent what not to propose twice. Name the direction plainly "
    "rather than describing it obliquely. This flag composes with previous-suggestion "
    "files that carry the same intent."
)

_QUESTION_HELP = (
    "An unresolved question that better context could answer, repeatable per question. "
    "Questions inform the missing-context section and can shape investigation or "
    "experiment ideas, but they never block generation on their own. Phrase each as "
    "the actual open question, not as background. Omit when there are none to report."
)

_CAPABILITY_HELP = (
    "A capability available to the downstream executor, repeatable per capability. "
    "Capabilities land in the handoff so the executor knows what it may rely on, such "
    "as inspecting local files or calling a specific tool. Keep each to one concrete "
    "capability statement. They never grant authority, which stays not-granted in v1."
)

_SUCCESS_HELP = (
    "What success should look like for the goal, repeatable per statement. Success "
    "lines shape acceptance checks and completion criteria so ideas stay evaluable "
    "instead of aspirational. Write each as an observable outcome a stranger could "
    "verify. These inform ranking but never act as hard filters on their own."
)

_ARTIFACT_HELP = (
    "Path to one local text artifact included as evidence, repeatable once per file. "
    "Each artifact keeps its path identity, content hash, and context reference into "
    "the output, so an executor on another machine can see what grounded the idea. "
    "Only UTF-8 text, Markdown, and JSON are accepted, with per-file and total caps "
    "enforced before model calls. Missing or unreadable artifacts fail with a typed error."
)

_PREVIOUS_HELP = (
    "Path to one previous suggestions result JSON used to avoid repeating ideas. The "
    "file's titles and summaries become rejected directions for suppression, which is "
    "what lets iterative callers converge instead of circling. A missing file or "
    "malformed document fails before any model call. Omit this flag on the first "
    "iteration, which simply means no prior batch exists."
)

_COUNT_HELP = (
    "Desired maximum number of returned ideas, from 1 to 20 with a default of 5. "
    "This is an upper bound on worthwhile ideas, not a quota: returning three strong "
    "ideas with an explicit shortfall beats filling the slate with weak filler. The "
    "generator builds a broader pool internally and critique narrows it to this many. "
    "Values outside the range fail before any model call, and this flag may override "
    "an --input document value."
)

_CATEGORY_HELP = (
    "Restrict generation to the given category id, repeatable for several categories. "
    "Unknown ids fail before any model call so typos surface as usage errors rather "
    "than silently broad generation. When omitted, the whole registry is considered "
    "and a useful mix is selected. Combine with --all-categories only to state that "
    "breadth explicitly, since both mean the same selection behavior."
)

_ALL_CATEGORIES_HELP = (
    "Consider the entire category registry explicitly instead of a subset. This is the "
    "default behavior written down, so it never requires returning one idea per "
    "category and never changes the count semantics. It exists for callers that want "
    "their breadth intent visible in logs and manifests. It composes with --count and "
    "--horizon without further interaction."
)

_HORIZON_HELP = (
    "Filter when ideas should become useful: now, next, later, or any for no filter. "
    "The default of any lets the mix span horizons, while a narrower value focuses "
    "generation on work that pays off in that window. Horizon is stored per idea and "
    "reported in coverage, so callers can see the temporal shape. An invalid value is "
    "rejected by the shell parser before the command body runs."
)

_ROUNDS_HELP = (
    "Maximum critique-and-revision cycles, from 1 to 3 with a default of 2. More "
    "rounds let the critic refine borderline candidates, while a single round keeps "
    "cost and latency minimal for simple goals. The loop shape is computed in code, "
    "never chosen by the model, so this bound is always honored. Out-of-range values "
    "fail before any model call."
)

_PROVIDER_HELP = (
    "Select the model provider through the existing credential infrastructure. The "
    "name is mapped explicitly to an SDK identifier rather than assumed to match, so "
    "misspellings fail with a typed error before generation. When omitted, the run "
    "uses the deterministic offline path with no credentials required. The value is "
    "recorded in settings for reproducibility."
)

_MODEL_HELP = (
    "Select the generator model within the chosen provider for this run. The value is "
    "recorded in settings and passed to the SDK agent when provider configuration is "
    "available, otherwise it is carried as metadata on the deterministic path. An "
    "empty value simply means the provider default applies. It never changes the "
    "output schema or the category registry."
)

_CRITIC_MODEL_HELP = (
    "Optional critic override within the selected provider for this run. When set, "
    "the critic runs on this model while the generator uses --model, which lets "
    "callers pair a strong reviewer with a cheaper drafter. When omitted, the critic "
    "reuses the generator model. The value is validated as a non-empty string and "
    "recorded in settings."
)

_MAX_OUTPUT_TOKENS_HELP = (
    "Bound the tokens of each individual model response in this run. This is a "
    "stopping threshold, not a billing cap: an in-flight request can consume tokens "
    "before the limit is observed. Smaller values keep responses tight while larger "
    "values suit complex goals with rich context. It must be a positive integer when given."
)

_MAX_TOTAL_TOKENS_HELP = (
    "Workflow-wide token stopping threshold across generation and revisions. Like "
    "per-response bounds, this stops scheduling new calls rather than interrupting "
    "one already in flight, so slight overruns are possible by design. It covers "
    "revisions too, never just the first pass. It must be a positive integer when given."
)

_TIMEOUT_HELP = (
    "Overall workflow deadline in seconds for this run, covering every revision. The "
    "service stops scheduling new work once the deadline passes and returns the last "
    "fully reviewed batch as a partial result. This bounds wall time without promising "
    "preemption of an in-flight provider call. It must be a positive integer when given."
)

_DRY_RUN_HELP = (
    "Validate and show resolved inputs without calling any model for this run. The "
    "output carries the context manifest, resolved settings, and validation warnings "
    "with file bodies withheld by default, which is what makes it safe for agents to "
    "probe large contexts cheaply. It never requires credentials and never spends "
    "tokens. Combine with JSON output when another agent inspects the manifest."
)


class SuggestRunCommand:
    """Validates run options ahead of any model call, then renders the result."""

    def register(self, parent: click.Group) -> None:
        # Attaches run with goal, context, generation, and budget controls.
        @parent.command(name="run", help=_COMMAND_HELP)
        @click.option("--goal", default=None, help=_GOAL_HELP)
        @click.option("--input", "input_path", default=None, help=_INPUT_HELP)
        @click.option("--context", "contexts", multiple=True, help=_CONTEXT_HELP)
        @click.option(
            "--context-file",
            "context_files",
            multiple=True,
            type=click.Path(path_type=Path),
            help=_CONTEXT_FILE_HELP,
        )
        @click.option(
            "--handoff-file",
            "handoff_file",
            default=None,
            type=click.Path(path_type=Path),
            help=_HANDOFF_FILE_HELP,
        )
        @click.option("--completed", "completed", multiple=True, help=_COMPLETED_HELP)
        @click.option("--in-progress", "in_progress", multiple=True, help=_IN_PROGRESS_HELP)
        @click.option("--decision", "decisions", multiple=True, help=_DECISION_HELP)
        @click.option("--constraint", "constraints", multiple=True, help=_CONSTRAINT_HELP)
        @click.option("--avoid", "avoid", multiple=True, help=_AVOID_HELP)
        @click.option("--question", "questions", multiple=True, help=_QUESTION_HELP)
        @click.option("--capability", "capabilities", multiple=True, help=_CAPABILITY_HELP)
        @click.option("--success", "successes", multiple=True, help=_SUCCESS_HELP)
        @click.option(
            "--artifact",
            "artifacts",
            multiple=True,
            type=click.Path(path_type=Path),
            help=_ARTIFACT_HELP,
        )
        @click.option(
            "--previous-suggestions",
            "previous_suggestions",
            default=None,
            type=click.Path(path_type=Path),
            help=_PREVIOUS_HELP,
        )
        @click.option(
            "--count", type=click.IntRange(1, 20), default=5, show_default=True, help=_COUNT_HELP
        )
        @click.option("--category", "categories", multiple=True, help=_CATEGORY_HELP)
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
        @click.option("--provider", default=None, help=_PROVIDER_HELP)
        @click.option("--model", "model", default=None, help=_MODEL_HELP)
        @click.option("--critic-model", "critic_model", default=None, help=_CRITIC_MODEL_HELP)
        @click.option(
            "--max-output-tokens",
            type=click.IntRange(1, 1000000),
            default=None,
            help=_MAX_OUTPUT_TOKENS_HELP,
        )
        @click.option(
            "--max-total-tokens",
            type=click.IntRange(1, 10000000),
            default=None,
            help=_MAX_TOTAL_TOKENS_HELP,
        )
        @click.option(
            "--timeout-seconds", type=click.IntRange(1, 3600), default=None, help=_TIMEOUT_HELP
        )
        @click.option("--dry-run", is_flag=True, default=False, help=_DRY_RUN_HELP)
        @click.pass_obj
        def _run(ctx: Context, /, **kwargs: object) -> None:
            # Delegates parsed values to the testable execution method.
            self.execute(ctx, kwargs)

    def execute(self, context: Context, raw: dict[str, object]) -> None:
        # Everything invalid fails here, before files are read or models run.
        request = self._request(raw)
        result = SuggestionService().run(request)
        SuggestionRenderer().render_result(context, result)

    def _request(self, raw: dict[str, object]) -> SuggestionRequest:
        # Merges --input documents with CLI overrides into one validated request.
        input_path = raw.get("input_path")
        if isinstance(input_path, str) and input_path:
            return self._from_input(input_path, raw)
        return self._from_flags(raw)

    def _from_flags(self, raw: dict[str, object]) -> SuggestionRequest:
        # Builds context and settings purely from individual flags.
        goal = raw.get("goal")
        if not isinstance(goal, str) or not goal.strip():
            raise SuggestionInputInvalid()
        given = raw.get("categories")
        listed: tuple[str, ...] = ()
        if isinstance(given, (tuple, list)) and given:
            listed = tuple(str(item) for item in given)
        try:
            resolved = SuggestionCategories().require_known(listed)
        except ValueError as error:
            raise SuggestionCategoryUnknown(str(error)) from error
        fields = self._fields(raw)
        files = self._files(raw)
        try:
            snapshot = SuggestionContextBuilder().build(fields, files)
        except ValueError as error:
            raise SuggestionContextUnreadable(str(error)) from error
        from ...types.suggestions import SuggestionContextItem as Item

        items = tuple(
            Item(
                ref=item.ref,
                kind=item.kind,
                label=item.label,
                content=item.content,
                source=item.source,
                caller_supplied=item.caller_supplied,
            )
            for item in snapshot.items
        )
        settings = SuggestionSettings(
            requested_count=self._required_int(raw.get("count"), 5),
            categories=tuple(resolved),
            all_categories=bool(raw.get("all_categories")),
            horizon=SuggestionHorizon(str(raw.get("horizon") or "any")),
            rounds=self._required_int(raw.get("rounds"), 2),
            provider=self._optional_str(raw.get("provider")),
            model=self._optional_str(raw.get("model")),
            critic_model=self._optional_str(raw.get("critic_model")),
            max_output_tokens=self._optional_int(raw.get("max_output_tokens")),
            max_total_tokens=self._optional_int(raw.get("max_total_tokens")),
            timeout_seconds=self._optional_int(raw.get("timeout_seconds")),
            dry_run=bool(raw.get("dry_run")),
        )
        return SuggestionRequest(goal=goal.strip(), context_items=items, settings=settings)

    def _from_input(self, input_path: str, raw: dict[str, object]) -> SuggestionRequest:
        # Rejects mixed sources, reads the document, then merges overrides.
        self._reject_mixed_input(raw)
        document = self._read_input_document(input_path)
        merged = self._merge_input(document, raw)
        return self._from_flags(merged)

    def _reject_mixed_input(self, raw: dict[str, object]) -> None:
        # Input documents stay mutually exclusive with goal/context flags.
        keys = (
            "goal",
            "contexts",
            "context_files",
            "handoff_file",
            "completed",
            "in_progress",
            "decisions",
            "constraints",
            "avoid",
            "questions",
            "capabilities",
            "successes",
            "artifacts",
            "previous_suggestions",
        )
        if any(bool(raw.get(key)) for key in keys):
            raise SuggestionInputInvalid()

    def _read_input_document(self, input_path: str) -> dict[str, object]:
        # Loads and validates the JSON envelope before any merging happens.
        try:
            if input_path == "-":
                document = json.load(sys.stdin)
            else:
                text = Path(input_path).read_text(encoding="utf-8")
                document = json.loads(text)
        except (OSError, json.JSONDecodeError) as error:
            raise SuggestionContextUnreadable(str(error)) from error
        if not isinstance(document, dict):
            raise SuggestionInputInvalid()
        if document.get("schema_version", 1) != 1:
            raise SuggestionContextUnreadable("unsupported schema version")
        goal = document.get("goal")
        if not isinstance(goal, str) or not goal.strip():
            raise SuggestionInputInvalid()
        return document

    def _merge_input(self, doc: dict[str, object], raw: dict[str, object]) -> dict[str, object]:
        # Lets generation flags override document values with fixed defaults.
        merged = dict(raw)
        goal = doc.get("goal")
        merged["goal"] = str(goal).strip()
        settings_doc = self._section(doc, "settings")
        for key, flag in (("count", "count"), ("rounds", "rounds"), ("horizon", "horizon")):
            if merged.get(flag) in (None, 5, 2, "any") and key in settings_doc:
                merged[flag] = settings_doc[key]
        context_doc = self._section(doc, "context")
        for key in (
            "contexts",
            "completed",
            "in_progress",
            "decisions",
            "constraints",
            "avoid",
            "questions",
            "capabilities",
            "successes",
        ):
            if key in context_doc and not merged.get(key):
                value = context_doc[key]
                if isinstance(value, list):
                    merged[key] = tuple(str(item) for item in value)
        return merged

    def _section(self, document: dict[str, object], name: str) -> dict[str, object]:
        # Returns one named object section or an empty mapping when absent.
        section = document.get(name, {})
        return section if isinstance(section, dict) else {}

    def _fields(self, raw: dict[str, object]) -> dict[str, tuple[str, ...]]:
        # Groups repeatable text flags by their context kind.
        mapping = {
            "contexts": "context",
            "completed": "completed",
            "in_progress": "in-progress",
            "decisions": "decision",
            "constraints": "constraint",
            "avoid": "avoid",
            "questions": "question",
            "capabilities": "capability",
            "successes": "success",
        }
        fields: dict[str, tuple[str, ...]] = {}
        for flag, kind in mapping.items():
            values = raw.get(flag)
            if isinstance(values, (tuple, list)) and values:
                fields[kind] = tuple(str(item) for item in values)
        return fields

    def _files(self, raw: dict[str, object]) -> dict[str, tuple[Path, ...]]:
        # Groups file flags by kind, expanding single paths to tuples.
        files: dict[str, tuple[Path, ...]] = {}
        context_files = raw.get("context_files")
        if isinstance(context_files, (tuple, list)) and context_files:
            files["context-file"] = tuple(Path(str(item)) for item in context_files)
        artifacts = raw.get("artifacts")
        if isinstance(artifacts, (tuple, list)) and artifacts:
            files["artifact"] = tuple(Path(str(item)) for item in artifacts)
        for flag, kind in (
            ("handoff_file", "handoff-file"),
            ("previous_suggestions", "previous-suggestions"),
        ):
            value = raw.get(flag)
            if isinstance(value, (str, Path)) and str(value):
                files[kind] = (Path(str(value)),)
        return files

    def _optional_str(self, value: object) -> str | None:
        # Normalizes empty strings to None so settings stay explicit.
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _optional_int(self, value: object) -> int | None:
        # Passes through validated ints while tolerating omission.
        if value is None:
            return None
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.strip().isdigit():
            return int(value.strip())
        return None

    def _required_int(self, value: object, default: int) -> int:
        # Returns a validated int or the default when the flag was omitted.
        resolved = self._optional_int(value)
        return resolved if resolved is not None else default
