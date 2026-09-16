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
state without another round of abstract planning. The category exists for the situation where the full
path is not worth designing yet — either because it is unknown, disputed, or cheaper to discover by
moving — and the binding question is simply what to do now. The requirement is therefore availability:
the action must run on the information, tools, access, and authority the caller already has, or on one
small prerequisite obtained as part of the move. It also has to be small enough to start without
translating an aspiration into tasks, because a step that still needs decomposition is a plan rather
than a next step. The best candidates buy something specific — progress, information, or reduced risk —
that makes the decision after it easier to take. Since the move may fail or reveal a blocker, the
proposal has to say what follows in each case. The proposal should:

- Name the current state, the desired near-term result, and the gap the next action closes.
- Use information, tools, access, and authority already available unless obtaining one small
  prerequisite is the action.
- Be concrete enough that an executor can start without translating an aspiration into tasks.
- Prefer information gain, progress, or risk reduction that makes the following decision easier.
- Distinguish the first useful action from a full plan, strategy, or optional expansion.
- State dependencies, owner, effort boundary, and a completion signal for the immediate move.
- Flag uncertainty and propose a check when acting immediately could cause avoidable harm.
- Define what the caller should do next after the action succeeds, fails, or reveals a blocker.
- Choose a move whose result is visible soon enough to inform the decision that follows it.

## Alignment check

Alignment, for immediate next steps, means the candidate is startable right now. The caller is at a
particular point with particular resources, and this category answers what can be done from there —
without first settling a strategy, agreeing a plan, or obtaining something they do not have. An aligned
candidate is concrete enough to hand to someone and small enough to finish before the situation changes,
and its result either moves the work forward or makes the next decision clearer. The action may well
reveal what the larger plan should be; what it must not do is require that plan to exist first.

The second half of alignment is distinguishing this from its neighbours, which all describe doing
something. Advancing a route the caller has already accepted belongs to continuation, because there the
direction is settled and momentum is what matters. Closing the last remaining obligation belongs to
completion. A missing condition that has to be obtained before anything can proceed belongs to
prerequisite. A broad tradeoff, an unsettled goal, or stakeholder alignment that must come first belongs
to its own category, and optional value that is not the next useful move belongs to adjacent opportunity
or quick wins. Keep the candidate here only when the live question is which concrete move is available
from now and what its result will unlock.

## When not to use
Do not use this category when an accepted plan already determines the next step; use continuation instead. Avoid it when the first action requires a missing condition, a consequential decision, or broad alignment that must happen first. If the goal is unclear, use goal clarification; if a fact must be established before acting, use investigation or verification.
