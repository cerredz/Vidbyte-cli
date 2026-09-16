# Coordination

## Description
A coordination suggestion aligns people, ownership, timing, or dependencies so that related work can proceed together. It addresses friction at the interfaces between actors rather than the internal quality of any one actor's task. The distinguishing feature is that no individual is failing and the work is still stuck, because the failure lives in an agreement nobody made. That agreement might concern who owns a boundary, when a dependency arrives, what a handoff must contain, or who has authority to settle a conflict. Coordination problems are easy to mistake for effort problems, since the visible symptom is usually that something did not get done. The correct test is whether the obstacle would survive if every party worked harder in isolation.

The suggestion should name the parties, the shared outcome that connects them, and the exact mismatch between them. It should prefer a decision, an owner, or a handoff contract over more status communication, because reporting the misalignment more often does not resolve it. It should say who is accountable once the coordination action is taken, since an alignment with no owner decays back to its original state. It should define the smallest synchronization point that releases the blocked work rather than the most complete process that could be imagined. It should say how the agreement gets recorded and made visible, because unrecorded agreements are renegotiated silently. It should not create meetings or process unless they resolve a named coordination failure, since ceremony is the most common substitute for an actual decision.

## Why use
Use this category when the obstacle lives between people rather than inside anyone's work. This is a specific and common failure shape: two competent parties, a shared objective, and a boundary neither of them owns. It resists effort by construction, because the work each party can do alone is already done. Naming the mismatch is what unblocks it, and naming it precisely — ownership, timing, authority, information, or interface — is what determines which repair will work.

The category also exists to resist the default response to misalignment, which is to add communication. More status reporting makes a coordination failure more visible without making it smaller, and it consumes exactly the attention the parties need in order to act. Requiring the suggestion to propose a decision, an owner, or a contract keeps it pointed at resolution. Requiring an accountable party afterwards keeps the resolution from being temporary.

Distinguish it from the categories around it. Bottleneck concerns a point in a system that limits flow, which may be a coordination failure but is argued from throughput rather than from an unmade agreement. Delegation moves a defined piece of work to a better-placed owner, where coordination decides who owns a boundary in the first place. Prerequisite creates a missing condition, and while an agreement can be a prerequisite, coordination is specifically about aligning parties rather than about any missing condition. Strategy chooses a direction that many actions serve, which resolves conflicting local goals by subordinating them rather than by negotiating an interface. Use coordination when two or more parties must act consistently and currently cannot.

## Use cases
- **Two owners each assume the other will act.** An unassigned boundary can leave a task waiting with nobody seeing it as theirs. Establish one accountable owner and the inputs that owner receives.
- **A dependency has no agreed timing.** Both sides may be individually ready and badly sequenced. Suggest a date, trigger, or service expectation that lets both sides plan.
- **A handoff loses information.** Work crossing teams or tools may arrive without context, acceptance criteria, or a responsible party. Define the smallest handoff contract that preserves what the receiver needs.
- **Groups are optimizing conflicting outcomes.** Local goals can produce delay, duplication, or incompatible decisions. Recommend a shared outcome or an explicit trade that aligns them.
- **A decision needs the right participants once.** The issue may be blocked because authority, expertise, or affected parties are absent. Arrange one focused decision with a named outcome rather than a standing meeting.
- **Parallel work risks collision.** Independent actions may touch the same resource, assumption, or interface. Suggest a boundary, lock, sequence, or shared record that prevents interference.
- **An external party controls the next step.** A supplier, partner, reviewer, or platform may owe something specific. Use it when the request, the owner, and the escalation path can all be made explicit.
- **A commitment changed without downstream alignment.** New scope, timing, or constraints may have invalidated assumptions others still hold. Recommend notifying and renegotiating the affected boundary.
- **The same misunderstanding keeps recurring.** Repeated confusion at one interface usually indicates a missing definition rather than careless people. Propose the definition, and say where it lives.
- **Authority is ambiguous in a dispute.** Two parties may disagree with no agreed way to settle it. Name the decision-maker and the criteria, rather than arguing the case again.
- **A shared artifact has no owner.** A document, schema, environment, or process may be used by everyone and maintained by no one. Assign maintenance explicitly, with a scope.
- **Work is being duplicated across groups.** Two efforts may be solving the same problem without either knowing. Suggest the smallest visibility mechanism that would have prevented it, and who runs it.

## When not to use
- **The obstacle is inside one person's task.** A solitary difficulty does not become coordination because others care about the result.
- **No dependency between actors exists.** Without an interface there is nothing to align.
- **The proposal is a status meeting.** Reporting the mismatch is not resolving it.
- **The suggestion adds process without naming a failure.** Ceremony introduced speculatively becomes overhead that outlives its cause.
- **One scarce stage is limiting everyone.** That is a property of flow rather than of agreement.
- **The conflict is really about direction.** Parties pulling different ways because the objective is unsettled need the objective settled.

Route the suggestion elsewhere when one of those signals holds. A limiting stage belongs to bottleneck, and an unsettled direction belongs to strategy or goal clarification. Moving defined work to a better-placed owner is delegation, and creating a missing condition is prerequisite. If the parties agree but lack the skill to execute, use learning, and if the interface problem is really that nobody has decided what done means, use goal clarification first.
