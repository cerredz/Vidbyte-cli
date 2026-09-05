# Design Doc: Persistence Runtime Primitive Scaffold

**Status:** Draft
**Author:** Claude
**Created:** 2026-09-05
**Last Updated:** 2026-09-05

---

## 1. Overview

This adds `vidbyte-cli runtime persistence`, the third local runtime primitive after
`adversarial-team`. It gives an agent-driven caller a settings surface for a "persistence
guard" — a future executor that will refuse to let a native coding-agent session stop, feeding
it a fixed continuation prompt plus its original task some bounded number of times, controlled
by a six-tier `--strength` setting. This PR builds the settings, validation, and typed launch
plan; it reuses `adversarial-team`'s established shape (host discovery, launch planning, typed
failures) and stops at the same explicit, unimplemented executor boundary that primitive
already established, rather than inventing a parallel mechanism or a different boundary.

---

## 2. Goals & Non-Goals

### Goals

- Add a `persistence` command under the existing `runtime` group.
- Expose the caller-facing settings as real CLI input: task, host, and a `--strength` tier
  from 1 to 6 — validated before anything else happens.
- Generalize `RuntimeLaunchPlan.capability_id` and `RuntimeLaunchPlanner.build()` to carry an
  explicit capability id per primitive instead of a single hardcoded literal, so a third
  primitive does not require re-deriving host/working-directory/task validation.
- Add `PersistenceStrength` and `PersistenceSettings` as typed, bounded contracts, with the
  six-tier-to-repeat-count mapping fixed as a reviewable constant.
- Reuse the existing credential, HTTP, idempotency, output, and error systems unchanged.
- Stop at an explicit `PersistenceExecutionNotImplemented` boundary before requesting paid
  admission or constructing any provider client — mirroring `RuntimeExecutionNotImplemented`
  exactly.
- Add zero new Python package dependencies.

### Non-Goals

- Implementing the actual continuation loop, or launching any native host process. That is a
  separate future PR, gated on the same external prerequisite every other runtime primitive in
  this repository is gated on: a `vidbyte-sdk` (or subprocess-based) mechanism for driving a
  native Codex/Claude/OpenCode session turn by turn does not exist anywhere in this
  workspace today, and adding one is out of scope here — see Section 3.
- Adding `vidbyte-sdk` as a `vidbyte-cli` dependency, for the same reason `adversarial-team`
  and the uncommitted `same-host-ensemble` draft both explicitly excluded it: nothing in this
  release imports code that does not exist yet on that package's own `main`.
- Deciding the exact wording of the canned continuation phrase the future executor will send
  ("Nice job, I think you can do better...", plus the original task). That is presentation
  content for the executor PR, not a CLI validation concern; this PR only fixes the *shape*
  (a bounded strength tier that resolves to a repeat count) and the *boundary* (stops before
  ever constructing that phrase).
- Reconciling the admission route path this PR wires (`/api/x402/runtime/persistence/admissions`)
  against `vidbyte`'s already-declared `/api/x402/runtime/same-host-ensemble/activate` naming
  convention. Both are provisional, unmounted, and inconsistent with each other; see Section 12.
- New `tests/` files. This repository's established convention for a scaffold-shaped PR of this
  kind is verification through `scripts/run_ci.py` plus updating the existing structural
  surface test, not a new bespoke test file — see Section 10.

---

## 3. Background & Context

