The total token limit bounds the aggregate model usage scheduled across the workflow. It covers initial generation, critique, and every permitted revision.

The threshold stops new work after observed usage reaches the boundary but does not interrupt an active request. Small overruns are therefore possible and should not be interpreted as ignored policy.

The limit must be positive whenever it is specified. Reaching it returns the last fully reviewed candidate batch with an explicit partial-result reason.
