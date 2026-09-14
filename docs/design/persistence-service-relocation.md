# Design Doc: Persistence Service Relocation

**Status:** Draft
**Author:** Claude
**Created:** 2026-09-07
**Last Updated:** 2026-09-07

---

## 1. Overview

The `runtime persistence` primitive's implementation — the Codex agent adapter, its two
authored prompts, and the persistence-only execution boundary — currently lives inside
`src/vidbyte_cli/lib/runtime_primitives/`, mixed in with the generic admission, host
discovery, and launch-planning plumbing that `runtime adversarial-team` and
`runtime same-host-ensemble` also depend on. This change moves the persistence agent into
`src/vidbyte_cli/services/persistence/`, the feature-service layer that PR #34 established
for `services/ensemble/`, and leaves the shared plumbing in `lib/`. Nothing about how the
command behaves changes: same admission sequence, same prompts, same turn counts, same
output.

---

## 2. Goals & Non-Goals

### Goals

- Move every module whose only reason to exist is the persistence Codex agent out of `lib/`
  and into `services/persistence/`.
- Give persistence the same package shape as `services/ensemble/`: a `runner.py` the command
  calls after admission, a `prompts/` subpackage holding every authored prompt as Markdown,
  and a loader class that fills `{{placeholder}}` slots.
- Remove the last `lib/` → persistence-implementation coupling, so the dependency rule stated
  in `services/README.md` and in `lib/runtime_primitives/executor.py`'s own docstring holds
  for every primitive, not just for the ensemble.
- Keep the two prompts inside the built wheel, verified by the existing `run_ci.py` check.
- Keep behavior identical: the same system prompt, the same continuation text, the same
  admission-before-execution ordering, the same progress vocabulary on stderr.

### Non-Goals

- Not moving `gate.py`, `hosts.py`, `planner.py`, or `verification.py`. Those are shared by
  `adversarial-team` and `same-host-ensemble`; filing them under one product's service would
  make the ensemble command import the persistence service to get an admission gate.
- Not changing the admission protocol, the price table, the HMAC verification, the strength
  tiers, or any wire type in `types/runtime.py`.
- Not changing prompt wording. The files move and one is renamed; their text is untouched.
- Not adding a command, an endpoint, or a backend route.
- Not touching `services/ensemble/`, which merged in PR #34 and defines the conventions this
  change follows.

---

## 3. Background & Context

`lib/` is documented as "reusable client-platform mechanisms … independent of any one product
capability" (`src/vidbyte_cli/lib/README.md`). `lib/runtime_primitives/persistence.py` is the
opposite of that: it is one product's algorithm, holding a `CodexHarnessAgent`, the fixed
continuation loop, the turn timeout, and the two prompts a model actually reads.

PR #34 introduced `src/vidbyte_cli/services/` for exactly this kind of code and stated the
dependency rule in `services/README.md`: *a service may import from `lib/` and `types/`;
nothing in `lib/` may import a service, and no service may import a command.* The ensemble
primitive was built directly in that layer. Persistence predates it and never moved.

The seam shows today in `lib/runtime_primitives/executor.py`. Its docstring already explains
that `same-host-ensemble` is "deliberately absent: it runs in `services/ensemble/`, because a
service may depend on `lib/` while nothing in `lib/` may depend on a service" — and then, four
lines down, the same file does `from .persistence import PersistentCodexSession as Session`
and defines `execute_persistence`, which validates
`plan.capability_id != "runtime.persistence@1"`. That is a product-specific method, holding a
concrete reference to a product-specific class, inside the shared substrate.

**Current state.** `lib/runtime_primitives/` contains nine files:

| File | Scope | Consumers |
|---|---|---|
| `persistence.py` | persistence only | `executor.py`, `commands/runtime/persistence.py` |
| `persistence_system.md` | persistence only | `persistence.py` |
| `continuation.md` | persistence only | `persistence.py` |
| `executor.py` | mixed — `execute_adversarial_team` + `execute_persistence` | `ApplicationContext`, two commands |
| `gate.py` | shared | persistence + same-host-ensemble commands |
| `verification.py` | shared | `gate.py` |
| `hosts.py` | shared | `ApplicationContext`, doctor |
| `planner.py` | shared | `ApplicationContext`, three commands |
| `__init__.py` | shared | `ApplicationContext` |

**Constraints.**

- `scripts/run_ci.py` is the only gate, and it asserts both prompt files are present and
  non-empty inside the built wheel at a hard-coded path.
- `pyproject.toml` declares the prompts as package data. The field guide records that a
  missing `package-data` glob passes every gate and fails on an installed copy's first turn.
- The field guide's *Agent Stage Prompts* rules apply to "any text a model will read, anywhere
  under `services/`": one prompt per Markdown file at
  `<service>/prompts/<stage>_<system|turn>.md`, loaded through a loader class using literal
  `{{token}}` replacement rather than `str.format`, with an `__init__.py` in the prompts
  package so the data directory cannot shadow a module.
