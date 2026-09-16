The tool-call cap bounds mutations and guidance requests made by the curation agent.

It is enforced inside the run-local store, so rejected calls cannot mutate the committed slate or bypass category and evidence validation.

The value must be between 1 and 256, and the result reports `tool_call_limit` when the cap is reached.
