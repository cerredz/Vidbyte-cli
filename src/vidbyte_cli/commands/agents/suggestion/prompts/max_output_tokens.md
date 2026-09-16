**Max Output Tokens**
Max Output Tokens bounds the intended size of each individual model reply in the run.
It keeps one generation or critique turn from consuming the workflow's entire token budget.
Smaller values favor concise artifacts, while larger values accommodate richer context and candidate detail.
The threshold is not a billing guarantee, because an in-flight request may finish beyond it.
It applies consistently to generation, critique, and curation responses alike.

**Purpose of Max Output Tokens**
The purpose of Max Output Tokens is to tell every model turn how much room its structured reply may take.
That room shapes reply length without changing what the reply must contain or prove.
It also guards the aggregate token budget, since many oversized turns would exhaust it early.
The ceiling works alongside the total-token cap rather than replacing it: one bounds each turn, the other bounds the run.
The workflow carries the ceiling into every turn prompt so each agent sees the same expectation.

**When not to use Max Output Tokens**
Do not set Max Output Tokens merely because the option exists when default reply sizes already work.
Omit it when the caller has no per-turn size concern and let the provider defaults apply.
Do not use this ceiling to bound total run spend, because the total-token cap governs the aggregate.
Use a narrower budget option when the concern is specifically turns, tool edits, rounds, or elapsed seconds.
Avoid tiny ceilings for large slates, because a cramped turn returns truncated artifacts that fail validation.

**Max Output Tokens inputs**
The value is one positive integer up to 5000000 whenever it is specified.
A single value is supplied per run, and repeated occurrences are not combined.
Whitespace and shell quoting do not change the meaning, while a non-integer value is rejected before provider work.
The command does not reinterpret the number as anything other than a per-turn output ceiling.
Values outside the supported range fail fast at the request boundary with a typed input error.

**Defaults and precedence for Max Output Tokens**
When it is omitted, no per-turn ceiling is sent and each turn uses its natural provider-bounded length.
Command-line values are the only source for this ceiling, and the run does not read a separate configuration document.
Environment variables do not silently populate this setting, which keeps an invocation reproducible.
An explicit value always takes precedence over omission for exactly one run.
The total-token cap, when set, still bounds the run aggregate independently of this per-turn ceiling.

**Max Output Tokens output contract**
Max Output Tokens is not printed as a separate progress message because stdout is reserved for the command result.
For a model-backed run, the effective ceiling travels inside the validated settings carried by the result envelope.
For dry-run output, the manifest records the requested ceiling without spending any provider turn.
Human output summarizes the resulting suggestions, while JSON and JSONL output preserve the settings and warnings.
Truncated turns surface as provider or validation outcomes, never as silently shortened ideas.

**How to use Max Output Tokens**
Use the command below as the smallest valid invocation shape for this value.
Replace the brace-delimited placeholder with the caller's actual integer while preserving shell quoting around spaces.
Combine the option with a precise goal because the ceiling shapes reply size rather than defining the task.
Raise the ceiling when curation receipts arrive incomplete on large slates with generous evidence.
Keep the ceiling proportionate to the requested count so each turn can actually fit its candidates.
The command remains a single argv-built request and does not require a temporary configuration file.

```text
vidbyte-cli agents suggest run --goal "{goal}" --max-output-tokens 8000
```

**Examples for Max Output Tokens**
A minimal example supplies only the required goal and leaves the per-turn ceiling unset.
A normal example sets a moderate ceiling that fits several candidates with evidence and actions.
An advanced example raises the ceiling alongside a large count for a wide exploratory slate.
Piping is appropriate only for a caller that captures the emitted result document, because input itself is passed through argv.
JSON output is the stable choice when another agent will inspect settings, warnings, and handoffs.
If an example fails, preserve the same goal and correct the named setting before changing the reasoning budgets.

```text
vidbyte-cli agents suggest run --goal "{goal}" --max-output-tokens 4000
vidbyte-cli --json agents suggest run --goal "{goal}" --max-output-tokens 16000 --count 12
```

**Related commands for Max Output Tokens**
Use agents suggest categories --view-all when the caller needs to choose a reasoning lens before running.
Use --max-total-tokens when the concern is aggregate run spend rather than per-turn size.
Use --count when the slate itself should be smaller rather than each reply shorter.
Use dry-run when the request shape and file manifest need inspection without credentials or model usage.
Use agents suggest handoff only after a result document exists and a specific idea identifier has been selected.
These commands share the same result conventions but do not imply that one command can authorize another.

**Failure modes for Max Output Tokens**
A non-positive or oversized value fails before the provider is loaded because the request dataclass requires a meaningful boundary.
A non-integer value fails as invalid input instead of becoming a silently rounded ceiling.
A ceiling too small for the slate produces truncated or invalid artifacts, which surface as provider or validation outcomes.
A provider or schema failure is reported as a provider failure and is never converted into a false budget stop.
Recover by correcting the specific value named by the error, rerunning dry-run when useful, and preserving the same intent.

**Authentication and permissions for Max Output Tokens**
This ceiling itself does not grant access to files, providers, accounts, repositories, or execution tools.
Integer values are available to local validation without credentials, while model-backed runs still require the configured provider.
The ceiling shapes how much of the caller's provider budget one turn may spend but changes no permission.
Read-only deny-all settings apply to generator and critic agents so suggestions cannot mutate the host through this workflow.
Permission failures should be repaired at the provider boundary rather than by weakening the output contract.
