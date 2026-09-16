# Verification

## Description
A verification suggestion tests a claim that the caller's next decision depends on. The claim may concern a requirement, a piece of evidence, a behaviour, a state of readiness, a safety property, or the result of earlier work. What makes it verification rather than investigation is that the claim already exists and is believed; the question is whether belief matches reality. The check should be narrower than the whole goal while still representing the risk of proceeding, which is the balance the suggestion has to strike. A useful verification states in advance what would count as support, what would count as failure, and what would leave the matter unresolved, because a check without a pass condition returns whatever the checker expected. It must rest on an observable or authoritative source rather than on intent, memory, or the confidence of whoever made the claim.

The suggestion should say why being wrong matters at this point in the work, since the value of a check is proportional to what is about to be built on it. It should identify the specific source, observation, test, or authority that can establish the claim, because "confirm this" without a means is not a check. It should target the edge, boundary, or failure condition that is most consequential, as claims usually fail there and are usually tested in the middle. It should say what decision follows from each possible result, which is also the test of whether the check is worth running. It should name the evidence to retain so that someone else can inspect the status later, because verification that leaves no record has to be repeated. Where the claim is too vague for a pass condition, the claim needs sharpening before it can be checked at all.

## Why use
Use this category when something believed true is about to be relied on, and the cost of it being false is meaningfully larger than the cost of checking. This is one of the highest-return actions available in most work, and it is systematically skipped, because the claim in question is usually one that a competent person already asserted and re-examining it feels redundant. It is not redundant. Most expensive failures trace back to a true-seeming assumption that nobody tested at the point where testing was still cheap.

The category also does something for honesty that no other category does. It produces a defensible statement of status: not that the work looks right, but that this specific condition was observed, against this source, on this date. That is what allows responsibility to move between people and what stops the same question from being re-argued each time it comes up. The requirement to retain inspectable evidence is what converts a private check into that shared status.

Distinguish it from its neighbours. Investigation answers an open question through inquiry, whereas verification tests a specific claim against a known acceptance condition; the difference is whether the answer is expected. Experiment intervenes to produce evidence about an uncertain effect, so it applies when nobody knows the outcome rather than when someone believes they do. Completion closes a remaining obligation, and verification often serves as its acceptance evidence without being the obligation itself. Risk prevention adds a guard against a failure, where verification establishes whether the failure is already present. Use verification when one focused check makes the status of a consequential claim honest and actionable.

## Use cases
- **A requirement is claimed satisfied.** The work may look complete while one acceptance condition is unconfirmed. Check it directly before treating the result as done.
- **A decision rests on an unconfirmed premise.** The choice may be safe only if a particular fact holds. Confirm it against an authoritative source or a direct observation.
- **Behaviour may differ from design.** What the system actually does under the relevant condition may not match intent. Establish it with a reproducible observation.
- **Readiness is asserted before exposure.** A release, handoff, launch, or migration may depend on an inspectable state. Check it when the check catches a consequential gap before commitment.
- **A fix may work only on the happy path.** The claim may need a boundary, failure, or representative case. Test the relevant edge while it is still cheaper than discovering the gap later.
- **Evidence is being summarized without a source check.** A citation, measurement, or record may not support the conclusion drawn from it. Trace the claim back when doing so could change confidence or action.
- **Two parties disagree about status.** A shared observation can settle whether the disagreement is factual. Use it when an agreed source exists and no negotiation is required.
- **A gate or policy must be demonstrated.** Evidence may be needed that a control, permission, or standard is actually satisfied. Use it when the pass condition and evidence record are explicit.
- **A long-standing assumption has never been tested.** Beliefs inherited from earlier conditions may no longer hold. Check the ones the current plan leans on hardest.
- **A dependency claims a guarantee.** A vendor, library, or team may assert behaviour that has not been observed here. Verify under the conditions that matter to this use.
- **A number is being reused out of context.** A measurement taken under different conditions may no longer apply. Confirm it in the setting where it is being relied on.
- **A migration claims parity.** Old and new paths may be asserted equivalent without comparison. Check the cases where they would most plausibly diverge.

## When not to use
- **The fact is unknown rather than believed.** Open-ended inquiry is a different instrument from a targeted check.
- **The effect of a new intervention is uncertain.** Where nobody knows the outcome, something has to be tried.
- **The claim is too vague for a pass condition.** A check without a threshold confirms whatever was expected.
- **No result would change the next decision.** A check with no consequence is a ritual.
- **The obligation simply needs closing.** Finishing work is not the same as testing a claim about it.
- **A guard is needed rather than a status.** Preventing a failure is a different act from detecting one.

Route the suggestion elsewhere when one of those signals holds. An unknown fact belongs to investigation, and an uncertain effect belongs to experiment. A remaining obligation belongs to completion, and a proportionate guard belongs to risk prevention. A claim too vague to test belongs to goal clarification, and a judgment that only a person can supply belongs to feedback. If the check would pass and the real doubt is whether the work is worth continuing, use stop or defer.
