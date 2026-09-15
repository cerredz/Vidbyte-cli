A handoff extracts one reviewed idea from a saved suggestion result and emits a deterministic action packet. It is a local read operation for callers that want to pass one selected idea to a person or another agent.

The command requires both a result path and an exact idea identifier. It validates the saved envelope before selecting the idea and never accepts a title, prefix, or fuzzy match as a substitute for the stable identifier.

No provider, credential, or execution permission is needed for extraction. JSON output preserves the handoff fields, while human output prints the copyable execution prompt and the packet itself never grants authority.

Use this command after a run has produced a result document. If selection or validation fails, correct the saved path or identifier and rerun the same request rather than treating an absent handoff as a provider failure.
