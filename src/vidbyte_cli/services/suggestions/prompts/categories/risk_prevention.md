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

## Generation requirements

Every risk-prevention suggestion must reduce the likelihood or impact of a plausible consequential
failure with a proportionate control. The category exists because some costs are only avoidable in
advance, and the moment to pay for them is before the exposure begins rather than after it is realized.
The requirement that keeps this useful is selectivity: anything can fail, so a proposal must name a
specific exposure whose occurrence would change the caller's outcome, along with the trigger and the
causal path to it. Proportion is the second requirement. A control is itself a cost — burden, friction,
new failure modes, reduced accessibility — and a guard that costs more than the exposure it removes is a
net loss, however prudent it sounds. Where prevention is impossible or too expensive, detection and
recovery are legitimate answers. And because controls decay quietly, the proposal has to say who owns it,
how it is tested, and what signal would show it is no longer working. The proposal should:

- Name the exposure, trigger, affected outcome, and the time when prevention matters.
- Explain likelihood, impact, detectability, or reversibility without inventing unsupported
  probabilities.
- Prefer prevention before exposure, while retaining detection, response, and recovery where prevention
  cannot be complete.
- Choose a control, owner, signal, or boundary that addresses the causal path rather than adding generic
  caution.
- Account for control burden, usability, accessibility, privacy, safety, and risks introduced by the
  control itself.
- Define how the control will be monitored, tested, maintained, and revised as conditions change.
- Preserve necessary work while making the decision to accept, reduce, transfer, avoid, or monitor
  exposure explicit.
- State what signal would show the risk is reduced or the control is failing.
- Show that the guard costs less than the exposure it is meant to remove.

## Alignment check

Alignment, for risk prevention, means the candidate protects an outcome the caller cares about from a
failure that could plausibly happen. There is an exposure — a way the work can go wrong, with a trigger
and a causal path — and the candidate intervenes on that path before the cost is realized. An aligned
candidate names the exposure specifically, says what it would damage and when prevention has to be in
place, and proposes a control with an owner and a signal. Listing every imaginable concern is the
opposite of this: a guard earns its place by attaching to one plausible, consequential failure rather
than to general caution.

The second half of alignment is proportion. Controls have their own cost — friction, maintenance, lost
accessibility, sometimes new failure modes — so an aligned candidate weighs the guard against the
exposure, prefers prevention where it is achievable and falls back to detection and recovery where it is
not, and says how the control stays alive as conditions change. Establishing whether a claim is even
true belongs to verification; a repeated flow constraint rather than a failure exposure belongs to
bottleneck; and concluding that the exposure cannot be justified at all belongs to stop or defer. A
warning that changes no likelihood, impact, detection, or recovery belongs nowhere. Keep the candidate
here only when the live question is which safeguard changes the risk path enough to justify its burden.

## When not to use
Do not use this category for every hypothetical concern, a goal that is merely unclear, or a claim that needs verification rather than protection. Avoid it when the control burden exceeds the plausible consequence or when no owner can maintain it. If the right answer is to abandon an exposure entirely, use stop or defer; if the risk comes from one limiting constraint, use bottleneck.
