# General suggestion rubric

Use this rubric for every candidate before assigning its final verdict. The rubric is category-neutral, so it judges whether the candidate is a sound next-action suggestion rather than whether it is excellent within a specialized domain. Rate every section independently as `strong`, `adequate`, `weak`, or `unknown`, and explain the rating in one or two precise sentences. Use `unknown` when the supplied context cannot answer the question, and never turn missing information into invented support. A weak section should produce a targeted repair when the candidate's central idea can survive the repair.

## How to use this rubric

The rubric describes the candidate's quality; it does not replace the existing verdict controls. Keep, revise, and reject remain the control signals, while the section ratings explain why the control signal is appropriate. A serious constraint conflict, contradictory evidence, or unsalvageable duplicate remains a hard control even when other sections are strong. Do not average the ratings into one score, because a strong goal connection cannot compensate for a weak or incoherent action. Do not invent a new suggestion while reviewing the current candidate, and do not treat a fluent explanation as evidence that the candidate is sound.

### Things to consider

- Review each section independently before writing the overall summary.
- Separate a defect in the candidate from a fact that the caller did not supply.
- Use the candidate's exact fields and supplied context references when explaining a rating.
- Treat `unknown` as an explicit uncertainty, not as an automatic pass or failure.
- Identify the smallest repair that would address a weak section.
- Preserve useful intent when recommending a revision.

### Questions to ask yourself

- What claim is this section asking me to assess?
- Which candidate fields support or weaken that claim?
- Which supplied context references support my assessment?
- Am I evaluating the candidate, or am I silently inventing a better candidate?
- Is this weakness repairable without changing the candidate's central idea?
- Does the final verdict reflect the most important section-level defects?

## 1. Current-state grounding

This section asks whether the candidate begins from the caller's actual situation. A suggestion is not grounded when it assumes work is unfinished even though the context says it is complete, or when it describes a generic situation instead of the supplied state. The critic should distinguish current facts, prior decisions, active work, unresolved questions, and desired future states. The candidate should acknowledge material context gaps rather than presenting guesses as observations.

### Things to consider

- Accuracy of the stated current state.
- Completed, in-progress, failed, rejected, and avoided work.
- The relevant actor, artifact, system, customer, or decision.
- Whether the context is current or superseded.
- Contradictions inside the supplied context.
- Unsupported assumptions presented as facts.
- Context that the candidate ignores even though it is material.
- Whether the suggestion is specific to this caller's situation.

### Questions to ask yourself

- Does the candidate describe where the work actually stands?
- Does it accidentally repeat work that is already complete or underway?
- Does it rely on a fact that the caller never supplied?
- Does it distinguish what is known from what is desired?
- Does it recognize important contradictions or missing context?
- Would this suggestion still make sense if the context were removed?
- Does the handoff preserve the relevant current-state information?

## 2. Goal contribution

This section asks whether the candidate makes a meaningful contribution to the caller's stated goal. Being related to the same topic is not enough, because a suggestion can be topically relevant while doing nothing useful for the actual objective. The candidate should identify what part of the goal it advances and whether that contribution is direct, enabling, alternative, adjacent, or exploratory. The expected benefit, action, and handoff should preserve the same goal rather than drifting toward a convenient proxy.

### Things to consider

- The exact goal stated by the caller.
- The specific part of the goal the candidate advances.
- Direct versus indirect contribution.
- Whether the benefit matches the original objective.
- Proxy-goal substitution or scope drift.
- Preservation of caller priorities and success definitions.
- Meaningful progress versus activity that merely sounds useful.
- Honesty of the candidate's relationship classification.

### Questions to ask yourself

- What part of the caller's goal would change if this action succeeded?
- Does the candidate explain that connection clearly?
- Is it merely topical, or does it create actual progress?
- Could the action succeed while leaving the real goal unchanged?
- Has the candidate quietly substituted a different objective?
- Does its expected benefit follow from the stated goal?
- Would the caller understand why this candidate belongs in the result set?

## 3. Next-action appropriateness

This section asks whether the candidate is appropriate from the current state, not merely worthwhile at some future point. A good next action respects sequence, prerequisites, open decisions, and the current bottleneck. The candidate should explain why this action belongs now and should not skip a necessary clarification, verification, preparation, or decision. When the caller is not ready for the proposed action, the better suggestion may be the immediate step that makes the later action possible.

### Things to consider

