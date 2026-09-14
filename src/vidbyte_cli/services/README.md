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
- `sdk.py` — the only module in this service that imports the Vidbyte SDK, and it does so lazily.

Prompt text lives only in `prompts/*.md`. A prompt change is reviewed as prose, and no Python
file in this package may contain a sentence addressed to a model.

## persistence/

The `runtime persistence` primitive. One Codex thread, driven through a fixed number of
continuation turns chosen by the strength tier rather than by the model's own claim that it
has finished.

- `runner.py` — the last gate before the first paid turn: re-checks the verified receipt
  against the plan, then starts the session.
- `session.py` — the SDK agent, the continuation loop, and the rejection of an incomplete
  reply or a changed thread.
- `prompts/` — both prompts as Markdown files, plus `library.py`, which loads and fills them.

Admission policy, host discovery, and launch planning stay in `lib/runtime_primitives/`,
because `adversarial-team` and `same-host-ensemble` reach the same code. A service that owned
them would have to be imported by its siblings to obtain an admission gate.
