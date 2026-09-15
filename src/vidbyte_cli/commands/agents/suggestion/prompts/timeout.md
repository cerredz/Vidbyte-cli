The workflow deadline bounds elapsed time across generation, critique, and revision. It protects callers from an open-ended suggestion cycle when model responses are slow.

The deadline prevents new work after expiration but does not promise cancellation within an in-flight provider request. The last fully reviewed batch remains the safe fallback.

The value must be positive whenever it is specified. A time-limited result names the stopping reason so partial completion cannot resemble ordinary success.
