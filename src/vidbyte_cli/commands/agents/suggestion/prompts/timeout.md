**Timeout**
Timeout bounds elapsed wall-clock time across generation, critique, and curation in one run.
It protects callers from an open-ended suggestion cycle when model responses are slow.
The deadline prevents new work after expiration but does not promise cancellation inside an in-flight provider request.
The last committed snapshot remains the safe fallback whenever the deadline arrives.
A time-limited result names its stopping reason so partial completion cannot resemble ordinary success.

**Purpose of Timeout**
The purpose of Timeout is to give the caller one explicit deadline over the whole workflow.
That deadline keeps a run against a slow provider from blocking the caller indefinitely.
It also makes latency predictable before any model work starts, because the worst-case wait is bounded up front.
The deadline works alongside the independent turn, token, edit, and round limits rather than replacing them.
When the clock runs out, the run stops with the `time_limit` stop reason and the last committed snapshot.

**When not to use Timeout**
Do not set Timeout merely because the option exists when the caller has no latency requirement.
Omit it when the run may take as long as it needs under the other budgets.
Do not use this deadline to bound token spend, turn count, or idea count, because dedicated options govern each of those.
Use a narrower budget option when the concern is specifically tokens, turns, edits, or refinement passes.
Avoid very short deadlines for large slates, because generation alone needs real provider latency before anything exists.

**Timeout inputs**
The value is one positive integer of seconds up to 86400 whenever it is specified.
A single value is supplied per run, and repeated occurrences are not combined into a longer deadline.
Whitespace and shell quoting do not change the meaning, while a non-integer value is rejected before provider work.
The command does not reinterpret the number as anything other than a wall-clock deadline for this run.
Values outside the supported range fail fast at the request boundary with a typed input error.

**Defaults and precedence for Timeout**
When it is omitted, no deadline is enforced and the run proceeds under the other budgets alone.
Command-line values are the only source for this deadline, and the run does not read a separate configuration document.
Environment variables do not silently populate this setting, which keeps an invocation reproducible.
An explicit value always takes precedence over omission for exactly one run.
The token, turn, edit, and round limits still apply independently inside the deadline.

**Timeout output contract**
Timeout is not printed as a separate progress message because stdout is reserved for the command result.
For a model-backed run, the effective deadline travels inside the validated settings carried by the result envelope.
For dry-run output, the manifest records the requested deadline without spending any provider turn.
Human output summarizes the resulting suggestions, while JSON and JSONL output preserve the stop reason and warnings.
A timed-out stop reports `time_limit` with the committed snapshot, so partial completion cannot resemble ordinary success.

**How to use Timeout**
Use the command below as the smallest valid invocation shape for this value.
Replace the brace-delimited placeholder with the caller's actual integer while preserving shell quoting around spaces.
Combine the option with a precise goal because the deadline bounds time rather than defining the task.
Budget the deadline from expected turns multiplied by realistic per-turn provider latency plus headroom.
Raise the deadline whenever extra compute is enabled, since the parallel fan-out adds generation latency.
The command remains a single argv-built request and does not require a temporary configuration file.

```text
vidbyte-cli agents suggest run --goal "{goal}" --timeout-seconds 600
```

**Examples for Timeout**
A minimal example supplies only the required goal and leaves the run without a deadline.
A normal example sets a ten-minute deadline that comfortably covers two refinement rounds.
An advanced example allows a long window for extra compute across many categories with large evidence.
Piping is appropriate only for a caller that captures the emitted result document, because input itself is passed through argv.
JSON output is the stable choice when another agent will inspect the stop reason, warnings, and handoffs.
If an example fails, preserve the same goal and correct the named setting before changing the reasoning budgets.

```text
vidbyte-cli agents suggest run --goal "{goal}" --timeout-seconds 300
vidbyte-cli --json agents suggest run --goal "{goal}" --timeout-seconds 3600 --extra-compute
```

**Related commands for Timeout**
Use agents suggest categories --view-all when the caller needs to choose a reasoning lens before running.
Use --max-agent-calls when the concern is turn count rather than elapsed time.
Use --max-total-tokens when the concern is token spend rather than latency.
Use dry-run when the request shape and file manifest need inspection without credentials or model usage.
Use agents suggest handoff only after a result document exists and a specific idea identifier has been selected.
These commands share the same result conventions but do not imply that one command can authorize another.

**Failure modes for Timeout**
A non-positive or oversized value fails before the provider is loaded because the request dataclass requires a meaningful boundary.
A non-integer value fails as invalid input instead of becoming a silently rounded deadline.
Reaching the deadline mid-run is not an error: the run returns the committed snapshot with the `time_limit` reason.
A provider or schema failure is reported as a provider failure and is never converted into a false deadline stop.
Recover by correcting the specific value named by the error, rerunning dry-run when useful, and preserving the same intent.

**Authentication and permissions for Timeout**
This deadline itself does not grant access to files, providers, accounts, repositories, or execution tools.
Integer values are available to local validation without credentials, while model-backed runs still require the configured provider.
The deadline limits how long one run may take but does not change what any turn may do.
Read-only deny-all settings apply to generator and critic agents so suggestions cannot mutate the host through this workflow.
Permission failures should be repaired at the provider boundary rather than by weakening the time contract.
