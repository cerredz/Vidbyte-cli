"""job-applier command surface — the declarative half of integrating a harness.

Most commands are pure declarations; only `apply` overrides the translation and
presentation hooks to show the pattern. `list` uses every default.
"""

from __future__ import annotations

from ...lib.harness.types import HarnessCommandDef
from ...types.api import HarnessRepoRef, HarnessRunCreateRequest
from ...types.manifest import ArgSpec, OptionSpec
from .render import render_apply_result
from .types import ApplyInput


def _apply_invocation(params: dict[str, object], repo: HarnessRepoRef) -> HarnessRunCreateRequest:
    # Translation hook: validate the flat CLI kwargs into a typed ApplyInput, then shape the
    # backend envelope from it. This is where a harness's custom dataclass earns its keep.
    parsed = ApplyInput.model_validate(params)
    return HarnessRunCreateRequest(
        harness="job-applier",
        command="apply",
        args={"query": parsed.query},
        options={"resume": parsed.resume, "limit": parsed.limit, "dry_run": parsed.dry_run},
        repo=repo,
    )


def build_commands() -> list[HarnessCommandDef]:
    return [
        HarnessCommandDef(
            name="apply",
            description="Submit applications for roles matching a query",
            args=[ArgSpec(name="query", description="what roles to search for")],
            options=[
                OptionSpec(name="resume", type="path", required=True, description="resume file"),
                OptionSpec(name="limit", type="number", default=10, description="max applications"),
                OptionSpec(name="dry-run", type="boolean", description="plan without applying"),
            ],
            mode="await",
            to_invocation=_apply_invocation,
            present=render_apply_result,
        ),
        HarnessCommandDef(
            name="list",
            description="List applications this harness has submitted",
            mode="read",
        ),
    ]
