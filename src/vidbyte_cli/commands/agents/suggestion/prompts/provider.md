**Provider**
Provider identifies the configured model service responsible for suggestion reasoning.
Explicit selection makes the source of generated and reviewed output reproducible across runs.
The provider must correspond to a supported SDK integration with available credentials.
Invalid or unavailable selections fail as provider configuration problems rather than empty suggestion results.
Provider choice does not alter schemas, categories, or context meaning in any way.

**Purpose of Provider**
The purpose of Provider is to pin which model service answers every turn in the run.
That pin keeps generation, critique, and curation on one consistent backend with one credential.
It also makes cost and capability attributable, because different providers price and behave differently.
The selection works alongside model overrides for the critic rather than replacing them.
When none is selected, the established default provider behavior remains in effect.

**When not to use Provider**
Do not set Provider merely because the option exists when the default backend already serves the goal.
Omit it when the caller has no provider preference and let the standard resolution apply.
Do not use this option to pick a critic model, because the critic-model option overrides only the review turn.
Use a narrower setting when the concern is specifically budgets, rounds, or selection rather than backend.
Avoid naming a provider whose credentials are not configured, because the run will fail before generating anything.

**Provider inputs**
The value is one supported provider name, currently `openai`, whenever it is specified.
A single value is supplied per run, and repeated occurrences are not combined.
Whitespace and shell quoting do not change the meaning, while an unknown name is rejected before provider work.
The command does not reinterpret the name as anything other than a backend selection for this run.
Unsupported values fail fast at the request boundary with a typed input error.

**Defaults and precedence for Provider**
When it is omitted, the run uses the established default provider resolution.
Command-line values are the only source for this selection, and the run does not read a separate configuration document.
Environment variables do not silently populate this setting, which keeps an invocation reproducible.
An explicit value always takes precedence over the default for exactly one run.
The critic-model override, when set, still selects the review turn's model within the chosen provider.

**Provider output contract**
Provider is not printed as a separate progress message because stdout is reserved for the command result.
For a model-backed run, the effective provider travels inside the validated settings carried by the result envelope.
For dry-run output, the manifest records the requested provider without spending any provider turn.
Human output summarizes the resulting suggestions, while JSON and JSONL output preserve the settings and warnings.
Backend problems surface as typed provider failures, never as silently empty slates.

**How to use Provider**
Use the command below as the smallest valid invocation shape for this value.
Replace the brace-delimited placeholder with the caller's actual provider name while preserving shell quoting.
Combine the option with a precise goal because the provider selects the backend rather than defining the task.
Confirm credentials for the named provider before launching a real run.
Keep the provider stable when comparing settings so backend differences do not confound the comparison.
The command remains a single argv-built request and does not require a temporary configuration file.

```text
vidbyte-cli agents suggest run --goal "{goal}" --provider openai
```

**Examples for Provider**
A minimal example supplies only the required goal and leaves provider resolution at its default.
A normal example pins the supported provider explicitly for a reproducible cost and capability story.
An advanced example combines the provider pin with JSON output for another agent to consume deterministically.
Piping is appropriate only for a caller that captures the emitted result document, because input itself is passed through argv.
JSON output is the stable choice when another agent will inspect settings, warnings, and handoffs.
If an example fails, preserve the same goal and correct the named setting before changing the reasoning budgets.

```text
vidbyte-cli agents suggest run --goal "{goal}" --provider openai
vidbyte-cli --json agents suggest run --goal "{goal}" --provider openai --count 8
```

**Related commands for Provider**
Use agents suggest categories --view-all when the caller needs to choose a reasoning lens before running.
Use --critic-model when only the review turn needs a different model within the provider.
Use dry-run when the request shape and file manifest need inspection without credentials or model usage.
Use agents suggest handoff only after a result document exists and a specific idea identifier has been selected.
Use the budget options when the concern is spend or time rather than backend selection.
These commands share the same result conventions but do not imply that one command can authorize another.

**Failure modes for Provider**
An unsupported provider name fails before any model work because the request dataclass requires a known backend.
Missing credentials for the named provider fail as provider configuration errors rather than empty results.
A provider or schema failure mid-run is reported as a provider failure and is never converted into a false no-suggestions result.
Budget and validation failures keep their own typed paths and are never relabeled as provider problems.
Recover by correcting the specific value named by the error, rerunning dry-run when useful, and preserving the same intent.

**Authentication and permissions for Provider**
This selection decides which configured credentials a real run will spend.
The name itself validates locally without credentials, while model-backed runs require the provider to be configured.
Credentials are used only when a real model-backed run is requested and are never copied into result prose.
Read-only deny-all settings apply to generator and critic agents so suggestions cannot mutate the host through this workflow.
Permission failures should be repaired at the provider boundary rather than by weakening the selection contract.
