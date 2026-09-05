# Build Decisions

The ordered set of decisions to make when building a specialized agent or runtime primitive on
the Vidbyte SDK. Each one has a default that is right most of the time and a named condition for
departing from it. Work through them in order — later decisions depend on earlier ones.

---

## 1. Which host, and is there actually an adapter?

**Decide:** which native coding agent runs this.

**Default:** Codex. It is the only host with a merged `CodexHarnessAgent`, verified native thread
forking, and per-fork sandbox control.

**Depart when:** a real adapter for another host exists and its fork and sandbox behavior is
verified. Not when the control matrix says a host *could* work — `ClaudeHarnessAgent` does not
exist, and OpenCode has no fork equivalent at all.

**Trap:** offering a host in `click.Choice` that no adapter serves. The command then accepts a
flag it cannot honor, which is worse than not offering it.

---

## 2. What is the caller allowed to set?

**Decide:** the input surface.

**Default:** one frozen Pydantic model holding every option, with bounds on the model.

**Trap:** passing `Mapping[str, object]` around and pulling values out with `.get()`. It defers
every type error to runtime and leaves the accepted surface undocumented.

**Rule:** bounds belong on the model, not only on the Click decorator. A bound on Click holds for
the terminal; a bound on the model holds for every caller.

**Rule:** anything with a closed set of values is an enum — hosts, reasoning efforts, confidence
levels. A string field with a docstring listing valid values is not validation.

---

## 3. What must the caller *not* be allowed to set?

**Decide:** which settings are invariants rather than options.

**Default:** anything whose weakening defeats the primitive's purpose.

**Worked example:** `same-host-ensemble` does not expose sandbox mode. Read-only proposal roles
and one write-enabled implementer is what makes "propose, don't commit" true. A flag letting a
caller give proposal roles write access would let them turn off the one property they are paying
for. It is not a missing feature; it is the design.

**Ask:** if a caller set this to its most permissive value, would the primitive still be the
thing we described? If not, it is not an option.

---

## 4. Where do the prompts come from?

**Decide:** authored, generated, or both.

**Default:** author the prompts for fixed stages; generate the prompts for stages whose count or
character depends on the task.

**Worked example:** the ensemble's planner, selector, and implementer prompts are authored —
those roles are the same every run. The proposal roles' prompts are generated, because which
perspectives a task needs depends entirely on the task. A database migration and a CSS refactor
do not want the same three reviewers.

**Rule:** prompts live in their own Markdown file, one prompt per file, never inline in the
logic and never in a Python string. Prompt text is prose and is reviewed as prose; a `.py` file
full of adjacent string literals hides which words actually changed. Ship them as package data
or the wheel installs the code without them.

**Rule:** an authored system prompt gets `identity`, `goal`, `checklist`, `things-not-to-do`,
`instructions-and-output`, and `examples` sections, wrapped in XML tags. Identity first, because
everything after is read through it; the most consequential constraints last, because attention
is strongest at the beginning and end. Keep `checklist` and `things-not-to-do` disjoint — the
first is what to verify about the finished output, the second is failures of authorship that
re-reading the output would not reveal.

**Rule:** `instructions-and-output` names the exact keys the stage must return, including any
count bounds, even though the schema already declares them. `OutputSchemaFormatter.annotate`
strips `minItems`, `maxItems`, `minLength`, and `maxLength` out of the wire schema and folds them
into property descriptions, because no provider grammar enforces them. Say it in the prompt or it
reaches the model only as a description, and a count violation costs a whole failed stage.

**Rule:** a generated system prompt is specified as a schema, not as free text. The ensemble's
`GeneratedRole` requires `identity`, `personality`, `knowledge`, and `goal`, so a planner that
omits one fails validation instead of producing a thin prompt nobody notices.

**Rule:** never let a generated prompt carry a safety constraint. Append those yourself, after
assembly. A planner that generates a role encouraging edits must still produce a read-only fork.

---

## 5. How does information move between stages?

**Decide:** structured output or prose.

**Default:** structured, whenever the next consumer is code or another agent.

**Why:** the receiving stage's job is usually to compare and reconcile. A schema makes conflict
mechanically visible — two proposals listing the same file with different approaches is
detectable. Prose makes it a reading comprehension task the model may fail silently.

**Rule:** `extra="forbid"` on every schema. A model that invents fields should fail validation,
not be silently half-parsed.

