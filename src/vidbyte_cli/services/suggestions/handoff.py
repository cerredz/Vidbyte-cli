"""Assembles deterministic execution handoffs from validated ideas.

The handoff is rendered from structured fields only, so the copyable prompt
cannot diverge from the data. Authority always defaults to not-granted: making
a suggestion never authorizes its execution.
"""

from __future__ import annotations

from ...types.suggestions import SuggestionHandoff, SuggestionIdea


class SuggestionHandoffBuilder:
    """Builds one handoff per idea and renders its execution prompt."""

    def __init__(self) -> None:
        # Stateless; every input arrives per call.
        pass

    def build(
        self, idea: SuggestionIdea, goal: str, context: dict[str, tuple[str, ...]]
    ) -> SuggestionHandoff:
        # Copies caller context into typed slots and renders the prompt last.
        handoff = SuggestionHandoff(
            idea_id=idea.id,
            idea_revision=idea.revision,
            original_goal=goal,
            selected_action=idea.first_action,
            reason_for_selection=idea.why_now,
            current_state=self._state(context),
            relevant_decisions=context.get("decision", ()),
            completed_work=context.get("completed", ()),
            in_progress_work=context.get("in-progress", ()),
            constraints=context.get("constraint", ()),
            required_context=self._required(idea),
            assumptions_to_verify=idea.assumptions,
            suggested_steps=(idea.first_action, idea.completion_criteria),
            deliverables=(idea.expected_benefit,),
            acceptance_checks=(idea.completion_criteria,),
            dependencies=idea.dependencies,
            required_capabilities=context.get("capability", ()),
            stop_conditions=self._stops(),
            return_report="Report outcome, evidence, and follow-ups to the calling agent.",
            execution_prompt="pending",
        )
        return handoff.model_copy(update={"execution_prompt": self.render_prompt(handoff)})

    def render_prompt(self, handoff: SuggestionHandoff) -> str:
        # Deterministic rendering: the same handoff always yields the same prompt.
        lines = [
            f"Goal: {handoff.original_goal}",
            f"Action: {handoff.selected_action}",
            f"Why: {handoff.reason_for_selection}",
            f"State: {handoff.current_state}",
            "Steps:",
            *[f"- {step}" for step in handoff.suggested_steps],
            "Acceptance:",
            *[f"- {check}" for check in handoff.acceptance_checks],
            "Stop when:",
            *[f"- {stop}" for stop in handoff.stop_conditions],
            f"Authority: {handoff.authority}",
            f"Report: {handoff.return_report}",
        ]
        return "\n".join(lines)

    def _state(self, context: dict[str, tuple[str, ...]]) -> str:
        # Summarizes caller state from completed and in-progress lists only.
        done = "; ".join(context.get("completed", ())) or "none reported"
        doing = "; ".join(context.get("in-progress", ())) or "none reported"
        return f"Completed: {done}. In progress: {doing}."

    def _required(self, idea: SuggestionIdea) -> tuple[str, ...]:
        # Carries evidence refs plus the benefit line so paths alone never suffice.
        return (*idea.evidence_refs, idea.expected_benefit)

    def _stops(self) -> tuple[str, ...]:
        # Fixed stop set every handoff carries regardless of category.
        return (
            "Done when acceptance checks pass.",
            "Stop on contradictory evidence.",
            "Stop when authority or prerequisites are missing.",
        )