- Strict mypy, ruff with `E,F,I,UP,B,C90`, and a 100-character line length.

---

## 4. Requirements

### Functional Requirements

1. `PersistentCodexSession` is importable from `vidbyte_cli.services.persistence.session` and
   is no longer importable from `vidbyte_cli.lib.runtime_primitives.persistence`.
2. The persistence system prompt is at `services/persistence/prompts/persistence_system.md`
   and the continuation prompt at `services/persistence/prompts/persistence_turn.md`, with
   their text unchanged.
3. A `PersistencePrompts` loader class in `services/persistence/prompts/library.py` reads both
   files through `importlib.resources` against an explicitly named anchor package and fills
   `{{original_task}}` by literal replacement.
4. No Python file under `services/persistence/` contains a sentence addressed to a model.
5. The persistence execution boundary lives in `services/persistence/runner.py` as
   `PersistenceRunner`, which refuses to start a session unless the supplied verdict is
   admitted, matches the plan's capability, carries a non-empty admission id, and the plan is
   a Codex `runtime.persistence@1` plan.
6. `RuntimeExecutor` keeps `execute_adversarial_team` and exposes the verdict check as a
   public `require_verdict`, so the persistence runner reuses it rather than restating it.
7. `RuntimeExecutor` no longer imports anything from `services/`, and no module under `lib/`
   does.
8. `commands/runtime/persistence.py` builds the session and the runner from
   `services/persistence/` and keeps the current ordering: validate the key, build the plan,
   load the SDK, buy one admission, verify it, then run.
9. `runtime doctor`, `runtime list`, `runtime adversarial-team`, and
   `runtime same-host-ensemble` are unaffected, and still reach `gate.py`, `hosts.py`,
   `planner.py`, and `executor.py` at their existing `lib/runtime_primitives/` paths.
10. Both prompts ship inside the built wheel under `vidbyte_cli/services/persistence/prompts/`.
11. `lib/runtime_primitives/` retains exactly the five shared modules plus `__init__.py`; the
    persistence modules and prompts are deleted from it.

### Non-Functional Requirements

- **Performance:** unchanged. Prompt reads stay cached per session instance; there is one
  additional module import at command time and no additional file read.
- **Scalability:** N/A — a single-process CLI invocation.
- **Security:** the credential-filtering behavior in `commands/runtime/persistence.py` is
  untouched; the environment override map still blanks every known provider variable and sets
  only `OPENAI_API_KEY`. No prompt or path change may cause a secret to be read or printed.
- **Observability:** the stderr progress vocabulary in `lib/constants/runtime.py` is
  unchanged, and stdout remains results-only.
- **Reliability:** admission is still checked at the final boundary before any turn, and an
  SDK failure is still converted to the static `PersistenceHostFailed`.

---

## 5. High-Level Design

The move splits `lib/runtime_primitives/` along the line that already exists inside it: the
five modules every runtime primitive shares stay, and the three files only persistence uses
leave. `persistence.py` becomes `services/persistence/session.py` — renamed because
`services.persistence.persistence` is a stutter and the class it holds is
`PersistentCodexSession`. The two prompts move into `services/persistence/prompts/` beside a
`library.py` loader, matching `services/ensemble/prompts/` exactly; `continuation.md` is
renamed `persistence_turn.md` so the pair reads as the field guide's
`<stage>_<system|turn>.md` convention.

`execute_persistence` moves out of `RuntimeExecutor` and becomes `PersistenceRunner.run` in
`services/persistence/runner.py`, mirroring `EnsembleRunner.run`. This is what removes the
`lib/` → service import: the executor no longer needs to name `PersistentCodexSession` at
all. The verdict check itself does not move — it is shared with `execute_adversarial_team` —
so `RuntimeExecutor._require_verdict` is renamed to the public `require_verdict` and the
runner calls it. A service calling into `lib/` is the allowed direction.

The command's control flow is unchanged in order and in what is free versus paid. It still
builds the plan from `ApplicationContext`, prepares the SDK session before spending anything,
buys exactly one admission, verifies it online through `RuntimeAdmissionGate`, and only then
executes. The single edit is the last step:
`context.runtime_executor().execute_persistence(...)` becomes `PersistenceRunner().run(...)`.
`ApplicationContext` keeps `runtime_executor()`, which `adversarial-team` still uses.

