# Design Doc: Same-Host Ensemble Runtime Primitive Scaffold

**Status:** Draft
**Author:** Claude
**Created:** 2026-09-05
**Last Updated:** 2026-09-05

---

## 1. Overview

This adds `vidbyte-cli runtime same-host-ensemble`, the second local runtime primitive after
`adversarial-team`. It gives an agent-driven caller full command-line control over a
role-differentiated fan-out/fan-in ensemble — how many roles, what each role's framing is,
what the implementer's framing is, which native host runs it, and which model/reasoning
settings apply — while stopping at an explicit, typed boundary before any admission request
or agent process starts. It reuses `adversarial-team`'s established shape (host discovery,
launch planning, typed failures, admission wiring) rather than inventing a parallel
mechanism.

---

## 2. Goals & Non-Goals

### Goals

- Add a `same-host-ensemble` command under the existing `runtime` group.
- Expose every ensemble-specific setting as a real CLI input: task, host, role roster (name +
  system prompt, repeatable or file-supplied), implementer prompt, and optional model /
  reasoning-effort overrides — validated before anything else happens.
- Generalize `RuntimeLaunchPlan`/`RuntimeLaunchPlanner` to carry a capability id per primitive
  instead of hardcoding `adversarial-team`'s.
- Restrict host selection to `codex` and `claude` for this primitive specifically, since those
  are the only hosts the cross-provider control matrix rates "Exact" for both fork and
  sandbox; never offer `opencode` as a choice for this command.
- Reuse the existing credential, HTTP, idempotency, output, and error systems unchanged.
- Stop at an explicit `EnsembleExecutionNotImplemented` boundary before requesting paid
  admission or constructing any provider client.
- Add zero new Python package dependencies.

### Non-Goals

- Implementing the actual fan-out/fan-in algorithm, forking, or any provider call. That is a
  separate future PR, gated on two external prerequisites: `vidbyte-sdk` PR #409 merging
  (`CodexHarnessAgent`) and a new, separately-approved `vidbyte-sdk` paradigm
  (`paradigms/same_host_ensemble`, required by that package's own README non-goal before any
  concrete paradigm may be implemented).
- Adding `vidbyte-sdk` as a `vidbyte-cli` dependency. That belongs to the future executor PR,
  once the SDK code it would import actually exists on `vidbyte-sdk`'s `main`.
- Sandbox mode is deliberately **not** an exposed setting. Read-only isolation for proposal
  roles and write access for the implementer role are safety invariants of the primitive
  itself, not caller-tunable knobs; exposing them would let a caller weaken the one property
  that makes "propose, don't commit" true.
- Reconciling `vidbyte` PR #508 (the x402 catalog entry already opened) against PR #507's
  runtime-specific admission scaffold. That is a `vidbyte` backend change, out of repo scope
  for this PR; tracked in Section 12.
- Building `ClaudeHarnessAgent`. It does not exist anywhere yet. This design assumes Claude
  support ships whenever that adapter lands; until then the future executor PR's boundary
  applies equally to both hosts (see Section 3).
- New `tests/` files, per the no-tests workflow.

---

## 3. Background & Context

- `vidbyte-cli` PR #23 (merged) already built the local-runtime shell: `runtime list`,
  `runtime doctor`, `runtime adversarial-team`, and the `lib/runtime_primitives/` package
  (`hosts.py`, `planner.py`, `executor.py`). Its own design doc
  (`docs/design/local-runtime-primitives-scaffold.md`) explicitly scoped out "any runtime
  algorithm" and left `RuntimeExecutor.execute_adversarial_team` raising
  `RuntimeExecutionNotImplemented`. That stub is still unfilled — this PR does not fill it,
  it adds a second, equally-stubbed primitive next to it.
- `vidbyte-cli` PR #24 (open) adds `skills/runtime_primitives/SKILL.md`, which documents the
  intended eventual approach: provider adapters (`CodexHarnessAgent` / a future
  `ClaudeHarnessAgent`) driven through their Python SDKs, with translations classified as
  exact/policy/emulated/unsupported. Its `references/control-matrix.md` rates **Fork** and
  **Sandbox** "Exact" for both Codex and the Claude Agent SDK, and lists no equivalent for
  OpenCode at all.
