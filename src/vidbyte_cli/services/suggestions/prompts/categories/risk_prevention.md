# Risk Prevention

## Description
A risk-prevention suggestion reduces the likelihood or impact of a plausible failure. It connects a recognizable exposure to a proportionate guard, signal, or recovery plan. The suggestion should focus on risks that could change the caller’s outcome rather than every imaginable concern. Prevention is strongest when the protection happens before the exposure begins. Detection and recovery still matter when prevention cannot be complete or would cost too much. Use this category when the benefit of reducing the exposure outweighs the burden of the control.

## Why use / use cases
- [ ] **A known failure mode could derail the outcome.** The caller has enough context to describe how the failure would occur. Use this category when a specific guard can reduce the likelihood or impact before exposure grows.
- [ ] **An irreversible action is approaching.** A check, backup, approval, or staged release may preserve recovery before the point of no return. Suggest prevention when the protection is proportionate to the consequence.
- [ ] **A handoff can lose critical information.** Ambiguous ownership, missing context, or an unverified interface may create predictable failure. Use it to add a narrow contract or confirmation at the boundary.
- [ ] **A small control prevents expensive rework.** A validation, limit, default, or precondition may catch the issue earlier. Recommend it when the control cost is lower than repairing the downstream result.
- [ ] **Exposure is increasing faster than confidence.** The work may be reaching more users, systems, data, or stakeholders than the evidence supports. Use this category to add staged exposure or a leading signal.
- [ ] **Detection is too slow for the consequence.** The caller may need an alert, audit, or checkpoint before the failure compounds. Suggest prevention when faster detection creates a credible recovery window.
- [ ] **A fallback can preserve the core obligation.** The primary route may fail despite reasonable safeguards. Use it when a concrete alternate path or recovery state can reduce the impact.
- [ ] **A recurring incident needs a durable guard.** Repeated warnings or manual fixes may indicate that prevention belongs in the workflow. Recommend it when the pattern and owner of the control are clear.

## Things to consider
- What exact failure mode and exposure make the risk plausible?
- How severe, likely, observable, and reversible is the outcome?
- Which prevention point occurs before the exposure or commitment?
- What guard, limit, checkpoint, or default is proportionate?
- How will the control avoid creating equal or greater operational burden?
- What signal detects failure early enough to matter?
- What recovery or fallback preserves the core outcome?
- Who owns the control, monitors it, and revises it when conditions change?

## When not to use
Do not use this category for every hypothetical concern, a goal that is merely unclear, or a claim that needs verification rather than protection. Avoid it when the control burden exceeds the plausible consequence or when no owner can maintain it. If the right answer is to abandon an exposure entirely, use stop or defer; if the risk comes from one limiting constraint, use bottleneck.