- Whether the action can begin from the current state.
- Required prerequisites and whether they are satisfied.
- Decisions or clarifications that must happen first.
- The current bottleneck, transition, or open question.
- The specificity of the `why_now` explanation.
- Declared horizon and sequence position.
- Premature, obsolete, or downstream actions.
- Whether the candidate is truly next rather than merely later.

### Questions to ask yourself

- Can someone begin this action from the state described?
- Does another action logically need to happen first?
- Is the candidate blocked by an unresolved decision or missing information?
- Does the candidate explain why it belongs now?
- Would it still be equally appropriate at an arbitrary time?
- Is the declared horizon consistent with the proposed action?
- Should the next action instead clarify, verify, decide, or prepare?

## 4. Action definition

This section asks whether the candidate defines one concrete, bounded action. The executor should be able to identify what to do first, what the action concerns, and what recognizable change or output it should produce. A suggestion is underdefined when it uses vague verbs, repeats the goal as an imperative, or hides several independent projects inside one title. The action should be specific enough to begin without requiring the executor to invent the missing plan.

### Things to consider

- A concrete verb and a clear object or target.
- An explicit first action.
- A bounded and understandable scope.
- One coherent action rather than several projects.
- A recognizable output, decision, observation, or state change.
- Appropriate level of abstraction for a next step.
- Agreement between title, summary, action list, and execution prompt.
- Absence of vague placeholders such as “improve” or “explore” without definition.

### Questions to ask yourself

- Could a competent executor tell where to begin?
- What exactly should be acted on, created, changed, decided, or checked?
- Is the first action actually the first step?
- Is this one action or several unrelated actions combined?
- Is the scope a next step rather than an entire project?
- Does the candidate identify a recognizable result?
- Could two executors interpret the action in materially different ways?

## 5. Problem-action fit

This section evaluates the problem or opportunity separately from the proposed response. A serious problem does not automatically justify the proposed action, and an attractive action does not prove that the underlying need is real. The candidate should make its action-to-result mechanism understandable and plausible from the supplied context. The critic must identify when the candidate jumps from “this matters” to an arbitrary solution or confuses an intended outcome with an action.

### Things to consider

- The specific problem, opportunity, decision, or uncertainty being addressed.
- The action proposed in response to it.
- The mechanism connecting the action to the expected result.
- Whether the action targets the right part of the situation.
- Whether the response is specific to this context or generic.
- Whether the expected benefit follows from the action.
- Whether the candidate confuses diagnosis, intervention, and outcome.
- Whether the useful intent can survive a more precise action.

### Questions to ask yourself

- What situation is this candidate responding to?
- What action does it actually propose?
- How is that action expected to change the situation?
- Is that mechanism stated and plausible?
- Does the candidate jump from an important problem to an unrelated solution?
- Could the problem remain true while the proposed action accomplishes nothing?
- If the problem is strong but the action is weak, have I kept those judgments separate?

## 6. Constraint compliance

This section asks whether the candidate remains inside the caller's explicit boundaries and authority. Constraints include prohibitions, prior decisions, requested scope, required formats, and limits on what the handoff may authorize. A suggestion should not silently reopen a closed decision, repeat a forbidden approach, or instruct another agent to take action that the caller never authorized. Serious conflicts are control failures, not merely low-quality ratings.

### Things to consider

- Explicit must, must-not, only, avoid, and forbidden instructions.
- Completed and in-progress work that should not be repeated.
- Prior decisions that the candidate must preserve.
- Scope and horizon selected by the caller.
- Authority to act on systems, people, data, or external commitments.
- Required output or handoff boundaries.
- Constraints carried into the execution prompt.
- Whether the useful intent survives removal of the conflict.

### Questions to ask yourself

- Which explicit constraints apply to this candidate?
- Does any part of the action violate or weaken one of them?
- Does it assume permission, access, ownership, or authority not supplied?
- Does it silently undo a prior decision?
- Does the handoff preserve every material boundary?
- Is the conflict local and repairable, or central to the candidate?
- Should this be rejected regardless of its other qualities?

## 7. Distinctness and non-redundancy

This section asks whether the candidate makes a materially different contribution from the other candidates and known prior work. Different wording, category labels, or titles do not create distinct suggestions when the action, mechanism, target, and result are effectively the same. A useful slate contains real alternatives, complementary actions, or different sequence positions rather than many descriptions of one idea. The critic should identify which candidate survives when two candidates overlap and explain why.

### Things to consider