- `vidbyte-sdk` PR #409 (open, assumed to land as-is) adds `CodexHarnessAgent`, with native
  thread forking (`afork`, requiring a live parent thread id — a fork cannot be the first
  turn) and per-fork sandbox control (`CodexSandbox.READ_ONLY` / `WORKSPACE_WRITE`). A prior
  conversation sketched a `vidbyte-sdk` paradigm (`SameHostEnsembleParadigm`) that runs one
  root turn to mint a thread id, fans out read-only role forks concurrently, joins their
  output, then forks once more with write access for the implementer. That paradigm does not
  exist yet and needs its own approved design doc in `vidbyte-sdk`, per that repo's
  `paradigms/README.md`: *"Do not implement a concrete paradigm without an approved design doc
  that identifies primitive gaps, result shape, stopping criteria, trace behavior, eval
  strategy, and adapter surfaces."* This PR does not attempt to satisfy that gate — it only
  builds the `vidbyte-cli` surface that will eventually call into it.
- `vidbyte-cli`'s `pyproject.toml` currently depends only on `click`, `httpx`, `keyring`,
  `platformdirs`, and `pydantic` — no `vidbyte-sdk` dependency exists today. Adding one before
  `vidbyte-sdk` actually ships the class this PR would import is not possible in a way that
  installs or passes CI, so this PR does not add it.
- `scripts/test_research_only_surface.py` asserts an exact top-level and `runtime` command
  surface (`EXPECTED_RUNTIME = {"adversarial-team", "doctor", "list"}`) and a list of
  `FORBIDDEN_SOURCE_TOKENS` left over from deleting the old backend-dispatch harness manifest
  system (`lib/harness/`, `harnesses/`, and even the literal token `"harness"` are now
  forbidden anywhere in source). This PR must add `"same-host-ensemble"` to
  `EXPECTED_RUNTIME` and must not reintroduce any forbidden token.
- The field guide (`field-guide/vidbyte-cli/`) establishes house rules this design follows:
  one `CliError` subclass per failure in `lib/errors/failures.py` (never a bare
  constructor), a single `match` in `lib/errors/handler.py`, no templated file-header
  comments (a 3–6 line module docstring instead), and no module-level helper functions sitting
  outside a class.
- `vidbyte` PR #507 (open) adds its own runtime-specific x402 admission scaffold
  (`backend/services/runtime_primitives/admission.py`, `backend/routes/x402_runtime.py`,
  `backend/lib/dtos/runtime_primitives.py`) and also touches `backend/lib/x402/catalog.py` —
  the same file the subagent's `vidbyte` PR #508 just modified with a generic
  `runtime.same-host-ensemble@1` catalog entry at 2 cents. These two PRs have not been
  reconciled; see Section 12.

---

## 4. Requirements

### Functional Requirements

1. `vidbyte-cli runtime same-host-ensemble <task> [options]` must validate every input and
   build a `RuntimeLaunchPlan` before reaching the executor boundary.
