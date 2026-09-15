**Title**
This input is called Suggestion Context. Suggestion context is the complete caller-supplied state used for one bounded run. It gives the agent a named record to read. It keeps this signal separate from unrelated context. It is optional when the caller has no such information. Supply it when the signal could change the next action.

**Description**
Suggestion context is the complete caller-supplied state used for one bounded run. The record should be concise enough to interpret without private history. It should describe the state that matters rather than every event around it. It may contain uncertainty when the caller has not confirmed a claim. It remains task information supplied for this run. Its wording should support a decision rather than advertise an implementation.

**Why it matters**
It gives the agent a named view of goals, evidence, history, constraints, and uncertainty. It helps the agent avoid a generic answer. It also gives the critic a reason to keep, revise, or reject a candidate. The value of the record depends on its accuracy and freshness. Omit it when it would only add noise. A clear reason makes later review more honest.

**Influence on output**
It makes omissions explicit and keeps every surviving suggestion traceable to the state that shaped it. The agent should connect a suggestion to this signal when the connection is material. The critic should call out unsupported or conflicting use of it. The final handoff should preserve any boundary that affects safe evaluation. It should not treat this input as permission to execute work. Uncertain signals should lower confidence rather than create false precision.
