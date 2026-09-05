# services/

Feature services. Each subfolder owns one product's algorithm from validated input to
normalized result.

The dependency direction is one way. A service may import from `lib/` and `types/`; nothing
in `lib/` may import a service, and no service may import a command. Commands parse and
render, services decide and orchestrate, `lib/` transports and formats.

## ensemble/

The `runtime same-host-ensemble` primitive. Four stages on one machine: a planner turn that
generates the role roster, concurrent read-only forks that each return 5 to 10 weighed
approaches, a read-only selector that narrows every approach down to one across several
rounds, and one write-enabled fork that implements the winner.

- `runner.py` — resolves the SDK, buys admission once, delegates to the service.
- `service.py` — the four-stage algorithm, the narrowing ladder, and the failure policy.
- `settings.py` — which prompt, which output schema, and which sandbox mode each stage gets.
- `prompts/` — every prompt as a Markdown file, plus `library.py`, which loads and fills them.
- `sdk.py` — the only module in `src/` that imports the Vidbyte SDK, and it does so lazily.

Prompt text lives only in `prompts/*.md`. A prompt change is reviewed as prose, and no Python
file in this package may contain a sentence addressed to a model.