2. `--host {auto,codex,claude}` must be the only accepted values; `auto` prefers Codex, then
   Claude (mirroring `adversarial-team`'s existing preference order minus OpenCode).
3. Roles must be settable two ways: repeatable `--role NAME:SYSTEM_PROMPT`, or `--roles-file
   PATH` pointing at a JSON array of `{"name": ..., "system_prompt": ...}` objects. The two are
   mutually exclusive. If neither is given, a built-in three-role default set applies
   (`correctness`, `simplification`, `security` — matching the vocabulary already used
   elsewhere in this workspace's own review tooling).
4. `--implementer-prompt TEXT` must be optional, defaulting to a fixed built-in prompt when
   omitted.
5. `--model TEXT` and `--reasoning-effort TEXT` must be optional, length-bounded pass-through
   strings. They are not validated against the SDK's own enum in this PR, because this PR does
   not depend on the SDK; the future executor PR performs that translation at its own
   boundary.
6. The command must reach `RuntimeExecutor.execute_same_host_ensemble(plan, roster)`, which
   must raise `EnsembleExecutionNotImplemented` unconditionally, before any admission request
   or process is created, regardless of which valid host was selected.
7. `RuntimeEndpoints` must expose a future-ready `admit_same_host_ensemble` operation
   analogous to `admit_adversarial_team`, unreachable from the scaffold executor.
8. Empty task, empty/invalid role entries, an unreadable or malformed `--roles-file`,
   specifying both `--role` and `--roles-file`, and reaching the execution boundary must each
   raise their own `CliError` subclass.
9. `--help` and `--version` must remain free of filesystem, credential, and network side
   effects.
10. `scripts/test_research_only_surface.py` must be updated to expect the new command and must
    continue to pass with no forbidden tokens reintroduced.

### Non-Functional Requirements

- No environment values, API keys, prompts, role system-prompt text, or subprocess output may
  appear in error metadata (matching the existing `RuntimeHostUnavailable`-style failures).
- All new Pydantic models reject extra fields and bound authored strings (matching
  `RuntimeLaunchPlan`'s existing `extra="forbid"` convention).
- Every new function/method signature occupies one line, immediately followed by a one- to
  two-line comment (existing repo-wide convention, reaffirmed in PR #23's own requirements).
- Existing Ruff, strict mypy, compile, smoke, build, and installed-wheel gates remain
  required; `python scripts/run_ci.py` must exit 0.

---

## 5. High-Level Design

`commands/runtime/same_host_ensemble.py` adds a second static command next to
`adversarial_team.py`, registered in the same `commands/runtime/__init__.py`. It parses the
role roster (from repeatable flags or a JSON file) into a new `EnsembleRoster` Pydantic model,
resolves the host exactly as `adversarial-team` does (minus `opencode`), and reuses
`RuntimeLaunchPlanner.build()` — generalized to accept a `capability_id` — to produce a
`RuntimeLaunchPlan`. It then calls `RuntimeExecutor.execute_same_host_ensemble(plan, roster)`,
a new method that raises `EnsembleExecutionNotImplemented` before any side effect, mirroring
`execute_adversarial_team`'s existing stub exactly.

```text
[agent caller via shell]
        |
        v
[same-host-ensemble command] -> [parse roles: flags or --roles-file] -> [EnsembleRoster]
        |
        v
[host registry] -> [launch planner (capability_id="runtime.same-host-ensemble@1")]
        |
        v
[executor.execute_same_host_ensemble: STOP -> EnsembleExecutionNotImplemented]
        |
        +-> [admit_same_host_ensemble endpoint: wired, not called by scaffold]

Future executor PR (blocked on vidbyte-sdk #409 + an approved SDK paradigm):
  admission grant -> CodexHarnessAgent root turn -> N read-only role forks (concurrent)
  -> join proposals -> one write-enabled implementer fork -> normalized result
```

No change touches `lib/runtime/context.py`: `runtime_launch_planner()` and
`runtime_executor()` already return primitive-agnostic instances, so the existing lazy
factories serve both primitives without modification.

---

## 6. Detailed Design

### 6.1 Generalized Launch Plan and New Ensemble Types

**File(s):** `src/vidbyte_cli/types/runtime.py`
**Type:** Modified

#### What it does

Widens `RuntimeLaunchPlan.capability_id` from a single hardcoded `Literal` to a
`Literal` union of every known capability id, so the same frozen plan type serves both
primitives without duplicating host/working-directory/task validation. Adds the
ensemble-specific role and roster contracts.

#### Interface / API

```python
class RuntimeCapabilityId(StrEnum):
    ADVERSARIAL_TEAM = "runtime.review.adversarial-team@1"
    SAME_HOST_ENSEMBLE = "runtime.same-host-ensemble@1"


class RuntimeLaunchPlan(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid", frozen=True)
    capability_id: RuntimeCapabilityId
    host: RuntimeHost
    executable: Path
    working_directory: Path
    task: str = Field(min_length=1, max_length=20_000)


class EnsembleRole(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str = Field(min_length=1, max_length=64)
    system_prompt: str = Field(min_length=1, max_length=20_000)


class EnsembleRoster(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    roles: tuple[EnsembleRole, ...] = Field(min_length=1, max_length=8)
    implementer_prompt: str = Field(min_length=1, max_length=20_000)
    model: str | None = Field(default=None, max_length=128)
    reasoning_effort: str | None = Field(default=None, max_length=32)
```

#### Logic / Algorithm

1. Replace the single-literal `capability_id` field with the enum above; every existing
   `RuntimeLaunchPlan(...)` call site names its own capability id explicitly.
2. Add `EnsembleRole`/`EnsembleRoster` as plain data contracts with no behavior — they are
   validated once at construction and never mutated.

#### Edge Cases & Error Handling

- `RuntimeCapabilityId` is closed (a `StrEnum`), so a third primitive must add its own member
  here — this is the intended, minimal seam for the next primitive.
- `EnsembleRoster.roles` bounds role count to 8 to keep a single ensemble invocation from
  becoming an unbounded fan-out; this is a scaffold-time constant, revisit if the future
  executor PR needs a different ceiling once real cost data exists.

### 6.2 Role Parsing

**File(s):** `src/vidbyte_cli/commands/runtime/same_host_ensemble.py`
**Type:** New file

#### What it does

Turns `--role`/`--roles-file` CLI input into a validated `EnsembleRoster`, applying the
built-in default roles when neither is given.

#### Interface / API

```python
_DEFAULT_ROLES: tuple[EnsembleRole, ...] = (...)  # correctness, simplification, security


class SameHostEnsembleCommand:
    def register(self, parent: click.Group) -> None: ...
    def execute(
        self,
        context: ApplicationContext,
        task: str,
        host: str,
        roles: tuple[str, ...],
        roles_file: Path | None,
        implementer_prompt: str | None,
        model: str | None,
        reasoning_effort: str | None,
    ) -> None: ...

    def _build_roster(
        self,
        roles: tuple[str, ...],
        roles_file: Path | None,
        implementer_prompt: str | None,
        model: str | None,
        reasoning_effort: str | None,
    ) -> EnsembleRoster: ...
```

#### Logic / Algorithm

1. Reject `--role` and `--roles-file` used together (`EnsembleRoleSourceConflict`).
2. If `--role` values are given, split each on the first `:` into name/system_prompt; a
   missing colon or empty half raises `EnsembleRoleInvalid`.
3. If `--roles-file` is given, read and `json.loads` it; a missing file, unreadable file, or
   any shape that does not validate as `tuple[EnsembleRole, ...]` raises
   `EnsembleRolesFileInvalid` with the underlying `pydantic.ValidationError` folded into the
   description, never the raw file content.
4. If neither is given, use `_DEFAULT_ROLES`.
5. Construct `EnsembleRoster` with the resolved roles plus implementer prompt (default if
   omitted) and optional model/reasoning-effort strings.

#### Edge Cases & Error Handling

- A `--roles-file` that parses as valid JSON but the wrong shape (e.g. a single object instead
  of an array) fails Pydantic validation, which is caught and re-raised as
  `EnsembleRolesFileInvalid` — never let a raw `pydantic.ValidationError` or `json.JSONDecodeError`
  escape to the CLI's generic exception path.
- A role name collision (two roles with the same `name`) raises `EnsembleRoleInvalid` — role
  names are used as fork identifiers in the future executor, so collisions must fail here.

### 6.3 Launch Planner Generalization

**File(s):** `src/vidbyte_cli/lib/runtime_primitives/planner.py`
**Type:** Modified

#### What it does

Accepts a capability id parameter instead of hardcoding one, so both primitives share the same
host-resolution and working-directory validation without duplicating it.

#### Interface / API

```python
class RuntimeLaunchPlanner:
    def build(
        self,
        capability_id: RuntimeCapabilityId,
        task: str,
        requested_host: RuntimeHost | None,
        working_directory: Path,
    ) -> RuntimeLaunchPlan: ...
```

#### Logic / Algorithm

1. Existing host resolution, working-directory validation, and task-bounds logic is unchanged.
2. The resolved `RuntimeLaunchPlan` is constructed with the passed-in `capability_id` instead
   of a hardcoded literal.

#### Edge Cases & Error Handling

- `adversarial_team.py`'s existing call site is updated to pass
  `RuntimeCapabilityId.ADVERSARIAL_TEAM` explicitly — the only change required there.

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
    def execute_same_host_ensemble(
        self, plan: RuntimeLaunchPlan, roster: EnsembleRoster
    ) -> NoReturn: ...


class RuntimeEndpoints:
    def admit_adversarial_team(
        self, request: RuntimeAdmissionRequest, idempotency_key: str
    ) -> RuntimeAdmissionGrant: ...
    def admit_same_host_ensemble(
        self, request: RuntimeAdmissionRequest, idempotency_key: str
    ) -> RuntimeAdmissionGrant: ...
```

#### Logic / Algorithm

1. `execute_same_host_ensemble` accepts the validated plan and roster only to fix the future
   implementation seam, then unconditionally raises `EnsembleExecutionNotImplemented`.
2. `admit_same_host_ensemble` POSTs to `/api/x402/runtime/same-host-ensemble/admissions` — this
   route path is provisional pending `vidbyte` PR #507's final routing convention; see
   Section 12.

#### Edge Cases & Error Handling

- Both new methods are exercised by the smoke/offline check the same way
  `execute_adversarial_team`/`admit_adversarial_team` already are — reachable and typed, never
  invoked end-to-end.

### 6.5 Agent-Native Failures

**File(s):** `src/vidbyte_cli/lib/errors/failures.py`
**Type:** Modified

#### What it does

Adds one `CliError` subclass per new failure, following the field guide's typed-failures rule
exactly — no bare `CliError(...)`, no shared generic class reused across primitives with a
hardcoded message that would then be wrong for the new one.

#### Interface / API

```python
class EnsembleRoleSourceConflict(CliError): ...
class EnsembleRoleInvalid(CliError): ...
class EnsembleRolesFileInvalid(CliError): ...
class EnsembleExecutionNotImplemented(CliError): ...
```

#### Logic / Algorithm

1. Each class fixes `code`, `exit_status`, `retryable`, and its own static
   `message`/`description`/`trace`/`hint`, matching `RuntimeExecutionNotImplemented`'s
   existing shape.
2. `EnsembleExecutionNotImplemented`'s `hint` points at `runtime list` for published capability
   metadata, exactly as the adversarial-team equivalent does.

#### Edge Cases & Error Handling

- `ErrorHandler.handle`'s single `match` needs no new `case` — all four are `CliError`
  subclasses and already fall under the existing base-class case.

---

## 7. Data Model Changes

### 7.1 CLI-Local Types

**Change type:** New/Modified (Python types only, no persisted schema)

Covered fully in Section 6.1. No database, no CLI-persisted config schema changes.

**Migration strategy:** N/A — additive Python types, existing credentials/configuration
untouched.

---

## 8. API Changes

### 8.1 `POST /api/x402/runtime/same-host-ensemble/admissions`

**Change type:** New consumer, not invoked by this scaffold

**Request:**

```json
{
  "client_runtime_version": "1",
  "host": "codex | claude"
}
```

**Response:**

```json
{
  "admission_id": "opaque string",
  "capability_id": "runtime.same-host-ensemble@1",
  "execution_location": "local",
  "charged_cents": 2,
  "admitted_at": "RFC 3339 timestamp"
}
```

**Error cases:** identical to `adversarial-team`'s admission route (400/422 invalid host or
version, 401/403 auth/scope, 402 wallet funding required, 409 idempotency conflict, 429 rate
limited, 503 unavailable) — reusing the exact contract `RuntimeAdmissionRequest`/
`RuntimeAdmissionGrant` already define.

This route's existence and exact price depend on the `vidbyte` backend reconciling PR #507
and PR #508 (see Section 12) — this PR wires the client-side call shape only.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/same-host-ensemble-scaffold.md` | This design doc |
| CREATE | `src/vidbyte_cli/commands/runtime/same_host_ensemble.py` | New command: role parsing, launch plan, executor call |
| MODIFY | `src/vidbyte_cli/commands/runtime/__init__.py` | Register the new command in the `runtime` group |
| MODIFY | `src/vidbyte_cli/commands/runtime/adversarial_team.py` | Pass `RuntimeCapabilityId.ADVERSARIAL_TEAM` explicitly |
| MODIFY | `src/vidbyte_cli/types/runtime.py` | Generalize `capability_id`; add `EnsembleRole`/`EnsembleRoster` |
| MODIFY | `src/vidbyte_cli/lib/runtime_primitives/planner.py` | `build()` takes `capability_id` |
| MODIFY | `src/vidbyte_cli/lib/runtime_primitives/executor.py` | Add `execute_same_host_ensemble` stub |
| MODIFY | `src/vidbyte_cli/lib/api/endpoints/runtime.py` | Add `admit_same_host_ensemble` |
| MODIFY | `src/vidbyte_cli/lib/errors/failures.py` | Add four new `CliError` subclasses |
| MODIFY | `scripts/test_research_only_surface.py` | Expect `same-host-ensemble` in `EXPECTED_RUNTIME` |
| MODIFY | `README.md` | Document the new command and its settings |
| MODIFY | `docs/architecture.md` | Document the second runtime primitive and its shared seams |

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Vidbyte backend | `/api/x402/runtime`, `/api/x402/runtime/same-host-ensemble/admissions` | Capability discovery, future paid admission | Route/price not final until `vidbyte` PR #507/#508 reconcile |
| Codex/Claude executables | User-installed | Future native-agent hosts | Same discovery mechanism as `adversarial-team`; no new risk |

No new Python package dependency is added. `vidbyte-sdk` is an explicit future dependency of
the follow-up executor PR, not this one.

---

## 11. Rollout & Deployment

- This PR is additive and ships independently of the backend admission route — `runtime list`
  already reports backend availability honestly, and this scaffold's executor never calls
  admission.
- No feature flag is needed: the command is fully functional up to its documented stop point,
  the same pattern already shipped for `adversarial-team`.
- The follow-up executor PR must not change `execute_same_host_ensemble`'s boundary until both
  external prerequisites (Section 2) are satisfied and verified.
- Rollback: remove the command registration and the four new failure classes; no local user
  state needs cleanup.

---

## 12. Open Questions

- [ ] `vidbyte` PR #507 vs PR #508: PR #507 adds its own runtime-specific admission/catalog
  plumbing and also touches `backend/lib/x402/catalog.py`; PR #508 already added a generic
  `runtime.same-host-ensemble@1` entry there at 2 cents. These need reconciling in `vidbyte`
  once #507's shape is final — either #508 is superseded by #507's own registration path, or
  #507 is updated to consume #508's entry. This is a `vidbyte` repo change, not tracked
  further in this doc.
- [ ] Exact non-interactive invocation contract for each host, once the executor is actually
  implemented (same open question PR #23 left for `adversarial-team`).
- [ ] Whether `--model`/`--reasoning-effort` should later become a strict `click.Choice` once
  the future executor PR imports `vidbyte-sdk` and its enums are known; deferred by design in
  this PR (Section 4, requirement 5).

---

## 13. Alternatives Considered

### Alternative 1: Wait for `vidbyte-sdk` #409 to merge before starting any of this

- What: Defer this entire PR until `CodexHarnessAgent` exists, then build the full CLI surface
  and real execution together.
- Why rejected: The CLI settings surface — the part you specifically asked for — has zero
  dependency on the SDK class actually existing. Building it now, stopped at an honest
  boundary, delivers agent-controllable settings today instead of blocking on an unmerged PR
  in a different repository.

### Alternative 2: Give the ensemble command its own launch-plan type instead of generalizing `RuntimeLaunchPlan`

- What: Add a parallel `EnsembleLaunchPlan` rather than widening `capability_id`.
- Why rejected: `RuntimeLaunchPlanner`'s host-resolution and working-directory validation is
  identical for both primitives; duplicating it into a second type just to avoid a one-field
  widening fails this repo's own restraint rule ("a stateless single-use helper is a private
  method, not a collaborator class") applied one level up — here, a duplicated type instead of
  a generalized field.

### Alternative 3: Expose sandbox mode as a caller-settable flag, for maximum "every setting is tunable" completeness

- What: Add `--proposal-sandbox`/`--implementer-sandbox` flags.
- Why rejected: this is the one setting explicitly excluded in Section 2. Sandbox separation
  between read-only proposal forks and the one write-enabled implementer fork is what makes
  "propose, don't commit" true; letting a caller weaken it defeats the primitive's own safety
  rationale rather than adding legitimate flexibility.
