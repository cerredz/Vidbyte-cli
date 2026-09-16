**Dry Run**
Dry Run validates and resolves the complete request without invoking any model.
It exposes settings, manifest entries, omissions, and warnings before reasoning incurs cost or latency.
File bodies stay out of the result by default while source identity and inclusion status remain inspectable.
This makes large or sensitive context sets easier to audit safely before spending provider budget.
No provider credentials or token usage are required for this validation path.

**Purpose of Dry Run**
The purpose of Dry Run is to prove the request is well-formed before it can spend anything.
That proof covers goal validity, context bounds, category selection, file readability, and every budget.
It also shows the caller exactly what the model would see, minus the model itself.
The validation uses the same dataclass and builder as a real run, so a passing dry run means the request shape is sound.
The result contains no ideas and clearly identifies dry-run completion as its stopping reason.

**When not to use Dry Run**
Do not use Dry Run when the caller actually needs suggestions, because validation alone produces no ideas.
Omit it for routine runs whose shape is already known to be valid.
Do not use this flag to preview idea quality, because no generation or critique happens.
Use a real run when the question is what the model thinks rather than whether the request parses.
Avoid treating a passing dry run as evidence about provider health, since no provider is contacted.

**Dry Run inputs**
The value is a boolean flag that takes no argument.
Presence enables validation-only mode, while absence runs the normal model-backed workflow.
The flag combines freely with every other option, and all of them are still validated.
Shell quoting does not apply, while an unexpected flag value is rejected before any work.
The command treats the flag as a mode switch for exactly one invocation.

**Defaults and precedence for Dry Run**
When it is omitted, the default is off and the run proceeds to model-backed generation.
Command-line presence is the only source for this mode, and the run does not read a separate configuration document.
Environment variables do not silently enable validation mode, which keeps an invocation reproducible.
An explicit flag always takes precedence over the default for exactly one run.
All other settings keep their own defaults and are validated as if a real run were starting.

**Dry Run output contract**
Dry Run reserves stdout for results only, while progress and diagnostics travel on the error channel.
Human output reports no suggestions with the dry-run status for quick scanning.
JSON and JSONL output emit the versioned envelope with settings, manifest, missing context, warnings, and the dry-run stop reason.
The manifest exposes source identity and bounded character information without exposing file bodies by default.
Errors arrive as typed machine envelopes with a repair-oriented description and no secret echo.

**How to use Dry Run**
Use the command below as the smallest valid invocation shape for this flag.
Combine the flag with the full intended option set so validation covers the real request.
Inspect the manifest and warnings before launching the corresponding real run.
Correct any flagged input and rerun validation until the request is clean.
Remove the flag only when validation passes and the caller is ready to spend provider budget.
The command remains a single argv-built request and does not require a temporary configuration file.

```text
vidbyte-cli agents suggest run --goal "{goal}" --dry-run
```

**Examples for Dry Run**
A minimal example validates only the required goal with every other default in place.
A normal example validates a realistic request with context records, categories, and budgets.
An advanced example validates file-backed context and JSON output shape for another agent to consume.
Piping is appropriate only for a caller that captures the emitted result document, because input itself is passed through argv.
JSON output is the stable choice when another agent will inspect the manifest, settings, and warnings.
If an example fails, correct the named input or path and revalidate before changing the reasoning settings.

```text
vidbyte-cli agents suggest run --goal "{goal}" --dry-run
vidbyte-cli --json agents suggest run --goal "{goal}" --trajectory "{value}" --files ./notes.md --dry-run
```

**Related commands for Dry Run**
Use agents suggest categories --view-all when the caller needs to choose a reasoning lens before running.
Use agents suggest categories --view {category-id} when one category needs a fuller conceptual definition.
Use a real run without the flag once validation passes and ideas are actually needed.
Use agents suggest handoff only after a result document exists and a specific idea identifier has been selected.
Use the budget options to right-size the validated request before spending anything.
These commands share the same result conventions but do not imply that one command can authorize another.

**Failure modes for Dry Run**
An invalid goal, unreadable file, unknown category, or out-of-range budget fails validation with a typed error.
A validation failure spends nothing and names the specific value to correct.
File bodies are never required for validation, so missing bodies are not failures.
A provider or credential problem cannot surface here, because no provider is contacted.
Recover by correcting the specific value named by the error and revalidating with the same intent.

**Authentication and permissions for Dry Run**
This mode requires no credentials, because it never contacts a provider.
The --files option still reads only paths explicitly named by the caller for manifest purposes.
Validation itself grants no access beyond reading the named inputs to bound and fingerprint them.
Read-only handling applies throughout, so validation cannot mutate the host through this workflow.
Permission failures should be repaired at the filesystem boundary rather than by weakening the validation contract.