```
commands/runtime/persistence.py
    |
    |-- context.runtime_launch_planner()   -> lib/runtime_primitives/planner.py -> hosts.py
    |-- context.runtime_endpoints()        -> lib/api/endpoints/runtime.py  [network]
    |-- RuntimeAdmissionGate.verify_online -> lib/runtime_primitives/gate.py -> verification.py
    |
    |-- PersistentCodexSession.prepare()   -> services/persistence/session.py
    `-- PersistenceRunner().run(...)       -> services/persistence/runner.py
              |                                   |
              |                                   `-- RuntimeExecutor.require_verdict()
              |                                          -> lib/runtime_primitives/executor.py
              `-- session.run()  -> prompts/library.py -> prompts/*.md -> vidbyte-sdk Codex
```

Key decisions:

- **Split rather than move wholesale.** Moving `gate.py` into `services/persistence/` would
  make `commands/runtime/same_host_ensemble.py` import the persistence service to obtain an
  admission gate, and would put host discovery — which `runtime doctor` uses with no primitive
  involved at all — under one product's name.
- **A runner, not a Protocol in the executor.** Typing `host:` as a locally declared Protocol
  would also break the `lib/` → service import, with a smaller diff, but it would leave a
  method whose body asserts `capability_id == "runtime.persistence@1"` inside the shared
  substrate. The ensemble precedent puts that code in the service.
- **Rename to `session.py` and `persistence_turn.md`.** Both names come from conventions the
  destination already enforces. They are the only renames; no other file changes name.

---

## 6. Detailed Design

### 6.1 Persistence service package marker

**File(s):** `src/vidbyte_cli/services/persistence/__init__.py`
**Type:** New file

#### What it does

Marks the package and states what it owns. It stays import-free, for the same reason
`services/ensemble/__init__.py` does: `runner.py` reaches the whole `lib/` stack, and
re-exporting it here would make importing `session` or a prompt drag that stack along.

#### Interface / API

```python
"""The persistence primitive: one Codex thread driven through a fixed continuation loop.

This module stays free of imports on purpose. Import `runner`, `session`, or
`prompts.library` directly, so reading a prompt never pulls in the command stack.
"""
```

#### Logic / Algorithm

None. Docstring only.

#### Edge Cases & Error Handling

N/A — no executable statements.

---

### 6.2 Prompt package marker

**File(s):** `src/vidbyte_cli/services/persistence/prompts/__init__.py`
**Type:** New file

#### What it does

Makes `prompts/` a real package. The field guide records why this file is mandatory: a data
directory sitting next to a same-named module shadows it, and the module then imports clean
while being dead.

#### Interface / API

```python
"""Both persistence prompts, as Markdown, plus the loader that fills their placeholders.

The `.md` files here are the prompts themselves — authored text, reviewed as prose rather
than as code. `library.py` holds the only Python in this package.
"""
```

#### Edge Cases & Error Handling

N/A.

---

### 6.3 Prompt loader

**File(s):** `src/vidbyte_cli/services/persistence/prompts/library.py`
**Type:** New file

#### What it does

Reads the two Markdown prompts out of the installed package and fills their placeholders. It
replaces the private `PersistentCodexSession._prompt` helper, which read files via
`files(__package__)` — an anchor that depends on where the module was imported from.

#### Interface / API

```python
class PersistencePrompts:
    def __init__(self) -> None: ...
    def system_prompt(self) -> str: ...
    def turn_prompt(self, original_task: str) -> str: ...
    def _render(self, name: str, **values: str) -> str: ...
    def _read(self, name: str) -> str: ...
```

#### Logic / Algorithm

1. `_read` resolves `resources.files("vidbyte_cli.services.persistence.prompts")`, joins
   `f"{name}.md"`, and reads it as UTF-8, caching the result on the instance.
2. `_render` reads the named prompt and applies `str.replace("{{" + key + "}}", value)` for
   each supplied value — a literal replace, never `str.format`, because prompt text may
   contain braces.
3. `system_prompt` returns `persistence_system` unrendered.
4. `turn_prompt` returns `persistence_turn` with `{{original_task}}` filled.

The anchor is written as a module-path string rather than `__package__`, so resolution does
not depend on how the module was imported. Text is returned exactly as stored — no `strip()`,
because the continuation prompt's trailing newline is part of what the model has been reading
since the primitive shipped.

#### Edge Cases & Error Handling

- **Prompt missing from the wheel:** `resources.files(...).read_text` raises
  `FileNotFoundError`. This is not caught: an installed package missing its own data is a
  packaging defect, and swallowing it would send an empty system prompt into a paid turn.
  `run_ci.py` asserts both files are in the wheel precisely so this cannot reach a user.
- **Task text containing `{{original_task}}`:** the replacement runs once over the template,
  so a literal placeholder inside the user's task is inserted as text and never re-expanded.
- **Task text containing braces or `%`:** unaffected, because substitution is `str.replace`.
- **Empty task:** cannot occur — `RuntimeLaunchPlanner.build` raises `RuntimeTaskInvalid`
  before a plan exists.
- **Repeat reads:** the per-instance cache means a 100-turn run reads each file once.

---

### 6.4 Persistence session

**File(s):** `src/vidbyte_cli/services/persistence/session.py`
**Type:** New file (moved from `src/vidbyte_cli/lib/runtime_primitives/persistence.py`)

#### What it does

Unchanged responsibility: owns one invocation's environment and `CodexHarnessAgent`, runs the
fixed continuation loop, and rejects incomplete or changed-thread results.

#### Interface / API

```python
class PersistentCodexSession:
    def __init__(self, environment: Mapping[str, str], progress: Callable[[str], None]) -> None: ...
    def prepare(self, plan: Plan) -> None: ...
    def run(self, plan: Plan, settings: PersistenceSettings) -> PersistenceResult: ...
    async def _run(self, plan: Plan, settings: PersistenceSettings) -> PersistenceResult: ...
    async def _turn(self, prompt: str) -> AgentMessage: ...
    def _session_id(self, reply: AgentMessage, previous: str) -> str: ...
    def _continuation_progress(self, index: int, count: int) -> Progress: ...
```

#### Logic / Algorithm

Identical to the current implementation. Only three things change:

1. Relative imports move up one level for `lib/`: `..constants.runtime` becomes
   `...lib.constants.runtime` and `..errors.failures` becomes `...lib.errors.failures`.
   `...types.runtime` is unchanged, because the new package sits at the same depth.
2. `self._prompt("persistence_system.md")` becomes `self._prompts.system_prompt()` and
   `self._prompt("continuation.md").replace("{{original_task}}", plan.task)` becomes
   `self._prompts.turn_prompt(plan.task)`.
3. The private `_prompt` method and the `importlib.resources.files` import are deleted;
   `__init__` gains `self._prompts = PersistencePrompts()`.

#### Edge Cases & Error Handling

Unchanged, and all of it is already covered by
`scripts/test-layered-runtime-admission-gate.py`:

- `run` before `prepare` raises `PersistenceHostFailed`.
- A reply that is not `completed`, has no `final_response`, has a blank `thread_id`, or whose
  `thread_id` differs from the first turn's raises `PersistenceHostFailed` and stops the loop.
- `CodexAgentError` and `TimeoutError` are converted to the static `PersistenceHostFailed`, so
  SDK diagnostics that may carry task content never reach the user.
- `asyncio.CancelledError` is not caught and stays cancellation.
- The turn timeout cancels `arun` so the SDK client unwinds before the loop continues.

---

### 6.5 Persistence runner

**File(s):** `src/vidbyte_cli/services/persistence/runner.py`
**Type:** New file (logic moved from `RuntimeExecutor.execute_persistence`)

#### What it does

The final admission boundary for persistence. It re-checks the verdict independently of the
command, confirms the plan is the Codex persistence plan the receipt was bought for, and only
then lets the session run.

#### Interface / API

```python
class PersistenceRunner:
    def __init__(self, executor: RuntimeExecutor | None = None) -> None: ...
    def run(self, plan: Plan, settings: Tier, session: Session, verdict: Verdict) -> Result: ...
```

#### Logic / Algorithm

1. `__init__` stores the shared `RuntimeExecutor`, defaulting to a new one, so the verdict
   policy has exactly one implementation across primitives.
2. `run` calls `self._executor.require_verdict(plan, verdict)`, which raises
   `RuntimeAdmissionNotVerified` on an absent, unadmitted, capability-mismatched, or
   blank-id receipt.
3. `run` then rejects a plan whose `capability_id` is not `runtime.persistence@1` or whose
   host is not `codex`, raising `RuntimeAdmissionNotVerified("persistence_plan_invalid")`.
4. `run` returns `session.run(plan, settings)`.

Both checks are ordered exactly as they are today, so the raised reason string for each
failure is unchanged.

#### Edge Cases & Error Handling

- **`verdict=None` or `admitted=False`:** raises before the session is touched.
- **Verdict for a different capability, or with a blank/whitespace `admission_id`:** raises.
- **A verdict that passes but a plan for another capability or host:** raises
  `persistence_plan_invalid` — this is the case where the receipt is real but was bought for
  something else.
- **Session failures:** propagate as `PersistenceHostFailed` from `session.run`; the runner
  adds no handling, so no failure is reclassified.

---

### 6.6 Runtime executor

**File(s):** `src/vidbyte_cli/lib/runtime_primitives/executor.py`
**Type:** Modified

#### What it does

Keeps the adversarial-team scaffold boundary and owns the one verdict policy every primitive
checks. It stops knowing that persistence exists.

#### Interface / API

```python
class RuntimeExecutor:
    def execute_adversarial_team(self, plan: Plan, verdict: Verdict | None = None) -> NoReturn: ...
    def require_verdict(self, plan: Plan, verdict: Verdict | None) -> None: ...
```

#### Logic / Algorithm

1. Delete `execute_persistence` and the `from .persistence import PersistentCodexSession`
   import, along with the now-unused `PersistenceResult` and `PersistenceSettings` aliases.
2. Rename `_require_verdict` to `require_verdict`. Its body does not change.
3. Update the module docstring: persistence now runs in `services/persistence/` for the same
   reason the ensemble does, which the docstring already explains.

#### Edge Cases & Error Handling

Unchanged. `execute_adversarial_team` still validates admission before raising
`RuntimeExecutionNotImplemented`, so the inert primitive cannot be used to skip the gate.

---

### 6.7 Persistence command

**File(s):** `src/vidbyte_cli/commands/runtime/persistence.py`
**Type:** Modified

#### What it does

Unchanged: parses arguments, validates the idempotency key, plans, prepares the SDK, buys and
verifies one admission, then runs.

#### Interface / API

Unchanged. `PersistenceCommand.register` and `PersistenceCommand.execute` keep their exact
signatures.

#### Logic / Algorithm

1. `from ...lib.runtime_primitives.persistence import PersistentCodexSession` becomes
   `from ...services.persistence.session import PersistentCodexSession`.
2. Add `from ...services.persistence.runner import PersistenceRunner`.
3. `from ...lib.runtime_primitives.gate import RuntimeAdmissionGate` is unchanged — the gate
   stays in `lib/`.
4. The final line changes from
   `context.runtime_executor().execute_persistence(plan, settings, session, verdict)` to
   `PersistenceRunner().run(plan, settings, session, verdict)`.

Everything before that line — the key regex, the plan, `PersistenceSettings`, the credential
filtering in `_session`, the admission call, the online verification — is untouched.

#### Edge Cases & Error Handling

Unchanged. A malformed idempotency key still raises `click.BadParameter` before credentials
are read; a missing `grant_token` and a rejected verdict still raise
`RuntimeAdmissionNotVerified` before execution; SDK preparation failure still precedes
payment.

---

### 6.8 Services README

**File(s):** `src/vidbyte_cli/services/README.md`
**Type:** Modified

#### What it does

Documents the second service beside `ensemble/`, in the same shape.

#### Logic / Algorithm

Add a `## persistence/` section after `## ensemble/` describing the primitive and listing
`runner.py`, `session.py`, and `prompts/`, and noting that admission, host discovery, and
launch planning stay in `lib/runtime_primitives/` because three primitives share them.

---

### 6.9 Packaging and gate

**File(s):** `pyproject.toml`, `scripts/run_ci.py`
**Type:** Modified

#### Logic / Algorithm

1. In `pyproject.toml`, `[tool.setuptools.package-data]` loses the
   `"vidbyte_cli.lib.runtime_primitives" = ["*.md"]` key and the `vidbyte_cli` list gains
   `"services/persistence/prompts/*.md"` beside the ensemble glob.
2. In `run_ci.py`, `_verify_installed_wheel` checks
   `vidbyte_cli/services/persistence/prompts/{persistence_system.md,persistence_turn.md}`.

#### Edge Cases & Error Handling

The field guide records the exact failure this guards: the clean-venv stage only runs
`--version` and `--help`, which import the command tree but read no data file, so a missing
prompt otherwise passes every gate and fails on an installed copy's first paid turn. Leaving
the stale `"vidbyte_cli.lib.runtime_primitives"` key in place would not fail the build — the
package still exists, it just has no `.md` files — which is why it is removed rather than
left as harmless.

---

### 6.10 Documentation references

**File(s):** `docs/architecture.md`, `AGENTS.md`, `src/vidbyte_cli/lib/constants/README.md`
**Type:** Modified

#### Logic / Algorithm

1. `docs/architecture.md`'s layer table: `lib/runtime_primitives/` is redescribed as shared
   host discovery, planning, admission, and the executor seam, and a
   `src/vidbyte_cli/services/` row is added.
2. `AGENTS.md`'s `services/` section gains one sentence naming `persistence/`.
3. `lib/constants/README.md` says agent orchestration belongs in `lib/runtime_primitives/`;
   it is corrected to name `services/` for agent orchestration and `lib/runtime_primitives/`
   for admission checks.

---

### 6.11 Verification script updates

**File(s):** `scripts/test-layered-runtime-admission-gate.py`
**Type:** Modified

#### Logic / Algorithm

1. Import `PersistentCodexSession` from `vidbyte_cli.services.persistence.session` and
   `PersistenceRunner` from `vidbyte_cli.services.persistence.runner`.
2. `test_executor_denial_prevents_all_turns` drives `PersistenceRunner().run(...)` for the
   persistence assertions and keeps `RuntimeExecutor().execute_adversarial_team(...)` for the
   adversarial-team one.
3. The timeout test's patch target becomes
   `vidbyte_cli.services.persistence.session.PersistenceLimit`.

Every assertion is preserved; only the symbol paths change.

---

## 7. Data Model Changes

N/A — no schema, collection, or wire type changes. `types/runtime.py` is untouched:
`PersistenceResult`, `PersistenceSettings`, `PersistenceStrength`, `RuntimeLaunchPlan`,
`RuntimeAdmissionGrant`, and `RuntimeAdmissionVerdict` keep their shapes and their location,
because `types/` is shared across `lib/`, `commands/`, and `services/` by design.

---

## 8. API Changes

N/A — no HTTP surface changes. `POST /runtime/admissions/persistence` and the grant
verification route are called in the same order, with the same request bodies, exactly once
per invocation.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/persistence-service-relocation.md` | This design doc |
| CREATE | `src/vidbyte_cli/services/persistence/__init__.py` | Import-free package marker |
| CREATE | `src/vidbyte_cli/services/persistence/runner.py` | Admission boundary moved out of `RuntimeExecutor` |
| CREATE | `src/vidbyte_cli/services/persistence/session.py` | Moved from `lib/runtime_primitives/persistence.py` |
| CREATE | `src/vidbyte_cli/services/persistence/prompts/__init__.py` | Required so the data dir cannot shadow a module |
| CREATE | `src/vidbyte_cli/services/persistence/prompts/library.py` | Loader class replacing `_prompt` |
| CREATE | `src/vidbyte_cli/services/persistence/prompts/persistence_system.md` | Moved, text unchanged |
| CREATE | `src/vidbyte_cli/services/persistence/prompts/persistence_turn.md` | Moved from `continuation.md`, text unchanged |
| DELETE | `src/vidbyte_cli/lib/runtime_primitives/persistence.py` | Now `services/persistence/session.py` |
| DELETE | `src/vidbyte_cli/lib/runtime_primitives/persistence_system.md` | Now under `services/persistence/prompts/` |
| DELETE | `src/vidbyte_cli/lib/runtime_primitives/continuation.md` | Now `prompts/persistence_turn.md` |
| MODIFY | `src/vidbyte_cli/lib/runtime_primitives/executor.py` | Drop `execute_persistence`; publish `require_verdict` |
| MODIFY | `src/vidbyte_cli/commands/runtime/persistence.py` | Import the session and runner from the service |
| MODIFY | `src/vidbyte_cli/services/README.md` | Document `persistence/` |
| MODIFY | `src/vidbyte_cli/lib/constants/README.md` | Correct the pointer to where orchestration lives |
| MODIFY | `pyproject.toml` | Move the prompt `package-data` glob |
| MODIFY | `scripts/run_ci.py` | Assert the prompts at their new wheel path |
| MODIFY | `scripts/test-layered-runtime-admission-gate.py` | New import paths and runner boundary |
| CREATE | `scripts/test-persistence-service-relocation.py` | Verification script for this change |
| MODIFY | `docs/architecture.md` | Layer table |
| MODIFY | `AGENTS.md` | Name the second service |

Unchanged and deliberately so:
`lib/runtime_primitives/{gate,hosts,planner,verification,__init__}.py`,
`lib/runtime/context.py`, `commands/runtime/{list,doctor,adversarial_team,same_host_ensemble}.py`,
`types/runtime.py`, `lib/constants/runtime.py`, `lib/errors/failures.py`, `services/ensemble/**`.

---

## 10. Testing Plan

This change must not alter behavior, so the plan has two halves: the existing contract suite
must pass unmodified except for symbol paths, and a new script must prove the relocation
itself is complete rather than half-done.

### Unit Tests

Existing, in `scripts/test-layered-runtime-admission-gate.py` — these keep their assertions
and are re-pointed at the new modules:

- `AdmissionContracts` → `test_executor_denial_prevents_all_turns` — asserts a `None` verdict,
  an unadmitted verdict, a capability-mismatched verdict, and a blank-id verdict each raise
  before any transport call, now through `PersistenceRunner` — [Hidden Assumption]
- `PersistenceContracts` → `test_all_strengths_keep_exact_task_and_session` — 6 through 100
  turns, exact task text preserved, thread reused, continuation prompt text intact —
  [Silent Failure]
- `PersistenceContracts` → `test_provider_configuration_and_working_directory_reach_sdk` —
  [Hidden Failure]
- `PersistenceContracts` → `test_incomplete_or_changed_thread_stops_continuation` —
  [Hidden Failure]
- `PersistenceContracts` → `test_sdk_failure_is_safe_and_stops_all_later_turns` —
  [Silent Failure]
- `PersistenceContracts` → `test_timeout_cancels_active_sdk_turn` — patch target moves —
  [Hidden Failure]
- `PersistenceContracts` → `test_cancellation_remains_cancellation` — [Hidden Failure]
- `PersistenceCommandContracts` → `test_one_admission_and_final_stdout_only` — [Silent Failure]
- `PersistenceCommandContracts` → `test_bad_receipt_never_starts_agent` — [Hidden Assumption]
- `PersistenceCommandContracts` → `test_sdk_preparation_failure_precedes_payment` —
  [Hidden Assumption]

New, in `scripts/test-persistence-service-relocation.py`:

- `RelocationContracts` → `it('imports the session and runner from services.persistence')` —
  [Edge Case]
- `RelocationContracts` → `it('no longer exposes lib.runtime_primitives.persistence')` —
  asserts `ModuleNotFoundError`, because a leftover module would let a stale import keep
  working and hide an incomplete move — [Silent Failure]
- `RelocationContracts` → `it('leaves no .md file under lib/runtime_primitives')` — the source
  tree, not the import graph: an orphaned prompt would still be found by a stale reader —
  [Silent Failure]
- `RelocationContracts` →
  `it('finds no runtime_primitives.persistence reference in src or scripts')` — a textual
  sweep, because a patch target inside a string literal is invisible to the import machinery
  and to mypy — [Hidden Failure]
- `LayeringContracts` → `it('has no module under lib/ importing from services')` — parses
  every file under `src/vidbyte_cli/lib/` with `ast` and fails on any absolute or relative
  import resolving into `services`; this is the rule the whole change exists to restore —
  [Hidden Assumption]
- `LayeringContracts` → `it('has no service importing a command')` — the other half of the
  documented direction, checked the same way — [Hidden Assumption]
- `PromptContracts` → `it('renders the system prompt identically to the pre-move file')` —
  compares against the text committed at `main`, so a whitespace change during the move is
  caught — [Silent Failure]
- `PromptContracts` → `it('fills the continuation placeholder with the exact original task')`
  — a task containing `{`, `}`, `%s`, CRLF, and non-ASCII text, proving literal replacement —
  [Edge Case]
- `PromptContracts` → `it('does not re-expand a literal placeholder inside the task')` — a
  task that itself contains `{{original_task}}` must appear once, as text — [Silent Failure]
- `PromptContracts` → `it('leaves no unfilled placeholder in a rendered turn prompt')` —
  [Silent Failure]
- `PromptContracts` → `it('caches each prompt file and reads it once per instance')` —
  [Edge Case]
- `PromptContracts` → `it('resolves prompts through the named anchor, not __package__')` —
  loads the module under a different name and asserts it still reads — [Hidden Assumption]
- `PromptContracts` → `it('contains no model-addressed sentence in any service .py file')` —
  the field guide's own check, `grep '"You are'` generalized — [Hidden Assumption]
- `PackagingContracts` → `it('declares the prompt glob in package-data')` — parses
  `pyproject.toml` and asserts the new glob is present and the stale key is gone —
  [Silent Failure]
- `PackagingContracts` → `it('asserts the new wheel prompt paths in run_ci')` —
  [Silent Failure]
- `RunnerContracts` →
  `it('raises persistence_plan_invalid for a valid receipt on a wrong plan')` — verdict
  admitted, plan capability wrong: the case where the receipt is genuine but bought for
  something else — [Silent Failure]
- `RunnerContracts` → `it('raises for a codex-hosted plan with a non-persistence capability')`
  — [Edge Case]
- `RunnerContracts` → `it('raises for a persistence capability on a non-codex host')` —
  [Edge Case]
- `RunnerContracts` → `it('never calls the session when the verdict is rejected')` — asserts a
  spy session recorded zero calls, not merely that an exception was raised — [Silent Failure]
- `RunnerContracts` → `it('shares one verdict policy with RuntimeExecutor')` — asserts the
  runner delegates to `RuntimeExecutor.require_verdict` rather than restating it, so the two
  boundaries cannot drift — [Hidden Failure]
- `ExecutorContracts` → `it('no longer defines execute_persistence')` — [Silent Failure]
- `ExecutorContracts` → `it('still denies adversarial-team without a verdict')` —
  [Hidden Assumption]

### Integration Tests

- **Command end to end with faked transport:** already covered by
  `PersistenceCommandContracts`, which drives `PersistenceCommand.execute` with a real
  `ApplicationContext`, a mocked endpoint group, and a recording transport. It is the flow
  that proves the new runner is actually wired in — a command still calling the old path would
  fail its admission-count assertion.
- **Mocked vs. real:** the Vidbyte SDK is real (its translator and agent run); only
  `CodexTransport` and the HTTP endpoint group are faked. Nothing contacts the network.
- **Silent failure paths between components:** the dangerous one is a prompt that loads but is
  empty or stale — the run would succeed, cost money, and produce worse output with no error.
  `PromptContracts` compares rendered text against the pre-move bytes, and `run_ci.py` asserts
  non-empty prompts inside the wheel.
- **Hidden assumptions only integration surfaces:** that `importlib.resources` resolves the
  prompts from an *installed* package, not from the checkout. Unit tests run against the
  source tree and cannot see this; `run_ci.py`'s clean-venv wheel install is what covers it,
  which is why the wheel path assertion is part of this change rather than an afterthought.

### Manual / QA Test Cases

1. Given a clean venv with the built wheel installed, when running
   `python -c "from vidbyte_cli.services.persistence.prompts.library import PersistencePrompts; print(len(PersistencePrompts().system_prompt()))"`,
   then it prints a non-zero length — [Hidden Assumption: prompts resolve from the wheel]
2. Given the same install, when running
   `python -c "import vidbyte_cli.lib.runtime_primitives.persistence"`, then it fails with
   `ModuleNotFoundError` — [Silent Failure: a stale module left behind]
3. Given no `codex` binary on `PATH`, when running `vidbyte-cli runtime persistence "task"`,
   then it fails with the host-unavailable error before any admission call — [Edge Case]
4. Given a valid login and `--strength 1`, when running the command, then stdout carries only
   the final text, stderr carries every progress phase, and exactly one admission is charged —
   [Silent Failure: a double charge or leaked progress on stdout]
5. Given `vidbyte-cli runtime doctor`, `runtime list`, and `runtime same-host-ensemble --help`,
   when run after the move, then all three behave as before, proving the shared plumbing was
   not disturbed — [Hidden Failure: collateral damage to the other primitives]

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| `vidbyte-sdk[codex]` | pinned at `6f9f84a2` | `CodexHarnessAgent`, Codex dataclasses, `CodexAgentError` | None added — the same lazy, in-method imports move with the file |
| `setuptools` | `>=77` | Ships the prompts as package data | A wrong glob silently drops the prompts; guarded by the `run_ci.py` wheel check |
| Vidbyte API | `POST /runtime/admissions/persistence`, grant verification | Paid admission | Unchanged — same routes, same order, same count |

---

## 12. Rollout & Deployment

- **Feature flags:** none. This is a source relocation with no runtime switch.
- **Breaking change:** not for CLI users — no command, option, output field, or exit code
  changes. It is breaking for anyone importing
  `vidbyte_cli.lib.runtime_primitives.persistence` as a library, which is internal-only: the
  package exposes a console script, `PersistentCodexSession` is not re-exported from any
  `__init__.py`, and the only importers are in this repository.
- **Migration path:** none needed. Both symbol moves are mechanical and are applied in the
  same commit as the deletions, so no revision exists where an import is dangling.
- **Deployment order:** single repository, single artifact. No backend coordination — the
  admission routes are untouched.
- **Rollback:** revert the merge commit. There is no persisted state, no migration, and no
  wire change to undo.
- **Known conflict surface:** the open branches `feat/task-board`, `feat/stages-runtime`, and
  `feat/runtime-payment-methods` were all cut before this move and reference
  `lib/runtime_primitives/persistence.py`. Each will need the same two import rewrites when it
  rebases. `feat/task-board`'s design doc plans `lib/runtime_primitives/task_board.py` and a
  stage prompt beside it; after this change, that primitive belongs in `services/task_board/`.
  This is called out here so those rebases are expected rather than discovered.

---

## 13. Open Questions

- [ ] Should `PersistenceResult`, `PersistenceSettings`, and `PersistenceStrength` move from
      `types/runtime.py` to a `types/persistence.py`, mirroring `types/ensemble.py`? Left in
      place for now: `types/` is shared by design and splitting it is a separate change with
      its own churn.
- [ ] `feat/task-board` plans a new primitive under `lib/runtime_primitives/`. Should that
      branch be retargeted at `services/task_board/` before it opens, or after it merges?
- [ ] `RuntimeExecutor` now holds one inert primitive and one shared policy method. If
      `adversarial-team` is ever implemented as a service too, the class reduces to
      `require_verdict` alone and would be better named for that. Not acted on here.

---

## 14. Alternatives Considered

### Alternative 1: Move the whole folder into `services/persistence/`

- **What:** relocate all nine files, delete `lib/runtime_primitives/` entirely.
- **Why rejected:** `gate.py` is imported by `commands/runtime/same_host_ensemble.py`, and
  `hosts.py`/`planner.py`/`executor.py` are built by `ApplicationContext` for `runtime doctor`
  and `runtime adversarial-team`. The ensemble command would import the persistence service to
  obtain an admission gate, and `lib/runtime/context.py` would import a service — the exact
  rule `services/README.md` states and this change exists to restore. It would also force the
  three context factories out into the commands, a larger and unrelated refactor.

### Alternative 2: Keep `execute_persistence` in `RuntimeExecutor`, typed against a Protocol

- **What:** declare a local `PersistenceSession(Protocol)` in `executor.py` so the concrete
  import disappears while the method stays.
- **Why rejected:** it removes the import but not the coupling. A method whose body asserts
  `plan.capability_id != "runtime.persistence@1"` is product code, and it would sit in the
  shared substrate directly under a docstring explaining why product code does not belong
  there. `services/ensemble/runner.py` already set the precedent for where this goes.

### Alternative 3: Move only the two `.md` files, leaving `persistence.py` in `lib/`

- **What:** the smallest possible change satisfying the prompt-location convention.
- **Why rejected:** it splits one primitive across two layers, so the module reading a prompt
  lives further from it than before, and it leaves the `lib/` → product coupling untouched.

### Alternative 4: Move the whole folder to `services/runtime/`

- **What:** relocate all nine files under a shared `services/runtime/` package instead of a
  per-product one.
- **Why rejected:** it renames the layering problem instead of fixing it. Host discovery,
  planning, and the admission gate are platform mechanisms used by primitives, commands, and
  `ApplicationContext` alike — `lib/` is where the repository already documents that such
  mechanisms live, and `runtime doctor` uses `hosts.py` with no primitive involved at all.

---

END OF DESIGN DOC
