"""software-engineering command surface — the declarative half of integrating a harness.

`fix` overrides the translation and presentation hooks to show the full pattern (validate
flat CLI kwargs into a typed FixInput, then shape the envelope from it). `review` uses every
default, so it needs no hooks at all.
"""

from __future__ import annotations

from ...lib.harness.types import HarnessCommandDef
from ...types.harness import HarnessRepoRef, HarnessRunCreateRequest
from ...types.manifest import ArgSpec, OptionSpec
from .render import render_fix_result
from .types import FixInput

HARNESS_NAME = "software-engineering"


def _fix_invocation(
    params: dict[str, object], repo: HarnessRepoRef | None
) -> HarnessRunCreateRequest:
    # Translation hook: validate the flat CLI kwargs into a typed FixInput, then shape the
    # backend envelope from it. This is where a harness's custom dataclass earns its keep.
    parsed = FixInput.model_validate(params)
    return HarnessRunCreateRequest(
        harness=HARNESS_NAME,
        command="fix",
        args={"task": parsed.task},
        options={"issue": parsed.issue, "base": parsed.base, "dry_run": parsed.dry_run},
        repo=repo,
    )


def build_commands() -> list[HarnessCommandDef]:
    return [
        HarnessCommandDef(
            name="fix",
            description="Implement a task or fix a bug on the current repo and open a PR",
            args=[ArgSpec(name="task", description="what to change, in natural language")],
            options=[
                OptionSpec(name="issue", type="number", description="GitHub issue to resolve"),
                OptionSpec(name="base", default="main", description="branch to base the PR on"),
                OptionSpec(name="dry-run", type="boolean", description="plan without pushing"),
            ],
            mode="await",
            to_invocation=_fix_invocation,
            present=render_fix_result,
        ),
        HarnessCommandDef(
            name="review",
            description="Review the current branch and report findings",
            mode="read",
        ),
    ]