- Difference in action, target, mechanism, outcome, or sequence position.
- Duplication of completed, in-progress, failed, rejected, or avoided work.
- Candidates that are broader or narrower restatements of one another.
- Alternatives that differ materially rather than cosmetically.
- Candidates that split one coherent action into several entries.
- Category changes that disguise the same underlying action.
- The candidate's marginal contribution to the slate.
- The stronger candidate when two cannot both survive.

### Questions to ask yourself

- Is this semantically different from every sibling candidate?
- Does it create a genuinely different course of action?
- Could two candidates be merged without losing useful information?
- Is the difference substantive or merely verbal?
- Does it repeat prior work under new wording?
- Which candidate should survive if these are duplicates?
- Would removing this candidate reduce the useful option set?

## 8. Communication and handoff quality

This section asks whether another person or agent can understand and use the suggestion without reconstructing missing logic. The title, summary, rationale, action, context, boundaries, and return report should communicate one clear proposal in a useful order. The handoff should contain enough relevant context to evaluate or begin the action while avoiding unrelated material that obscures the request. Clear language is part of suggestion quality because an unclear suggestion cannot reliably influence the next decision.

### Things to consider

- One-pass clarity of the title and summary.
- Explicit action, goal connection, and reason for acting now.
- Relevant decisions, constraints, and context.
- Understandable terminology and references.
- A recognizable completion condition when applicable.
- Distinction between required instructions and optional guidance.
- Preservation of the candidate through the execution prompt.
- No accidental grant of authority.

### Questions to ask yourself

- Can the suggestion be understood without hidden deliberation?
- Does the title accurately name the action?
- Does the summary explain rather than merely praise the idea?
- Does the handoff contain the context needed to use it?
- Does the execution prompt preserve the reviewed candidate exactly enough?
- Are any important boundaries or decisions missing?
- Would a downstream agent know what it is being asked to consider or do?

## 9. Internal coherence

This section asks whether every field describes the same underlying suggestion. A candidate can contain individually plausible fields that contradict one another, such as a narrow first action paired with a broad summary or a completion condition unrelated to the proposed work. The critic should compare the title, rationale, action sequence, expected result, category, horizon, dependencies, and handoff as one connected proposal. When fields disagree, the review should identify the smallest set of fields that must change to restore one coherent idea.

### Things to consider

- Agreement between title, summary, and selected action.
- Agreement between `why_now` and the proposed sequence.
- Agreement between action and expected benefit.
- Agreement between readiness and dependencies.
- Agreement between category, relationship, and mechanism.
- Agreement between completion criteria and the action.
- Agreement between candidate fields and the generated handoff.
- Whether multiple ideas were accidentally conflated.

### Questions to ask yourself

- Do all fields describe one idea?
- Does the first action implement the summary?
- Does the expected benefit follow from the action?
- Do dependencies and readiness describe the same state?
- Does the category describe the actual mechanism?
- Does the completion condition belong to this action?
- Has the handoff drifted from the candidate that was reviewed?

## 10. Suggestion substance

This section asks whether the candidate is a real and useful suggestion rather than an observation, aspiration, category label, or generic best practice. A substantive suggestion adds a course of action, decision, clarification, or next move that makes the caller's path clearer. Fluent wording cannot compensate for an empty recommendation that could be given to almost any caller. When the candidate proposes investigation, clarification, stopping, or delegation, it should still state what should happen and what decision or change that action serves.

### Things to consider

- A genuine recommendation rather than a description of the current state.
- A concrete course of action or decision to consider.
- Specificity to the caller's situation.
- A rationale tied to this particular action.
- A useful distinction from generic advice.
- An explicit next move when proposing investigation or clarification.
- A meaningful decision when proposing prioritization or stopping.
- Substantive content beneath fluent or promotional language.

### Questions to ask yourself

- Does this candidate actually recommend something?
- Is it more than a restatement of the goal or desired outcome?
- Could the same wording be given to almost any caller?
- Does it narrow the space of possible next actions?
- If it asks a question, does it say what to do with the answer?
- If it proposes investigation, what should be investigated and why?
- Would accepting it make the caller's next move clearer?

## Required assessment format

For every candidate, return exactly one assessment for each rubric section. Use the fixed field names in the structured schema, rate each section as `strong`, `adequate`, `weak`, or `unknown`, and provide a concise explanation for every rating. Include only context references that exist in the supplied context, and use the explanation to state what the reference supports. Mark a section `unknown` when the context cannot answer it, rather than guessing or treating fluency as support. Keep the existing verdict, confidence, evidence check, constraint state, duplicate identifier, repair instruction, preserved fields, and review summary alongside this rubric assessment.
