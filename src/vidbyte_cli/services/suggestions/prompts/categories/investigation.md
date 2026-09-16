# Investigation

## Description
An investigation gathers missing knowledge before a consequential action or decision. It begins with a precise question and ends when enough reliable evidence is available for the decision at hand. The work should prefer sources that are authoritative, accessible, relevant, and proportionate to the stakes. More information is not automatically better if it cannot change the decision or reduce meaningful uncertainty. A useful investigation includes a stopping point and a way to synthesize what was learned. Use this category when information, rather than execution or persuasion, is the binding input to the next choice.

## Why use / use cases
- [ ] **A consequential decision rests on a missing fact.** Acting without the fact could create material cost, risk, or rework. Use this category to gather only the evidence that bears on the decision.
- [ ] **Sources disagree about an important claim.** Conflicting information may change the route or confidence of the work. Suggest an investigation that compares source quality, definitions, timing, and evidence rather than counting opinions.
- [ ] **The caller needs to understand the current state.** An inventory, baseline, dependency map, or history may be missing. Use it when the snapshot will determine a concrete action or allocation.
- [ ] **A constraint or requirement is unclear.** Policy, law, contract, platform behavior, or stakeholder need may govern what is possible. Recommend focused inquiry when the governing source can be identified and applied.
- [ ] **A pattern needs explanation before intervention.** Repeated behavior may have several causes. Use this category when gathering discriminating evidence is more useful than immediately choosing a remedy.
- [ ] **An external option must be compared.** Vendors, methods, markets, or practices may differ on criteria that matter to the goal. Suggest an investigation with a bounded comparison frame and decision threshold.
- [ ] **The cost of being wrong is high.** A short evidence-gathering step may protect a larger commitment. Use it when the investigation can materially lower uncertainty before exposure increases.
- [ ] **The caller is researching without a stopping rule.** Open-ended reading can feel productive while delaying action. Recommend an explicit question, source set, synthesis format, and evidence threshold.

## Things to consider
- What exact question must the investigation answer?
- Which decision or action depends on the answer?
- What sources are authoritative, accessible, current, and relevant?
- What evidence would be sufficient rather than merely interesting?
- How will source quality, definitions, and conflicts be evaluated?
- What information has low decision value and should be excluded?
- What stopping rule prevents the inquiry from expanding indefinitely?
- How will the findings change the next action or confidence level?

## Generation requirements

Every investigation suggestion must gather specific evidence that can change a decision, confidence
level, or next action. The proposal should:

- State the question, unknown, or competing explanation being investigated.
- Explain why the uncertainty matters now and what decision depends on resolving it.
- Identify the authoritative, observable, representative, or otherwise useful source of evidence.
- Define the smallest search, interview, inspection, comparison, or analysis that can answer the question.
- Distinguish source quality, absence of evidence, contradiction, and unresolved uncertainty.
- Use supplied context to bound scope and avoid researching facts that cannot affect the caller's goal.
- Label assumptions, search terms, inclusion criteria, and possible bias before collecting evidence.
- Define what finding would support, weaken, or redirect the current plan.
- Preserve a traceable record so another person can inspect the evidence and reasoning.
- Keep open-ended evidence gathering as the primary mechanism; route claim checks to verification and live interventions to experiment.

## Candidate shape

Shape the candidate as a focused evidence-gathering plan with a decision attached. The reader should
know what to look for, where to look, how much is enough, and what changes for each result.

- In the **summary**, name the unknown, decision at stake, and evidence needed.
- In the **action sequence**, define the query, source, collection method, synthesis, and decision update.
- In **decision points**, choose source authority, sample or stopping rule, inclusion criteria, and how conflicting findings are handled.
- In **considerations**, cover relevance, reliability, recency, representativeness, cost, access, bias, privacy, and reproducibility.
- In **dependencies**, name source access, expert availability, tools, permissions, or a decision owner.
- In **evidence references**, cite source content and explain how it supports or contradicts the claim; never cite a search phrase as evidence.
- In **assumptions**, label what the investigation presumes and make it part of the search or interpretation plan.
- In the **completion criterion**, require a bounded evidence record and a clear change in confidence or action.
- If the fact is already available or has a fixed pass condition, route it to verification.

## Valid suggestion directions

Use this category for bounded inquiry:

- Inspect records, artifacts, logs, requirements, or authoritative documents.
- Interview or observe people positioned to know the relevant behavior or constraint.
- Compare alternatives, precedents, or sources using explicit inclusion criteria.
- Trace a claim to its primary source and record support, contradiction, or uncertainty.
- Analyze a pattern, failure, queue, cost, or behavior before choosing an intervention.
- Narrow an open research question into the smallest decision-relevant query.
- Search for disconfirming evidence rather than collecting only supporting examples.
- Reconcile conflicting sources and state why one should carry more weight.
- Set a stopping rule when additional evidence is unlikely to change the decision.

## Alignment check

The candidate is aligned when it gathers evidence about an unknown and connects the result to a real
decision. It should not promise certainty or research for its own sake. The investigation must have a
source, scope, interpretation rule, and action for meaningful findings.

Reject or reroute candidates that:

- Check a known claim against a fixed acceptance condition; use verification.
- Introduce an intervention whose effect is unknown; use experiment.
- Learn a reusable capability or skill; use learning.
- Clarify the desired outcome rather than facts about the world; use goal clarification.
- Continue searching after the decision is already supported and no finding can change it.

The primary decision must be what evidence is worth gathering now and how it will change the caller's next move.

## When not to use
Do not use this category when the needed evidence is already available or when the real need is to test a live intervention. Avoid it when no plausible finding would change the decision, because more research would only defer commitment. If the question is a claim check with a known acceptance condition, use verification; if the issue is learning a capability, use learning.
