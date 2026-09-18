Suggestion feedback records the user's explicit reaction to a suggestion in one local project's memory. The accept verb records a suggestion the user clearly wanted, and the reject verb records a suggestion the user clearly refused; both store the suggestion text, the user's optional reason, and a UTC timestamp.

Recorded feedback is what makes project-backed runs improve over time. The next agents suggest run that passes the same project key loads every accepted and rejected record as context, so the generator can prefer the qualities of accepted ideas, and ideas that repeat a rejected suggestion word for word are removed before ranking.

Record feedback only when the user's reaction is explicit. Silence, a change of topic, partial interest, or the user implementing something similar is never acceptance or rejection, and a reason should carry the user's own explanation rather than one the calling agent inferred. A project-backed run returns both feedback commands with the project key already filled in, which is the safest template to use.

Feedback commands are local and deterministic. They need no credentials, make no model call, and never execute, approve, or schedule the suggestion they record. Each call appends one record after every earlier one and never edits or removes history.