**Rule:** include the fields that make disagreement visible. `files` exists on `RoleProposal`
specifically so overlap is detectable; `confidence` exists so the implementer can be told, in
its own prompt, that self-reported confidence is not evidence.

**Rule:** `output_schema` belongs to the agent, not to the turn. `CodexVidbyteTranslator`
resolves it once at construction, so a stage that needs two different shapes needs two agents. A
multi-turn stage — the ensemble's selector runs one turn per narrowing round — gets one schema
covering every round, which is what lets those rounds share a thread and see their own earlier
reasoning.

**Rule:** identifiers an agent must echo back are assigned by your code, never by the model. The
ensemble numbers each candidate `<role index>.<approach index>` before the selector sees it, so a
reply naming an id that was not on offer is a detectable failure rather than a silent
substitution.

---

## 6. Fan out, or chain?

**Decide:** whether stages run independently or feed each other.

**Default:** fan out from one root, concurrently.

**Why:** independence keeps errors decorrelated, which is the entire statistical reason an
ensemble beats a single agent. Chaining means a bad early framing contaminates everyone
downstream, and it serializes work the fork API parallelizes for free.

**Depart when:** a stage genuinely cannot start without a previous stage's output. The
implementer is chained after the proposals because it has to be; the proposals are not chained to
each other because they do not have to be.

**Rule:** the fan-in stage forks from the **root**, not from one of the fan-out branches.
Forking from a branch inherits that branch's framing and quietly reintroduces the correlation you
fanned out to avoid.

---

## 7. What happens when one branch fails?

**Decide:** the partial-failure policy, explicitly.

**Default:** survivable branches are recorded and stepped over; the run aborts only when nothing
survived.

**Why:** two proposals out of three still beats one agent. Aborting the whole run throws away
work the caller already paid for.

**Rule:** stages whose output everything else depends on — a planner, an implementer — are not
survivable. Their failure ends the run with its own typed error.

**Rule:** bound every concurrent branch with `asyncio.timeout`. One hung host must not hold the
fan-in open indefinitely.

**Rule:** `asyncio.CancelledError` is never converted into a failure record. Re-raise it, or
Ctrl-C stops working.

**Rule:** report failures in the result document with a closed reason vocabulary. Never put a
provider exception message there — it can quote workspace paths and prompt text.

---

## 8. When is the caller charged?

**Decide:** where admission sits in the sequence.

**Default:** after every free local check, before the first agent runs.

**Order:** input validation → SDK availability → host discovery → **admission** → execution.

**Why:** a user with no Codex installed, or an SDK too old to have the integration, must not pay.
Every check that can fail for free must run first.

**Rule:** one idempotency-keyed purchase per invocation, so a retried HTTP request is not charged
twice.

**Rule:** report `charged_cents` in the result. The caller should be able to see what a run cost
without consulting the backend.

---

## 9. How does it fail out loud?

**Decide:** the failure vocabulary.

**Default:** one `CliError` subclass per distinct failure in `lib/errors/failures.py`, each
fixing `code`, `exit_status`, and `retryable`, and carrying its own `message`, `description`,
`trace`, and `hint`.

**Why:** agents are this CLI's heaviest callers and have no transcript to fall back on. The
`description` tells them what was and was not done and whether retrying helps; the `trace`
describes the code path before the raise.

**Rule:** never construct a bare `CliError(...)` at a call site, and never write a module-level
`def some_error(...) -> CliError` factory.

**Rule:** no task text, prompt body, file path, environment value, or provider message in
`message`, `description`, `trace`, or `hint`. The private `cause` field is where a provider
exception goes, and no renderer serializes it.

**Rule:** say explicitly whether money was spent. "No admission was requested and no process
started" is the single most useful sentence in a pre-payment failure.

---

## 10. Can it be installed?

**Decide:** how the SDK dependency is declared.

**Default:** an optional extra, imported lazily.

**Why:** the published `vidbyte-sdk` release predates the Codex integration, and `run_ci.py`
installs the built wheel into a clean virtualenv and runs `--help`, which imports every command
module. A module-scope import fails the gate.

**Check:** `pip download vidbyte-sdk==<version> --no-deps` and inspect the wheel before assuming
a symbol ships. Do not trust that a merged PR is a published one.

**Rule:** convert both `ImportError` and `AttributeError`. A too-old SDK imports fine and is
missing the symbol.

**Rule:** declare a `[[tool.mypy.overrides]]` with `ignore_missing_imports` for the optional
module, and give the service its own `Protocol` for the surface it drives, so the type checker
still has something real to check against.
