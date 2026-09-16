The agent-call cap bounds the total generator, critic, and curator turns in one run.

It protects the provider budget when rounds or recovery paths expand, while still allowing the default generation plus three critique-and-curation passes.

The value must be between 1 and 128, and the result reports `agent_call_limit` when the next turn is refused.
