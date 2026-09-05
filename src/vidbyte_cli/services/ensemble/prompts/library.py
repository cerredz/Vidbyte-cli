"""Loads the Markdown prompts in this package and fills their `{{placeholder}}` slots.

No prompt text lives here — every sentence an agent reads is in a `.md` file beside this one,
so a prompt change is a prose diff. This class only reads those files, substitutes values, and
renders the candidate blocks the selector and implementer are given.

Substitution is a literal replace rather than `str.format`, because the prompts contain JSON
braces that a format string would try to interpret.
"""

from __future__ import annotations

from importlib import resources

from ....types.ensemble import (
    APPROACHES_PER_ROLE_MAX,
    APPROACHES_PER_ROLE_MIN,
    ApproachCandidate,
    GeneratedRole,
    SelectedApproach,
)

# The package the `.md` files sit in, named explicitly so resolution does not depend on how
# this module was imported. They ship in the wheel via `[tool.setuptools.package-data]`.
_ANCHOR = "vidbyte_cli.services.ensemble.prompts"


class EnsemblePrompts:
    """Reads each prompt file once and renders it with the values one run supplies."""

    def __init__(self) -> None:
        # One cache per run; the files are immutable package data, so reading twice is waste.
        self._cache: dict[str, str] = {}

    def planner_system_prompt(self, roles: int) -> str:
        # Stage one designs the roster every later stage forks from.
        return self._render("planner_system", roles=str(roles))

    def planner_turn_prompt(self, task: str, roles: int) -> str:
        # The planner reads the real task before deciding which perspectives it needs.
        return self._render("planner_turn", task=task, roles=str(roles))

    def role_system_prompt(self, role: GeneratedRole) -> str:
        # The planner wrote the four sections; the mandate and constraints are ours, always.
        return self._render(
            "role_system",
            role_name=role.name,
            identity=role.identity,
            personality=role.personality,
            knowledge=role.knowledge,
            goal=role.goal,
            **self._band(),
        )

    def role_turn_prompt(self, task: str) -> str:
        # Every role sees the same task; their system prompts are what differentiates them.
        return self._render("role_turn", task=task, **self._band())

    def selector_system_prompt(self) -> str:
        # One selector agent spans every narrowing round, so this is authored once per run.
        return self._render("selector_system")

    def selector_round_prompt(
        self, task: str, candidates: tuple[ApproachCandidate, ...], number: int, target: int
    ) -> str:
        # Only the survivors are re-rendered, so each round's prompt shrinks with the slate.
        return self._render(
            "selector_round_turn",
            task=task,
            candidates=self._render_candidates(candidates),
            round=str(number),
            surviving=str(len(candidates)),
            target=str(target),
        )

    def selector_final_prompt(
        self, task: str, candidates: tuple[ApproachCandidate, ...], number: int
    ) -> str:
        # The last round is authored separately: what it writes becomes the implementer brief.
        return self._render(
            "selector_final_turn",
            task=task,
            candidates=self._render_candidates(candidates),
            round=str(number),
            surviving=str(len(candidates)),
        )

    def implementer_system_prompt(self) -> str:
        # Stage four's system prompt: the only agent in the topology that may write.
        return self._render("implementer_system")

    def implementer_turn_prompt(
        self, task: str, selected: SelectedApproach, candidates: int, roles: int
    ) -> str:
        # The implementer sees one approach and the reviewer's verdict, never the whole slate.
        approach = selected.candidate.approach
        verdict = selected.verdict
        return self._render(
            "implementer_turn",
            task=task,
            candidate_id=selected.candidate.candidate_id,
            score=str(verdict.score),
            title=approach.title,
            approach=approach.approach,
            rationale=verdict.rationale,
            pros=self._bullets(verdict.pros),
            cons=self._bullets(verdict.cons + approach.risks),
            files=self._bullets(approach.files),
            candidates=str(candidates),
            roles=str(roles),
        )

    def _band(self) -> dict[str, str]:
        # The proposal band comes from the schema constants, so prompt and contract agree.
        return {"minimum": str(APPROACHES_PER_ROLE_MIN), "maximum": str(APPROACHES_PER_ROLE_MAX)}

    def _render(self, name: str, **values: str) -> str:
        # A literal replace, because the prompts contain JSON braces `str.format` would eat.
        rendered = self._read(name)
        for key, value in values.items():
            rendered = rendered.replace("{{" + key + "}}", value)
        return rendered

    def _read(self, name: str) -> str:
        # Read through `importlib.resources` so the prompts resolve from the installed wheel.
        if name not in self._cache:
            source = resources.files(_ANCHOR).joinpath(f"{name}.md")
            self._cache[name] = source.read_text(encoding="utf-8").strip()
        return self._cache[name]

    def _render_candidates(self, candidates: tuple[ApproachCandidate, ...]) -> str:
        # One flat labeled block each: prose would bury the ids the selector must echo back.
        return "\n\n".join(self._render_candidate(candidate) for candidate in candidates)

    def _render_candidate(self, candidate: ApproachCandidate) -> str:
        # The id leads, because naming an id the selector was not given fails the round.
        approach = candidate.approach
        return (
            f'<candidate id="{candidate.candidate_id}" role="{candidate.role}" '
            f'confidence="{approach.confidence.value}">\n'
            f"title: {approach.title}\n"
            f"approach: {approach.approach}\n"
            f"pros:\n{self._bullets(approach.pros)}\n"
            f"cons:\n{self._bullets(approach.cons)}\n"
            f"risks:\n{self._bullets(approach.risks)}\n"
            f"files:\n{self._bullets(approach.files)}\n"
            "</candidate>"
        )

    def _bullets(self, values: tuple[str, ...]) -> str:
        # An empty list still renders a line, so a section never reads as truncated output.
        return "\n".join(f"  - {value}" for value in values) or "  - none reported"
