**Goal**
Goal is the named goal value that this command accepts for one suggestion workflow.
It gives the parent agent a stable way to state the outcome the caller wants the suggestion agent to advance.
This value is required for a run. Supplying it is helpful when the additional signal can change the next action.
The command keeps this value as caller task data and does not treat it as an instruction to execute work.
The value is carried into the bounded request with its source and semantic identity intact.
A precise value gives the generator and independent critic more signal than a broad label or an unstated assumption.

**Purpose of Goal**
The purpose of Goal is to make the outcome the caller wants the suggestion agent to advance explicit before candidate generation starts.
That explicit record lets the workflow compare ideas against the situation the caller actually described.
It also lets the critic explain whether a candidate is supported, missing evidence, or in conflict.
The field is most valuable when its content changes feasibility, novelty, timing, risk, or the definition of progress.
A short accurate statement is more useful than a long narrative that hides the decision-relevant fact.
The resulting ideas should refer to this signal only when the connection is material and explain why it matters.

**When not to use Goal**
Do not provide Goal merely because the option exists or because an empty value would look complete.
Omit it when the caller has no reliable signal of this kind and let the workflow mark the context as missing.
Do not use this field to smuggle execution instructions, credentials, private data, or a second command configuration.
Use a narrower context option when the statement has a clearly different meaning such as a risk, decision, or prohibition.
Avoid repeating the goal or copying an entire unrelated transcript because repetition lowers the signal available to the critic.
If the caller is unsure whether the record is current, state that uncertainty in the value rather than presenting it as a fact.

**Goal inputs**
The value is one trimmed nonempty string up to 4096 characters.
Repeated occurrences remain separate records so the agent can cite and compare them without parsing a delimiter.
Whitespace around a value is trimmed at the request boundary, while an empty value is rejected before provider work.
The command does not reinterpret the content as an identifier unless the option contract explicitly says it is one.
Use plain caller-readable text and keep each record focused on one fact, choice, boundary, or result.
The input is bounded before it enters the agent context so oversized content becomes an explicit truncation or omission.
A caller should keep related facts separate when their provenance, confidence, or expected effect differs enough to influence review.

**Defaults and precedence for Goal**
There is no useful implicit goal because the agent cannot infer the caller's intended outcome safely..
Command-line values are the only source for this field, and the run does not read a separate configuration document.
Environment variables do not silently populate this context value, which keeps an invocation reproducible.
When multiple values are supplied, their command-line order becomes their stable context order.
Explicit caller input therefore takes precedence over absence, while other settings such as count and rounds remain independent.
The result manifest records what was supplied and whether the bounded value was included, truncated, or omitted.
Use the manifest and warnings to distinguish absence from an explicitly bounded value when a downstream agent needs to explain why a suggestion changed.

**Goal output contract**
Goal is not printed as a separate progress message because stdout is reserved for the command result.
For a model-backed run, the value appears inside the fresh managed context window used by the relevant agent.
For dry-run output, the manifest exposes source identity and bounded character information without exposing file bodies by default.
Human output summarizes the resulting suggestions, while JSON and JSONL output preserve stable machine-readable fields.
Errors go to the CLI error channel as typed envelopes with a repair-oriented description and no secret echo.
The field influences ideas and handoffs but never grants authority, starts work, or changes the caller's permissions.

**How to use Goal**
Use the command below as the smallest valid invocation shape for this value.
Replace each brace-delimited placeholder with the caller's actual text while preserving shell quoting around spaces.
Repeat the option when more than one independent record should be supplied.
Combine the option with a precise goal because the field is evidence or context rather than a standalone task.
Add category and budget options only when they answer a real selection or resource question.
The command remains a single argv-built request and does not require a temporary configuration file.
Keep the invocation close to the caller's actual decision so another agent can reproduce the request without guessing omitted context, quoting, or precedence.

```text
vidbyte-cli agents suggest run --goal "{goal}"
```

**Examples for Goal**
A minimal example supplies only the required goal and leaves this optional signal absent when it has no value.
A normal example adds one focused record that directly changes how the next action should be judged.
An advanced example repeats the option for several independent records and combines it with a selected category.
Piping is appropriate only for a caller that captures the emitted result document, because input itself is passed through argv.
JSON output is the stable choice when another agent will inspect identifiers, manifests, warnings, and handoffs.
If an example fails, preserve the same goal and correct the named input or path before changing the reasoning settings.

```text
vidbyte-cli agents suggest run --goal "{goal}"
vidbyte-cli --json agents suggest run --goal "{goal}" --goal "{value}"
```

**Related commands for Goal**
Use agents suggest categories --view-all when the caller needs to choose a reasoning lens before running.
Use agents suggest categories --view {category-id} when one category needs a fuller conceptual definition.
Use the other context options when the signal is more accurately a decision, constraint, risk, or current commitment.
Use agents suggest handoff only after a result document exists and a specific idea identifier has been selected.
Use dry-run when the request shape and file manifest need inspection without credentials or model usage.
These commands share the same result conventions but do not imply that one command can authorize another.
Choose the narrowest neighboring command that answers the immediate question, then return to this option when the run itself needs the signal.

**Failure modes for Goal**
A missing required value fails before the provider is loaded because the request dataclass requires a meaningful boundary.
An empty repeated value fails as invalid input instead of becoming a misleading blank context record.
An unsupported path, malformed JSON file, directory, or unreadable file fails with a typed context error.
An oversized value is truncated only within the documented bound and the result records that status as a warning.
A provider or schema failure is reported as a provider failure and is never converted into a false no-suggestions result.
Recover by correcting the specific value named by the error, rerunning dry-run when useful, and preserving the same intent.

**Authentication and permissions for Goal**
This input itself does not grant access to files, providers, accounts, repositories, or execution tools.
Text values are available to local validation without credentials, while model-backed runs still require the configured provider.
The --files option reads only paths explicitly named by the caller and does not scan a workspace or agent history.
Read-only deny-all settings apply to generator and critic agents so suggestions cannot mutate the host through this workflow.
Provider credentials are used only when a real model-backed run is requested and are never copied into result prose.
Permission failures should be repaired at the provider or filesystem boundary rather than by weakening the context contract.
