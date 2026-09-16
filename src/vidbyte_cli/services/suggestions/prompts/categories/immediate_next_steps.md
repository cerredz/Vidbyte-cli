# Immediate Next Steps

## Description
An immediate-next-steps suggestion identifies an action the caller can take from the present state. It focuses on reducing the distance between current knowledge and the next useful result. Unlike continuation, it does not assume that an entire existing plan has already been accepted. It may compare several available moves and choose the one with the best immediate information or progress value. The action should be small enough to begin without another round of abstraction. Use this category when the immediate move is more important than designing the full path in advance.

## Why use / use cases
- [ ] **The caller is unsure what can begin now.** The current state may contain enough information for one useful action even if the full plan is incomplete. Use this category to turn availability into a concrete start.
- [ ] **Several low-cost actions are possible.** Choosing one can reduce delay and avoid spending more time on abstract planning. Suggest the move with the strongest immediate progress or information value.
- [ ] **The next action can reveal the shape of the problem.** A small inspection, conversation, draft, or measurement may make later choices easier. Use it when the action is safe and its result will inform what follows.
- [ ] **The caller is stuck at an abstraction boundary.** Broad goals can hide a first observable operation. Recommend an action that changes the state enough to create a better next question.
- [ ] **A new task has no accepted execution path.** The direction may be plausible while the route remains open. Use this category to identify a reversible first move without pretending the whole plan is settled.
- [ ] **A dependency may already be available.** The caller may delay while assuming access, approval, or input is missing. Suggest checking the current state when a quick confirmation can unlock work.
- [ ] **The next move can be completed without new authority.** A small action may produce progress while larger decisions await an owner. Use it when it does not create unapproved scope or irreversible commitment.
- [ ] **A short action can establish momentum.** Starting may reduce context-switching or make the task concrete. Recommend it only when momentum leads to evidence or progress rather than activity for its own sake.

## Things to consider
- What is true, available, and unresolved in the present state?
- Which actions can begin without new permission or preparation?
- What immediate result provides the greatest progress or information value?
- Which action is reversible if the initial assumption is wrong?
- What hidden prerequisite could make the apparent next step premature?
- What is the smallest unit that changes the state meaningfully?
- What result determines whether to continue, redirect, or stop?
- What larger planning question should remain deliberately deferred?

## Generation requirements

Every immediate-next-steps suggestion must identify an action the caller can begin from the present
state without another round of abstract planning. The proposal should:

- Name the current state, desired near-term result, and gap the next action closes.
- Use information, tools, access, and authority already available unless obtaining one small prerequisite is the action.
- Be concrete enough that an executor can start without translating an aspiration into tasks.
- Prefer information gain, progress, or risk reduction that makes the following decision easier.
- Distinguish the first useful action from a full plan, strategy, or optional expansion.
- Use supplied context to respect completed, in-progress, blocked, and forbidden work.
- State dependencies, owner, effort boundary, and a completion signal for the immediate move.
- Label uncertainty and propose a check when acting immediately could cause avoidable harm.
- Define what the caller should do next after the action succeeds, fails, or reveals a blocker.
- Keep near-term movement from the current state as the primary mechanism; route accepted-plan execution, final closure, and broad choices elsewhere.

## Candidate shape

Shape the candidate as the smallest useful move available now. It should reduce distance to a result
or increase information without pretending to solve every later step.

- In the **summary**, name the current state, immediate action, and near-term result.
- In the **action sequence**, begin with available inputs, perform the first bounded move, inspect its result, and choose the next branch.
- In **decision points**, identify what can be decided now, what should remain deferred, and what result changes the next step.
- In **considerations**, cover effort, risk, dependency, reversibility, owner, distraction, and completion evidence.
- In **dependencies**, name only conditions that genuinely block starting; do not turn preferences into prerequisites.
- In **evidence references**, cite the current state, goal, and available resource; do not cite a future result.
- In **assumptions**, label what the immediate action relies on and include a cheap check when necessary.
- In the **completion criterion**, require a visible artifact, observation, decision, or state change that enables the following move.
- If an accepted plan already determines this exact action, use continuation rather than reopening the next step.

## Valid suggestion directions

Use this category for actions that can begin now:

- Inspect, collect, or transform an available input into the next useful artifact.
- Send the specific request, handoff, or question that unlocks near-term progress.
- Run a small check that reduces uncertainty before a consequential action.
- Draft the smallest version of a deliverable that can be reviewed or tested.
- Resolve the first local blocker when the broader route is already clear.
- Record current state, ownership, or a decision so work can resume without reconstruction.
- Prepare one dependency that is genuinely needed for the next step.
- Choose the immediate action with the highest information or progress value.
- Define a stop or reassessment point after the first move.

## Alignment check

The candidate is aligned when the caller can begin it from the current state and its result makes
progress or the next decision visible. It should be smaller than a strategy and more concrete than a
general recommendation. The action can reveal a new plan, but it should not require one before starting.

Reject or reroute candidates that:

- Advance an already accepted route without a new immediate choice; use continuation.
- Close the final obligation; use completion.
- Depend on a missing condition that must be obtained first; use prerequisite.
- Need a broad tradeoff, goal decision, or stakeholder alignment before action; use the fitting category.
- Are optional extensions rather than the next useful move; use adjacent opportunity or quick wins.

The primary decision must be which concrete move is available from now and what its result will unlock.

## When not to use
Do not use this category when an accepted plan already determines the next step; use continuation instead. Avoid it when the first action requires a missing condition, a consequential decision, or broad alignment that must happen first. If the goal is unclear, use goal clarification; if a fact must be established before acting, use investigation or verification.
