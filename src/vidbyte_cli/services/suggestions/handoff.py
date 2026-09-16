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
            suggestion_title=idea.title,
            suggestion_summary=idea.summary,
            primary_category=idea.primary_category,
            secondary_categories=idea.secondary_categories,
            horizon=idea.horizon,
            relationship=idea.relationship,
            readiness=idea.readiness,
            expected_benefit=idea.expected_benefit,
            effort_estimate=idea.effort_estimate,
            review_summary=idea.review_summary,
            evidence_refs=idea.evidence_refs,
            suggestion_context=idea.suggestion_context,
            original_goal=goal,
            selected_action=idea.proposed_action,
            reason_for_selection=idea.why_now,
            current_state=self._state(context),
            relevant_decisions=context.get("decision", ()),
            completed_work=context.get("completed", ()),
            in_progress_work=context.get("in-progress", ()),
            constraints=context.get("constraint", ()),
            required_context=self._required(idea),
            assumptions_to_verify=idea.assumptions,
            suggested_steps=(idea.first_action, idea.completion_criteria),
            deliverables=(idea.completion_criteria,),
            acceptance_checks=tuple(
                check.pass_condition for check in idea.suggestion_context.verification_plan
            ),
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
            f"Suggestion: {handoff.suggestion_title}",
            f"Summary: {handoff.suggestion_summary}",
            f"Category: {handoff.primary_category}",
            f"Horizon: {handoff.horizon.value}",
            f"Relationship: {handoff.relationship.value}",
            f"Readiness: {handoff.readiness.value}",
            f"Expected benefit: {handoff.expected_benefit}",
            f"Effort estimate: {handoff.effort_estimate}",
            f"Review: {handoff.review_summary}",
            "Evidence refs:",
            *[f"- {ref}" for ref in handoff.evidence_refs or ("none supplied",)],
            "Required context:",
            *[f"- {item}" for item in handoff.required_context or ("none supplied",)],
            "Problem or opportunity:",
            f"- Type: {handoff.suggestion_context.problem_or_opportunity.type}",
            f"- Condition: {handoff.suggestion_context.problem_or_opportunity.condition}",
            f"- Consequence: {handoff.suggestion_context.problem_or_opportunity.consequence}",
            f"- Affected area: {handoff.suggestion_context.problem_or_opportunity.affected_area}",
            "Reasoning:",
            f"- Insight: {handoff.suggestion_context.core_insight}",
            f"- Causal rationale: {handoff.suggestion_context.causal_rationale}",
            f"- Goal target: {handoff.suggestion_context.goal_contribution.target}",
            f"- Goal contribution: {handoff.suggestion_context.goal_contribution.contribution}",
            f"- Before: {handoff.suggestion_context.expected_change.before}",
            f"- After: {handoff.suggestion_context.expected_change.after}",
            "Verification plan:",
            *self._verification_lines(handoff),
            f"- Final success condition: {handoff.suggestion_context.final_success_condition}",
            "Decision context:",
            *self._context_lines(handoff),
            "Execution:",
            f"- Goal: {handoff.original_goal}",
            f"- Proposed action: {handoff.selected_action}",
            f"- Why now: {handoff.reason_for_selection}",
            f"- Current state: {handoff.current_state}",
            "Caller decisions:",
            *[f"- {item}" for item in handoff.relevant_decisions or ("none supplied",)],
            "Completed work:",
            *[f"- {item}" for item in handoff.completed_work or ("none supplied",)],
            "In-progress work:",
            *[f"- {item}" for item in handoff.in_progress_work or ("none supplied",)],
            "Constraints:",
            *[f"- {item}" for item in handoff.constraints or ("none supplied",)],
            "Assumptions to verify:",
            *[f"- {item}" for item in handoff.assumptions_to_verify or ("none supplied",)],
            "Steps:",
            *[f"- {step}" for step in handoff.suggested_steps],
            "Deliverables:",
            *[f"- {item}" for item in handoff.deliverables or ("none specified",)],
            "Acceptance:",
            *[f"- {check}" for check in handoff.acceptance_checks],
            "Dependencies:",
            *[f"- {item}" for item in handoff.dependencies or ("none specified",)],
            "Required capabilities:",
            *[f"- {item}" for item in handoff.required_capabilities or ("none specified",)],
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
        # Carries refs plus bounded summaries so paths alone never suffice.
        context = idea.suggestion_context
        return (
            *idea.evidence_refs,
            context.problem_or_opportunity.condition,
            context.core_insight,
        )

    def _verification_lines(self, handoff: SuggestionHandoff) -> tuple[str, ...]:
        # Renders every verification component so the method is executable.
        lines: list[str] = []
        for index, check in enumerate(handoff.suggestion_context.verification_plan, 1):
            lines.extend(
                (
                    f"- Check {index} claim: {check.claim}",
                    f"  Procedure: {check.procedure}",
                    f"  Pass condition: {check.pass_condition}",
                    f"  Evidence: {check.evidence_to_capture}",
                    f"  On failure: {check.on_failure}",
                )
            )
        return tuple(lines)

    def _context_lines(self, handoff: SuggestionHandoff) -> tuple[str, ...]:
        # Renders bounded decision context and caller state in stable order.
        context = handoff.suggestion_context
        lines = [
            *self._labeled_items("In scope", context.scope.in_scope),
            *self._labeled_items("Out of scope", context.scope.out_of_scope),
        ]
        for decision in context.decision_points:
            lines.extend(
                (
                    f"- Decision condition: {decision.condition}",
                    f"  Response: {decision.response}",
                    f"  Requires authority: {decision.requires_authority}",
                )
            )
        lines.extend(
            [
                *self._labeled_items("Beneficiary", context.beneficiaries),
                *self._labeled_items("Affected surface", context.affected_surfaces),
            ]
        )
        for tradeoff in context.tradeoffs:
            lines.extend(
                (
                    f"- Tradeoff cost: {tradeoff.cost}",
                    f"  Why acceptable: {tradeoff.reason_acceptable}",
                    f"  Mitigation: {tradeoff.mitigation}",
                )
            )
        for risk in context.risks:
            lines.extend(
                (
                    (
                        f"- Risk: {risk.failure_mode} ({risk.likelihood} likelihood, "
                        f"{risk.impact} impact)"
                    ),
                    f"  Guard: {risk.guard}",
                )
            )
        for unknown in context.unknowns:
            lines.extend(
                (
                    f"- Unknown: {unknown.question}",
                    f"  Importance: {unknown.importance}",
                    f"  Resolution: {unknown.resolution_method}",
                )
            )
        lines.extend(
            (
                f"- Confidence: {context.confidence.level}",
                *[f"  Confidence basis: {item}" for item in context.confidence.basis],
                *[
                    f"  Confidence would change with: {item}"
                    for item in context.confidence.would_change_with
                ],
                f"- Cost of inaction: {context.cost_of_inaction}",
                f"- Reversibility: {context.reversibility.level}; {context.reversibility.reason}",
                f"  Recovery: {context.reversibility.recovery}",
                (
                    f"- Time sensitivity: {context.time_sensitivity.level}; "
                    f"{context.time_sensitivity.trigger}"
                ),
            )
        )
        if context.time_sensitivity.expires_when:
            lines.append(f"  Expires when: {context.time_sensitivity.expires_when}")
        for alternative in context.alternatives_considered:
            lines.extend(
                (
                    f"- Alternative considered: {alternative.alternative}",
                    f"  Not selected because: {alternative.reason_not_selected}",
                )
            )
        return tuple(lines)

    def _labeled_items(self, label: str, items: tuple[str, ...]) -> tuple[str, ...]:
        # Gives repeated context values a stable readable label.
        return tuple(f"- {label}: {item}" for item in items)

    def _stops(self) -> tuple[str, ...]:
        # Fixed stop set every handoff carries regardless of category.
        return (
            "Done when acceptance checks pass.",
            "Stop on contradictory evidence.",
            "Stop when authority or prerequisites are missing.",
        )