- `vidbyte-cli` `main` (PR #23, merged) already built the local-runtime shell: `runtime list`,
  `runtime doctor`, `runtime adversarial-team`, and the `lib/runtime_primitives/` package
  (`hosts.py`, `planner.py`, `executor.py`). Its own design doc
  (`docs/design/local-runtime-primitives-scaffold.md`) explicitly scoped out "any runtime
  algorithm" and left `RuntimeExecutor.execute_adversarial_team` raising
  `RuntimeExecutionNotImplemented`. That stub is still unfilled — this PR does not fill it,
  it adds a second, equally stubbed command next to it (a third primitive overall, since an
  uncommitted `same-host-ensemble` design draft also exists locally but has not been
  implemented or merged).
- `vidbyte-cli`'s `pyproject.toml` depends only on `click`, `httpx`, `keyring`, `platformdirs`,
  and `pydantic` — no `vidbyte-sdk` dependency, and no subprocess-based native-agent driver of
  any kind exists anywhere in this repository today. Every runtime primitive in this codebase,
  without exception, currently stops before the point where it would need one.
- `vidbyte`'s x402 catalog (a separate repository, currently on an open, unmerged branch) has
  already declared a first "runtime" bucket entry, `runtime.same-host-ensemble@1`, at a flat,
  non-metered 2-cent admission price — establishing the payment model this second primitive's
  catalog counterpart will also use (see the companion `vidbyte` PR). That catalog entry's own
  design rationale is explicit that Vidbyte's backend never executes, sees, or prices the local
  work itself; it only charges a flat fee to license one local invocation. This CLI-side PR is
  consistent with that model: it validates and plans locally, and the future executor's paid
  admission call (wired but unreachable) is the only backend touchpoint.
- The field guide (`field-guide/vidbyte-cli/`) establishes house rules this design follows: one
  `CliError` subclass per failure in `lib/errors/failures.py` (never a bare constructor), no
  templated file-header comments (a 3–6 line module docstring instead), no module-level helper
  functions sitting outside a class, and touching only the files this design doc assigns.
- `scripts/test_research_only_surface.py` asserts an exact `runtime` command surface
  (`EXPECTED_RUNTIME = {"adversarial-team", "doctor", "list"}`). This PR must add `"persistence"`
  to that set and must not reintroduce any of the `FORBIDDEN_SOURCE_TOKENS` left over from the
  deleted backend-dispatch harness system.

---

## 4. Requirements

### Functional Requirements

1. `vidbyte-cli runtime persistence <task> [options]` must validate every input and build a
   `RuntimeLaunchPlan` plus a `PersistenceSettings` value before reaching the executor boundary.
2. `--host {auto,codex,claude,opencode}` must be the only accepted values, resolved exactly as
   `adversarial-team` resolves them (auto prefers Codex, then Claude, then OpenCode).
3. `--strength {1,2,3,4,5,6}` must be required-with-a-default (default `1`), validated by
   Click's own `IntRange(1, 6)` before the command body runs, and must resolve to a fixed
   repeat count via `PersistenceSettings.repeat_count`:

   | Strength | Repeat count |
   |---|---:|
   | 1 | 3 |
   | 2 | 8 |
   | 3 | 20 |
   | 4 | 40 |
   | 5 | 70 |
   | 6 | 100 |

4. `RuntimeLaunchPlan.capability_id` must widen from a single hardcoded `Literal` to a
   `Literal` union naming every known capability id; every existing construction site must name
   its own id explicitly rather than relying on a default.
5. `RuntimeLaunchPlanner.build()` must accept a `capability_id` parameter instead of hardcoding
   one, with `adversarial_team.py`'s existing call site updated to pass its own id explicitly.
6. The command must reach `RuntimeExecutor.execute_persistence(plan, settings)`, which must
   raise `PersistenceExecutionNotImplemented` unconditionally, before any admission request or
   process is created, regardless of which valid host or strength was selected.
7. `RuntimeEndpoints` must expose a future-ready `admit_persistence` operation analogous to
   `admit_adversarial_team`, unreachable from the scaffold executor.
8. `--help` and `--version` must remain free of filesystem, credential, and network side
   effects.
9. `scripts/test_research_only_surface.py` must be updated to expect the new command and must
   continue to pass with no forbidden tokens reintroduced.

### Non-Functional Requirements

- No environment values, API keys, prompts, or subprocess output may appear in error metadata
  (matching the existing `RuntimeHostUnavailable`-style failures).
- All new Pydantic models reject extra fields and are frozen, matching `RuntimeLaunchPlan`'s
  existing convention.
- Every new function/method signature occupies one line, immediately followed by a one- to
  two-line comment (existing repo-wide convention, reaffirmed in PR #23's own requirements).
- Existing Ruff, strict mypy, compile, smoke, build, and installed-wheel gates remain required;
  `python scripts/run_ci.py` must exit 0.

---

## 5. High-Level Design

`commands/runtime/persistence.py` adds a third static command next to `adversarial_team.py`,
registered in the same `commands/runtime/__init__.py` and `commands/__init__.py`. It resolves
the host exactly as `adversarial-team` does, resolves `--strength` into a `PersistenceSettings`
value, and reuses `RuntimeLaunchPlanner.build()` — generalized to accept a `capability_id` — to
produce a `RuntimeLaunchPlan`. It then calls
`RuntimeExecutor.execute_persistence(plan, settings)`, a new method that raises
`PersistenceExecutionNotImplemented` before any side effect, mirroring
`execute_adversarial_team`'s existing stub exactly.

```text
[agent caller via shell]
        |
        v
[persistence command] -> [resolve --strength] -> [PersistenceSettings]
        |
        v
[host registry] -> [launch planner (capability_id="runtime.persistence@1")]
        |
        v
[executor.execute_persistence: STOP -> PersistenceExecutionNotImplemented]
        |
        +-> [admit_persistence endpoint: wired, not called by scaffold]

Future executor PR (blocked on a native-agent driving mechanism that exists nowhere yet):
  admission grant -> native host turn 1 -> inject canned continuation + original task
  -> native host turn 2 -> ... -> repeat_count turns total -> normalized result
```

No change touches `lib/runtime/context.py`: `runtime_launch_planner()` and
`runtime_executor()` already return primitive-agnostic instances, so the existing lazy
factories serve a third primitive without modification.

---

## 6. Detailed Design

### 6.1 Generalized Launch Plan and Persistence Settings

**File(s):** `src/vidbyte_cli/types/runtime.py`
**Type:** Modified

#### What it does

Widens `RuntimeLaunchPlan.capability_id` from a single hardcoded `Literal` to a two-member
`Literal` union so the same frozen plan type serves both primitives without duplicating
host/working-directory/task validation. Adds the persistence-specific strength contract.

#### Interface / API

```python
class RuntimeLaunchPlan(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid", frozen=True)
    capability_id: Literal["runtime.review.adversarial-team@1", "runtime.persistence@1"]
    host: RuntimeHost
    executable: Path
    working_directory: Path
    task: str = Field(min_length=1, max_length=20_000)


class PersistenceStrength(IntEnum):
    """The six caller-facing persistence tiers."""

    TIER_1 = 1
    TIER_2 = 2
    TIER_3 = 3
    TIER_4 = 4
    TIER_5 = 5
    TIER_6 = 6


_PERSISTENCE_REPEAT_COUNTS: Mapping[PersistenceStrength, int] = {
    PersistenceStrength.TIER_1: 3,
    PersistenceStrength.TIER_2: 8,
    PersistenceStrength.TIER_3: 20,
    PersistenceStrength.TIER_4: 40,
    PersistenceStrength.TIER_5: 70,
    PersistenceStrength.TIER_6: 100,
}


class PersistenceSettings(BaseModel):
    """Bounded, frozen persistence-primitive settings for a future executor."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    strength: PersistenceStrength

    @property
    def repeat_count(self) -> int:
        # Resolves the caller-facing tier to the fixed continuation-turn count.
        return _PERSISTENCE_REPEAT_COUNTS[self.strength]
```

#### Logic / Algorithm

1. Replace the single-literal `capability_id` field with the two-member union above; the
   existing `adversarial_team.py` call site names its own literal explicitly (see 6.2).
2. Add `PersistenceStrength`/`PersistenceSettings` as plain data contracts with one derived
   property and no other behavior — validated once at construction, never mutated.
3. Keep `_PERSISTENCE_REPEAT_COUNTS` a private module constant, not a method on a class with no
   state of its own, per the field guide's restraint rule.

#### Edge Cases & Error Handling

- `PersistenceStrength` is a closed `IntEnum`; an out-of-range `--strength` value is rejected
  by Click's own `IntRange(1, 6)` before this type is ever constructed, so no dedicated
  `CliError` subclass is needed for that case (matching how `--host` relies on `click.Choice`
  rather than a custom "bad choice" failure).
- A fourth primitive extends the `capability_id` `Literal` union directly — this is the
  intended, minimal seam, matching the restraint rule against introducing a `StrEnum` before a
  third distinct member actually needs one.

### 6.2 Launch Planner Generalization

**File(s):** `src/vidbyte_cli/lib/runtime_primitives/planner.py`,
`src/vidbyte_cli/commands/runtime/adversarial_team.py`
**Type:** Modified

#### What it does

Accepts a capability id parameter instead of hardcoding one, so both primitives share the same
host-resolution and working-directory validation without duplicating it.

#### Interface / API

```python
class RuntimeLaunchPlanner:
    def build(
        self,
        task: str,
        host: RuntimeHost | None,
        cwd: Path,
        capability_id: Literal["runtime.review.adversarial-team@1", "runtime.persistence@1"],
    ) -> RuntimeLaunchPlan: ...
```

#### Logic / Algorithm

1. Existing host resolution, working-directory validation, and task-bounds logic is unchanged.
2. The resolved `RuntimeLaunchPlan` is constructed with the passed-in `capability_id` instead
   of the removed module-level `_CAPABILITY_ID` constant.
3. `adversarial_team.py`'s existing call site is updated to pass
   `"runtime.review.adversarial-team@1"` explicitly — the only change required there.

#### Edge Cases & Error Handling

- No behavioral change to task/host/directory validation; this is a pure parameter-threading
  change.

### 6.3 Persistence Command

**File(s):** `src/vidbyte_cli/commands/runtime/persistence.py`
**Type:** New file

#### What it does

Registers `vidbyte-cli runtime persistence`, resolves `--host` and `--strength`, and reaches
the executor boundary — mirroring `adversarial_team.py`'s shape exactly, with one added option.

#### Interface / API

```python
class PersistenceCommand:
    def register(self, parent: click.Group) -> None: ...
    def execute(
        self, context: ApplicationContext, task: str, host: str, strength: int
    ) -> None: ...
```

#### Logic / Algorithm

1. Register `persistence` with a required `task` argument, `--host` (same
   `click.Choice(("auto", *hosts))` as `adversarial-team`), and `--strength`
   (`click.IntRange(1, 6)`, default `1`, `show_default=True`).
2. Resolve `host` to `None` (auto) or a `RuntimeHost` exactly as `adversarial-team` does.
3. Build the plan via `context.runtime_launch_planner().build(task, requested, Path.cwd(),
   "runtime.persistence@1")`.
4. Construct `PersistenceSettings(strength=PersistenceStrength(strength))`.
5. Call `context.runtime_executor().execute_persistence(plan, settings)`.

#### Edge Cases & Error Handling

- Identical task/host/directory failure modes as `adversarial-team`
  (`RuntimeTaskInvalid`, `RuntimeHostUnavailable`, `RuntimeWorkingDirectoryInvalid`) — none are
  duplicated; all are reused from `lib/errors/failures.py` as-is.
- `--strength` out of `[1, 6]` fails at Click's parse boundary with the usual usage-error exit
  code, before any service is touched — consistent with how an invalid `--host` string already
  behaves.

### 6.4 Executor Stub and Endpoint

**File(s):** `src/vidbyte_cli/lib/runtime_primitives/executor.py`,
`src/vidbyte_cli/lib/api/endpoints/runtime.py`
**Type:** Modified

#### What it does

Adds the same-shape inert boundary `adversarial-team` already has, plus the matching
not-yet-called admission endpoint method.

#### Interface / API

```python
class RuntimeExecutor:
    def execute_adversarial_team(self, plan: RuntimeLaunchPlan) -> NoReturn: ...
    def execute_persistence(
        self, plan: RuntimeLaunchPlan, settings: PersistenceSettings
    ) -> NoReturn: ...


class RuntimeEndpoints:
    def admit_adversarial_team(
        self, request: AdmissionRequest, key: str
    ) -> AdmissionGrant: ...
    def admit_persistence(self, request: AdmissionRequest, key: str) -> AdmissionGrant: ...
```

#### Logic / Algorithm

1. `execute_persistence` accepts the validated plan and settings only to fix the future
   implementation seam, then unconditionally raises `PersistenceExecutionNotImplemented`.
2. `admit_persistence` POSTs to `/api/x402/runtime/persistence/admissions` — this route path is
   provisional and does not match `vidbyte`'s already-declared
   `/api/x402/runtime/same-host-ensemble/activate` naming convention; see Section 12.

#### Edge Cases & Error Handling

- Both new methods are exercised by the smoke/offline check the same way
  `execute_adversarial_team`/`admit_adversarial_team` already are — reachable and typed, never
  invoked end-to-end.

### 6.5 Agent-Native Failure

**File(s):** `src/vidbyte_cli/lib/errors/failures.py`
**Type:** Modified

#### What it does

Adds one `CliError` subclass for the new failure, following the field guide's typed-failures
rule exactly — no bare `CliError(...)`, no reuse of `RuntimeExecutionNotImplemented`'s message
for a different primitive.

#### Interface / API

```python
class PersistenceExecutionNotImplemented(CliError):
    code = CliErrorCode.NOT_IMPLEMENTED
    exit_status = ExitCode.OPERATIONAL_FAILURE

    def __init__(self) -> None: ...
```

#### Logic / Algorithm

1. Fixes `code`, `exit_status`, and its own static `message`/`description`/`trace`/`hint`,
   matching `RuntimeExecutionNotImplemented`'s existing shape and wording pattern exactly, with
   "persistence" in place of "adversarial-team" throughout.
2. `hint` points at `runtime list` for published capability metadata, exactly as the
   adversarial-team equivalent does.

#### Edge Cases & Error Handling

- `ErrorHandler.handle`'s single `match` needs no new `case` — this is a `CliError` subclass
  and already falls under the existing base-class case.

---

## 7. Data Model Changes

### 7.1 CLI-Local Types

**Change type:** New/Modified (Python types only, no persisted schema)

Covered fully in Section 6.1. No database, no CLI-persisted config schema changes.

**Migration strategy:** N/A — additive Python types; existing credentials/configuration
untouched.

---

## 8. API Changes

### 8.1 `POST /api/x402/runtime/persistence/admissions`

**Change type:** New consumer, not invoked by this scaffold

**Request:**

```json
{
  "client_runtime_version": "1",
  "host": "codex | claude | opencode"
}
```

**Response:**

```json
{
  "admission_id": "opaque string",
  "capability_id": "runtime.persistence@1",
  "execution_location": "local",
  "charged_cents": 2,
  "admitted_at": "RFC 3339 timestamp"
}
```

**Error cases:** identical to `adversarial-team`'s admission route (400/422 invalid host or
version, 401/403 auth/scope, 402 wallet funding required, 409 idempotency conflict, 429 rate
limited, 503 unavailable) — reusing the exact contract `RuntimeAdmissionRequest`/
`RuntimeAdmissionGrant` already define.

This route's existence and exact path depend on the `vidbyte` backend actually mounting a
`runtime` route family, and on reconciling this path's `/admissions` suffix against the
already-declared `/activate` suffix on the ensemble entry — see Section 12. This PR wires the
client-side call shape only.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/persistence-runtime-primitive-scaffold.md` | This design doc |
| CREATE | `src/vidbyte_cli/commands/runtime/persistence.py` | New command: strength/host resolution, launch plan, executor call |
| MODIFY | `src/vidbyte_cli/commands/runtime/__init__.py` | Register the new command in the `runtime` group |
| MODIFY | `src/vidbyte_cli/commands/__init__.py` | Register `PersistenceCommand` alongside the other runtime commands |
| MODIFY | `src/vidbyte_cli/commands/runtime/adversarial_team.py` | Pass `"runtime.review.adversarial-team@1"` explicitly to the generalized planner |
| MODIFY | `src/vidbyte_cli/types/runtime.py` | Widen `capability_id`; add `PersistenceStrength`/`PersistenceSettings` |
| MODIFY | `src/vidbyte_cli/lib/runtime_primitives/planner.py` | `build()` takes `capability_id` |
| MODIFY | `src/vidbyte_cli/lib/runtime_primitives/executor.py` | Add `execute_persistence` stub |
| MODIFY | `src/vidbyte_cli/lib/api/endpoints/runtime.py` | Add `admit_persistence` |
| MODIFY | `src/vidbyte_cli/lib/errors/failures.py` | Add `PersistenceExecutionNotImplemented` |
| MODIFY | `scripts/test_research_only_surface.py` | Expect `persistence` in `EXPECTED_RUNTIME` |
| MODIFY | `README.md` | Document the new command and its strength tiers |
| MODIFY | `docs/architecture.md` | Update the local runtime primitives section for a second stubbed executor |

---

## 10. Verification

This repository's established convention for a scaffold-shaped runtime-primitive PR — set by
both the merged `adversarial-team` PR and the uncommitted `same-host-ensemble` draft — is to
verify through the existing gate rather than add a new per-feature test file:

- `python -m pip install -e ".[dev]"`, then `python scripts/run_ci.py` (lint, format check,
  strict mypy, compileall, smoke, distribution build, Twine check, clean-wheel install) must
  exit 0.
- `python scripts/test_research_only_surface.py` must pass with `EXPECTED_RUNTIME` updated to
  include `"persistence"`, and must not report any of `FORBIDDEN_SOURCE_TOKENS` reintroduced.
- Manual check: `python -m vidbyte_cli runtime persistence --help` and
  `python -m vidbyte_cli runtime persistence "test task" --strength 3` (offline, no
  credentials) both terminate with the typed `PersistenceExecutionNotImplemented` failure and
  never attempt a network call — verified the same way `adversarial-team`'s equivalent
  behavior is exercised by `check_help_tree`/`check_command_surface`.

No new `tests/` or `scripts/test-*.py` file is added, per the Non-Goals in Section 2.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Vidbyte backend | `/api/x402/runtime`, `/api/x402/runtime/persistence/admissions` | Capability discovery, future paid admission | Route/path not final until the `vidbyte` catalog entry and a real mounted route reconcile (Section 12) |
| Codex/Claude/OpenCode executables | User-installed | Future native-agent hosts | Same discovery mechanism as `adversarial-team`; no new risk |

No new Python package dependency is added. A native-agent-driving mechanism (whether a future
`vidbyte-sdk` dependency or a subprocess-based driver) is an explicit future dependency of the
follow-up executor PR, not this one.

---

## 12. Open Questions

- [ ] This PR's `admit_persistence` targets `/api/x402/runtime/persistence/admissions`, but
  `vidbyte`'s already-declared `runtime.same-host-ensemble@1` catalog entry uses
  `/api/x402/runtime/same-host-ensemble/activate` — a different suffix convention
  (`/admissions` vs. `/activate`). These need reconciling to one convention before either
  admission route is actually mounted; tracked here, not resolved by this PR.
- [ ] Exact non-interactive invocation contract for driving a native host turn by turn, once
  the executor is actually implemented (the same open question the `adversarial-team` and
  `same-host-ensemble` designs both left unresolved).
- [ ] The exact wording of the canned continuation phrase, and whether it should be
  caller-configurable or fixed. This PR only fixes the strength-tier-to-repeat-count shape;
  the phrase itself is future executor-PR content.
- [ ] Whether the flat admission price should scale with `--strength` (a strength-6 run means
  up to 100 local host turns, versus a bounded single fan-out/fan-in round for the ensemble
  primitive) or stay flat regardless of tier. This is a `vidbyte` catalog decision, not a CLI
  concern, and is left open in the companion `vidbyte` PR.

---

## 13. Alternatives Considered

### Alternative 1: Wait for a native-agent-driving mechanism to exist before starting any of this

- What: Defer this entire PR until `vidbyte-sdk` (or some subprocess-based driver) can actually
  hold a multi-turn conversation with a native host, then build the full CLI surface and real
  execution together.
- Why rejected: The CLI settings surface — strength tiers, host selection, task validation —
  has zero dependency on that mechanism actually existing, exactly as `adversarial-team`
  already demonstrated. Building it now, stopped at the same honest boundary every other
  runtime primitive in this repository already uses, delivers agent-controllable settings today
  instead of blocking on unstarted work in a different repository.

### Alternative 2: Give the persistence command its own launch-plan type instead of generalizing `RuntimeLaunchPlan`

- What: Add a parallel `PersistenceLaunchPlan` rather than widening `capability_id`.
- Why rejected: `RuntimeLaunchPlanner`'s host-resolution and working-directory validation is
  identical for both primitives; duplicating it into a second type just to avoid a one-field
  widening fails this repo's own restraint rule ("a stateless single-use helper is a private
  method, not a collaborator class") applied one level up — here, a duplicated type instead of
  a generalized field.

### Alternative 3: Make the six strength tiers directly settable as a raw repeat count

- What: Expose `--repeat-count N` instead of `--strength {1..6}`.
- Why rejected: this was the explicit product shape requested — six named tiers, not an
  unbounded integer — and a raw count invites an unbounded value that the future executor would
  have to defend against on its own. Fixing the six values as a closed enum keeps that ceiling
  enforced at the type level instead of by convention.
