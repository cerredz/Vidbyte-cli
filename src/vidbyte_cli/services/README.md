# services/

Feature services. Each subfolder owns one product's algorithm from validated input to
normalized result.

The dependency direction is one way. A service may import from `lib/` and `types/`; nothing
in `lib/` may import a service, and no service may import a command. Commands parse and
render, services decide and orchestrate, `lib/` transports and formats.

## ensemble/

The `runtime same-host-ensemble` primitive. Three stages on one machine: a planner turn that
generates the role roster, concurrent read-only forks that each return a structured proposal,
and one write-enabled fork that reconciles them and does the work.

- `runner.py` — resolves the SDK, buys admission once, delegates to the service.
- `service.py` — the three-stage algorithm and its partial-failure policy.
- `settings.py` — which prompt and which sandbox mode each stage gets.
- `prompts.py` — every authored prompt, and assembly of the planner's generated ones.
- `sdk.py` — the only module in `src/` that imports the Vidbyte SDK, and it does so lazily.
