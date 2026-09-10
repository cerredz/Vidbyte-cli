"""Extracts one handoff from a saved suggestion result without a model.

The command reads a `suggestions.result` document, selects one idea by id,
and emits its handoff as `suggestions.handoff`. This is a pure local read, so
it never needs credentials and never calls a provider on any code path.
"""

from __future__ import annotations

import json
from pathlib import Path

import click

from ...lib.errors.failures import SuggestionContextUnreadable, SuggestionInputInvalid
from ...lib.runtime.context import ApplicationContext as Context
from ...types.suggestions import SuggestionHandoff, SuggestionResult
from .render import SuggestionRenderer

_COMMAND_HELP = (
    "Extract one idea's handoff from a saved suggestions result file for execution. "
    "The input is read locally and validated as a suggestions.result document, then "
    "the idea matching --idea is selected by its stable identifier. No model is "
    "called and no credentials are needed, so extraction stays offline and free. Use "
    "JSON output when another agent must consume the handoff packet directly."
)

_INPUT_HELP = (
    "Path to a saved suggestions result JSON document to extract from. The file must "
    "be a suggestions.result envelope with a matching schema version, otherwise a "
    "typed error is raised before anything is emitted. A missing path, a directory, "
    "or malformed JSON fails the same way with no partial output. Exactly one input "
    "source is read per invocation."
)

_IDEA_HELP = (
    "Identifier of the idea whose handoff should be extracted from the result. The "
    "value must match one idea id in the document exactly, such as idea-003, with no "
    "fuzzy matching or prefix expansion applied. An unknown id fails with a usage "
    "error that lists no file contents. The emitted handoff preserves the selected "
    "idea's id and revision verbatim."
)


class SuggestionHandoffCommand:
    """Reads a saved batch and renders one deterministic handoff packet."""

    def register(self, parent: click.Group) -> None:
        # Attaches handoff with input and idea selectors as its only options.
        @parent.command(name="handoff", help=_COMMAND_HELP)
        @click.option(
            "--input",
            "input_path",
            required=True,
            type=click.Path(path_type=Path),
            help=_INPUT_HELP,
        )
        @click.option("--idea", required=True, help=_IDEA_HELP)
        @click.pass_obj
        def _handoff(ctx: Context, input_path: Path, idea: str) -> None:
            # Delegates to the execution method for direct testing.
            self.execute(ctx, input_path, idea)

    def execute(self, context: Context, input_path: Path, idea: str) -> None:
        # Validates the document, selects the idea, and emits its handoff.
        result = self._load(input_path)
        selected = next((item for item in result.ideas if item.id == idea.strip()), None)
        if selected is None:
            raise SuggestionInputInvalid()
        handoff = SuggestionHandoff.model_validate(selected.handoff.model_dump(mode="json"))
        SuggestionRenderer().render_handoff(context, handoff)

    def _load(self, input_path: Path) -> SuggestionResult:
        # Rejects missing, malformed, and wrong-kind documents before selecting.
        try:
            text = Path(input_path).read_text(encoding="utf-8-sig")
            document = json.loads(text)
        except (OSError, json.JSONDecodeError) as error:
            raise SuggestionContextUnreadable(str(error)) from error
        if not isinstance(document, dict) or document.get("kind") != "suggestions.result":
            raise SuggestionInputInvalid()
        try:
            return SuggestionResult.model_validate(document.get("data", document))
        except Exception as error:
            raise SuggestionContextUnreadable(str(error)) from error
