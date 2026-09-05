# Design Doc: Same-Host Ensemble Implementation

**Status:** Draft
**Author:** Claude
**Created:** 2026-09-05
**Last Updated:** 2026-09-05

---

## 1. Overview

This replaces the `same-host-ensemble` scaffold with a working local runtime primitive. A
caller gives one task; the CLI runs a three-stage Codex topology on the caller's own machine.
Stage one is a single planner turn that reads the task and *generates* the ensemble's roles —
their names and their complete system prompts. Stage two forks that thread once per generated
role, concurrently, each fork sandboxed read-only so it can analyze the workspace but cannot
change it, and each returning a structured proposal rather than an edit. Stage three forks the
root thread once more with workspace-write access and hands the implementer every surviving
proposal, so exactly one agent in the topology can touch the repository. The core algorithm is
under fifty lines because the Codex SDK supplies thread forking natively; everything else in
this PR is input validation, prompt authorship, typed failures, and result rendering.

---

## 2. Goals & Non-Goals

### Goals

- Replace `RuntimeExecutor.execute_ensemble`'s unconditional raise with the real fan-out/fan-in
  algorithm, driven entirely by `CodexHarnessAgent` from `vidbyte-sdk`.
- Move the implementation into its own subfolder, `src/vidbyte_cli/services/ensemble/`, a new
  `services/` package that sits beside `lib/` (PR #25 review comment 3941838090).
- Generate roles at runtime from a planner agent instead of shipping predetermined roles with
  hardcoded system prompts (review comment 3941890823). Every generated system prompt carries
  `identity`, `personality`, `knowledge`, and `goal` sections (review comment 3941891486).
- Author the planner's and implementer's own system prompts with `identity`, `goal`,
  `checklist`, and `examples` sections, following the anatomy in the `vidbyte-prompts` master
  template (review comments 3941893030, 3941896983), and keep every prompt in its own file
  (review comment 3941909792).
- Collapse the command's loose `Mapping[str, object]` values into one validated Pydantic input
  contract, `EnsembleInputs` (review comment 3941900411), whose `host` field is a dedicated
  enum admitting only `codex` (review comments 3941836516, 3941905419).
- Enforce "propose, don't commit" structurally: proposal forks get `CodexSandbox.READ_ONLY` at
  both thread and turn level, and only the implementer fork gets `WORKSPACE_WRITE`.
- Request paid admission exactly once, after every free local precondition has passed, so a
  missing host or missing SDK never costs the caller two cents.
- Keep `python scripts/run_ci.py` green, including the clean-venv wheel install, without adding
  a hard runtime dependency the published `vidbyte-sdk` release cannot satisfy.

### Non-Goals

- Implementing `execute_adversarial_team`. It stays stubbed; `docs/architecture.md`'s
  rule-6 exception narrows to that one primitive instead of disappearing.
- Supporting `claude` or `opencode` as ensemble hosts. `ClaudeHarnessAgent` does not exist in
  `vidbyte-sdk`, and the control matrix rates OpenCode as having no fork/sandbox equivalent.
  Codex is the only accepted value (review comment 3941836516).
- Reconciling `vidbyte` PR #507 against PR #508 in the backend catalog. That remains a
  `vidbyte` repository change, out of scope here.
- Publishing a new `vidbyte-sdk` release. This PR consumes the SDK through an optional extra
  and fails with a typed, pre-payment error when the installed SDK predates `CodexHarnessAgent`.
- New `tests/` files, per the no-tests workflow. Existing gates in `scripts/` are updated, not
  weakened.

---

## 3. Background & Context

- `vidbyte-cli` PR #23 (merged) built the runtime shell: `runtime list`, `runtime doctor`,
  `runtime adversarial-team`, and `lib/runtime_primitives/` (`hosts.py`, `planner.py`,
  `executor.py`). PR #25 added a second, equally-stubbed `same-host-ensemble` command next to
  it. This PR fills that stub in and resolves all eleven review comments left on PR #25.
- `vidbyte-sdk` PR #409 has **merged** (with PR #411's review fixes), so `CodexHarnessAgent` is
  real code on the SDK's `main`. Reading the merged implementation rather than the design doc
  turned up four facts that shape this design:
  1. `CodexTransport.run` wraps each turn in `async with sdk.async_codex(config) as client`, and
     `CodexHarnessAgent.session_persistence_supported` is `False`. There is no long-lived
     process — every turn and every fork opens and closes its own Codex app-server. A
     three-role ensemble therefore costs nine app-server startups.
  2. `CodexFork.afork` raises when `parent_thread_id` is empty, so a fork is impossible before
     one successful turn. The planner turn is not ceremony; it is the precondition for forking
     at all, which is exactly why role generation belongs there.
  3. `ephemeral=True` looks like the way to get work that "doesn't save", but it is a trap.
     `thread_fork_kwargs` forwards it, yet the roadmap's checklist item L02 ("Keep in-memory
     threads alive across turns; reject resume after their owning process is gone") is still
     unchecked. Because each turn opens a fresh client, an ephemeral forked thread would be dead
     before its child could resume it. This design uses `ephemeral=False` and gets the no-write
     property from the sandbox instead.
  4. Sandbox is settable at two independent levels (`CodexThreadSettings.sandbox` via
     `_thread_common`, `CodexTurnSettings.sandbox` via `turn_kwargs`), and the
     `PROVIDER_DEFAULT` empty-string sentinel is *dropped* by `_without_empty`. Leaving sandbox
     unset therefore inherits whatever the user's Codex config says, which may be
     workspace-write. Read-only must be set explicitly, on both levels.
- Two repository constraints in this CLI bound the implementation:
  - `scripts/test_research_only_surface.py` declares
    `FORBIDDEN_SOURCE_TOKENS = ("harness", ...)` and scans **every** `src/**/*.py`
    case-insensitively. The SDK's class is named `CodexHarnessAgent`, so importing it by name
    trips a gate whose stated purpose (see `check_source_prose`) is catching prose that still
    names a *deleted* symbol. Section 6.8 narrows the token to the deleted symbols themselves.
  - `run_ci.py` builds the wheel, installs it into a fresh virtualenv, and runs
    `vidbyte-cli --help`, which imports every command module. The published
    `vidbyte-sdk==0.1.0` wheel contains **zero** codex files (verified by downloading it), so a
    module-level SDK import would break the gate. Every SDK import is therefore lazy, inside a
    method, behind a typed failure.
- The field guide (`field-guide/vidbyte-cli/`) governs style: one `CliError` subclass per
  failure carrying `description`/`trace`/`hint`, one `match` in `handler.py`, no module-level
  helper functions, no templated file headers (a 3–6 line docstring instead), a class only when
  it holds real state, and `python scripts/run_ci.py` as the sole verification gate.
- `AGENTS.md` states the CLI ships a command only once the route behind it is live, so nothing
  in its surface answers "not implemented yet". This PR moves `same-host-ensemble` onto the
  right side of that rule: the command now performs its full local algorithm, and a backend
  admission route that is not yet deployed surfaces through the existing API error machinery as
  an API failure, not as a command-level "not implemented".

---

## 4. Requirements

### Functional Requirements

1. `vidbyte-cli runtime same-host-ensemble <task> [options]` must parse its options into one
   `EnsembleInputs` Pydantic model and validate it before any other work.
2. `--host` must accept only `codex`. The value must be bound to an `EnsembleHost` enum whose
   single member is `CODEX`, so the accepted set and the type are one declaration.
3. `--roles N` must bound the fan-out to 2–8 roles inclusive, defaulting to 3.
4. `--reasoning-effort` must accept only members of an `EnsembleReasoningEffort` enum
   (`none`, `minimal`, `low`, `medium`, `high`, `xhigh`), matching the SDK's own vocabulary.
5. `--model` must be an optional, length-bounded pass-through string.
6. `--role-timeout` must bound each proposal fork in seconds (1–3600, default 300).
7. The command must never accept caller-supplied role names or role system prompts. Roles are
   generated by the planner agent at stage one.
8. Stage one must run exactly one turn on a fresh Codex thread using the authored planner
   system prompt, and must return a structured `RolePlan` of exactly `--roles` entries, each
   carrying `name`, `identity`, `personality`, `knowledge`, and `goal`.
9. Each generated role's four sections must be assembled into that fork's system prompt, wrapped
   in XML tags, before the fork is created.
10. Stage two must fork the root thread once per role, concurrently, with
    `CodexSandbox.READ_ONLY` set on both the fork's thread settings and its turn settings, and
    must collect a structured `RoleProposal` from each.
11. A role that fails or times out must be recorded as an `EnsembleRoleFailure` and must not
    abort the run, provided at least one role succeeded. If every role fails, the run must abort
    with a typed failure rather than running the implementer on nothing.
12. Stage three must fork the root thread (not any role's thread) with
    `CodexSandbox.WORKSPACE_WRITE`, using the authored implementer system prompt, and receive
    every surviving proposal in its turn input.
13. Paid admission must be requested exactly once, after input validation, SDK availability, and
    host discovery have all passed, and before the planner turn starts.
14. The command must emit one `runtime.ensemble` result document carrying the roles, the
    proposals, the failures, the implementation text, and both root and implementer thread ids.
15. Every distinct failure must be its own `CliError` subclass in `lib/errors/failures.py`.
16. `--help` and `--version` must remain free of filesystem, credential, network, and SDK-import
    side effects.
17. `scripts/test_research_only_surface.py` must continue to pass, and must continue to catch
    every deleted symbol it was written to catch.

### Non-Functional Requirements

- **Concurrency:** proposal forks run under one `asyncio.gather`; wall-clock time for the
  fan-out is the slowest role, not their sum. Each role is individually bounded by
  `asyncio.timeout`, so one hung host cannot hold the fan-in open indefinitely.
- **Security:** no task text, role prompt, proposal body, file path, environment value, or SDK
  exception message may appear in any `CliError`'s `message`, `description`, `trace`, or `hint`.
  Provider exceptions travel only in the private `cause` field, which no renderer serializes.
- **Cost safety:** the two-cent admission is requested only after every free precondition
  passes. A missing Codex executable, an absent SDK, or invalid input costs nothing.
- **Isolation:** exactly one agent in the topology may write to the workspace. This is enforced
  by sandbox settings on the fork, not by prompt instructions.
- **Observability:** the result document reports per-role success and failure and both thread
  ids, so a caller can resume or audit any branch afterward.
- **Packaging:** the core wheel gains no new hard dependency; the SDK arrives through a
  `codex` optional extra and is imported lazily.

---

## 5. High-Level Design

The command layer shrinks to parsing and rendering. `SameHostEnsembleCommand` builds an
`EnsembleInputs` model, asks `RuntimeLaunchPlanner` for a `RuntimeLaunchPlan` exactly as
`adversarial-team` does, and calls `RuntimeExecutor.execute_ensemble(plan, inputs)`. The
executor is no longer inert: it resolves the SDK, buys admission, and delegates to
`EnsembleService`, the new `services/ensemble/` package where the actual algorithm lives.

`EnsembleService.run` is one `asyncio.run` boundary wrapping three stages. The planner turn
mints the root thread id and returns the generated roster. The fan-out forks that thread once
per role under `asyncio.gather`, each fork read-only and each returning a typed proposal. The
fan-in forks the root thread a final time with write access and hands it the surviving
proposals. The result is normalized into `EnsembleResult` and rendered.

Two decisions carry the design. First, roles branch from the **root**, never from each other:
independent branches keep their errors decorrelated, which is the entire statistical reason an
ensemble beats one agent, and chaining them would serialize work the fork API gives us in
parallel for free. Second, the implementer also branches from the root rather than from any
role, so it inherits the task and the plan but none of a single role's framing.

```text
[CLI] -> EnsembleInputs (validated) -> RuntimeLaunchPlan (host + cwd)
                                          |
                                  [admission: 2c, once]
                                          |
                        stage 1: planner turn on a fresh thread
                        (authored prompt: identity/goal/checklist/examples)
                                          |
                             RolePlan -> N generated roles
                        (each: identity/personality/knowledge/goal)
                                          |
             +----------------------------+----------------------------+
             |                            |                            |
      fork #1 READ_ONLY           fork #2 READ_ONLY            fork #N READ_ONLY
      RoleProposal                RoleProposal                 RoleProposal
             |                            |                            |
             +----------------------------+----------------------------+
                                          |
                        stage 3: fork root, WORKSPACE_WRITE
                        (authored implementer prompt) -> implementation
                                          |
                                   EnsembleResult
```

Every arrow crossing a fork boundary is a separate Codex app-server lifecycle, because the SDK
opens and closes a client per operation. That is a cost characteristic, not a correctness
problem, and it is why concurrent fan-out matters.

---

## 6. Detailed Design

### 6.1 Ensemble Contracts

**File(s):** `src/vidbyte_cli/types/ensemble.py`
**Type:** New file

#### What it does

Holds every ensemble-specific typed contract: the validated command input model that review
comment 3941900411 asked for, the enums that constrain it, the two structured-output schemas the
agents fill in, and the result document.

#### Interface / API

```python
class EnsembleHost(StrEnum):
    CODEX = "codex"


class EnsembleReasoningEffort(StrEnum):
    NONE = "none"
    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"


class EnsembleConfidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class EnsembleInputs(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    task: str = Field(min_length=1, max_length=20_000)
    host: EnsembleHost = EnsembleHost.CODEX
    roles: int = Field(default=3, ge=2, le=8)
    model: str | None = Field(default=None, max_length=128)
    reasoning_effort: EnsembleReasoningEffort | None = None
    role_timeout_seconds: int = Field(default=300, ge=1, le=3600)


class GeneratedRole(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str = Field(min_length=1, max_length=64)
    identity: str = Field(min_length=1, max_length=4_000)
    personality: str = Field(min_length=1, max_length=4_000)
    knowledge: str = Field(min_length=1, max_length=8_000)
    goal: str = Field(min_length=1, max_length=4_000)


class RolePlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    roles: tuple[GeneratedRole, ...] = Field(min_length=1, max_length=8)


class RoleProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    role: str = Field(min_length=1, max_length=64)
    approach: str = Field(min_length=1, max_length=20_000)
    risks: tuple[str, ...] = Field(default=(), max_length=20)
    files: tuple[str, ...] = Field(default=(), max_length=50)
    confidence: EnsembleConfidence


class EnsembleRoleFailure(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    role: str
    reason: Literal["timeout", "host_error", "invalid_output"]


class EnsembleResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    task: str
    host: EnsembleHost
    roles: tuple[GeneratedRole, ...]
    proposals: tuple[RoleProposal, ...]
    failures: tuple[EnsembleRoleFailure, ...]
    implementation: str
    root_thread_id: str
    implementer_thread_id: str
    charged_cents: int
```

#### Logic / Algorithm

1. `EnsembleInputs` is constructed once from Click's parsed values and never mutated.
2. `GeneratedRole`'s four fields are exactly the sections review comment 3941891486 required,
   so a role that omits one fails Pydantic validation rather than producing a thin prompt.
3. `EnsembleRoleFailure.reason` is a closed literal set, so the result document stays
   machine-branchable and never carries a provider message.

#### Edge Cases & Error Handling

- `EnsembleHost` has a single member deliberately. Adding a host is a one-line change here plus
  a real adapter, which is the correct amount of friction given no second adapter exists.
- `RolePlan.roles` is bounded at 8 independently of `EnsembleInputs.roles` so a planner that
  ignores its instructions cannot produce unbounded fan-out.
- `extra="forbid"` on `RoleProposal` means a model that invents fields fails validation and is
  recorded as `invalid_output` rather than silently half-parsed.

### 6.2 Authored Prompts

**File(s):** `src/vidbyte_cli/services/ensemble/prompts.py`
**Type:** New file

#### What it does

Owns every authored prompt string and the assembly of generated role sections into a fork
system prompt. Review comment 3941909792 asked for prompts in their own file; this is that file.

#### Interface / API

```python
class EnsemblePrompts:
    def planner_system_prompt(self, roles: int) -> str: ...
    def planner_turn_prompt(self, task: str) -> str: ...
    def role_system_prompt(self, role: GeneratedRole) -> str: ...
    def role_turn_prompt(self, task: str) -> str: ...
    def implementer_system_prompt(self) -> str: ...
    def implementer_turn_prompt(self, task: str, proposals: tuple[RoleProposal, ...]) -> str: ...
```

#### Logic / Algorithm

1. The planner system prompt is authored with four XML-tagged sections —
   `<identity>`, `<goal>`, `<checklist>`, `<examples>` — as review comments 3941893030 and
   3941896983 required, following the master template's rule that identity leads and the most
   consequential constraints land last.
2. The `<examples>` section carries two worked few-shot examples showing a task and the roles a
   good planner produces for it, because role differentiation is the one judgment the planner
   makes and examples constrain it more reliably than adjectives.
3. `role_system_prompt` assembles a generated role into
   `<identity>…</identity><personality>…</personality><knowledge>…</knowledge><goal>…</goal>`,
   then appends the fixed propose-don't-implement clause that every role shares regardless of
   what the planner generated.
4. The implementer system prompt uses the same four authored sections as the planner, with a
   checklist covering proposal reconciliation and a worked example of resolving two conflicting
   proposals.
5. `implementer_turn_prompt` renders proposals as a numbered, labeled block so conflicting
   `files` entries are adjacent and visible rather than buried in prose.

#### Edge Cases & Error Handling

- Section text arrives already validated by `GeneratedRole`'s length bounds, so assembly cannot
  produce an unbounded system prompt.
- The propose-don't-implement clause is appended by this class, never by the planner, so a
  planner that generates a role encouraging edits still yields a read-only fork whose prompt
  says otherwise — and the sandbox enforces it regardless.

### 6.3 SDK Resolution

**File(s):** `src/vidbyte_cli/services/ensemble/sdk.py`
**Type:** New file

#### What it does

Performs the one lazy import of `vidbyte-sdk`, verifies the codex integration is actually
present, and hands back a typed handle. This is the only module in `src/` that touches the SDK.

#### Interface / API

```python
class EnsembleAgent(Protocol):
    thread_id: str

    async def arun(self, request: Any) -> Any: ...
    async def afork(self, settings: Any) -> "EnsembleAgent": ...


class EnsembleSdk:
    def __init__(self, symbols: Mapping[str, Any]) -> None: ...
    @classmethod
    def load(cls) -> "EnsembleSdk": ...
    def agent(self, settings: Any) -> EnsembleAgent: ...
    def run_input(self, prompt: str) -> Any: ...
    def root_settings(self, name: str, system_prompt: str, schema: type, options: Any) -> Any: ...
    def fork_settings(
        self, name: str, system_prompt: str, schema: type | None, options: Any
    ) -> Any: ...
    def is_provider_error(self, error: Exception) -> bool: ...
```

#### Logic / Algorithm

1. `load()` imports `vidbyte.agents.codex` inside a `try`, converting `ImportError` into
   `EnsembleSdkUnavailable`. It also converts `AttributeError` — an SDK installed at a release
   predating the codex integration imports as a package but lacks the symbols.
2. The resolved symbols are stored on the instance, so the class holds real state and satisfies
   the field guide's rule that a class must have `self.<field>` rather than being a namespace of
   static methods.
3. `agent`, `run_input`, `root_settings`, and `fork_settings` are thin constructors that keep
   every SDK type name confined to this module.
4. `is_provider_error` identifies the SDK's own error class so the service can classify a
   provider failure without importing it directly.

#### Edge Cases & Error Handling

- Importing at call time rather than module scope is what keeps `vidbyte-cli --help` working in
  the clean-venv wheel gate, where the SDK is absent.
- `EnsembleSdkUnavailable` is raised before admission, so a missing dependency is free.
- The `Protocol` gives mypy a checkable surface without depending on the SDK's own annotations,
  which are unavailable at type-check time for the same packaging reason.

### 6.4 Fork Settings

**File(s):** `src/vidbyte_cli/services/ensemble/settings.py`
**Type:** New file

#### What it does

Builds the three settings bundles the topology needs — root, read-only proposal fork, and
write-enabled implementer fork — so sandbox policy lives in exactly one place.

#### Interface / API

```python
class EnsembleSettingsFactory:
    def __init__(
        self, sdk: EnsembleSdk, inputs: EnsembleInputs, working_directory: Path
    ) -> None: ...
    def root(self, system_prompt: str) -> Any: ...
    def proposal(self, role: GeneratedRole, system_prompt: str) -> Any: ...
    def implementer(self, system_prompt: str) -> Any: ...
```

#### Logic / Algorithm

1. `root()` builds the harness agent settings with the planner system prompt, `RolePlan` as its
   output schema, `thread.cwd` set to the plan's working directory, and read-only sandbox — the
   planner only reads.
2. `proposal(role)` sets read-only sandbox on **both** `thread` and `turn`, because
   `PROVIDER_DEFAULT` is dropped before the SDK call and would silently inherit the user's own
   Codex configuration.
3. `implementer()` is the single bundle using workspace-write sandbox.
4. `ephemeral` is left `False` everywhere. Ephemeral forked threads do not survive their owning
   client, and the SDK opens a new client per operation, so an ephemeral fork would be dead
   before its child turn resumed it.
5. `--model` and `--reasoning-effort` are applied at the turn level on every bundle so one
   caller setting governs all three stages.

#### Edge Cases & Error Handling

- `working_directory` comes from the already-validated `RuntimeLaunchPlan`, so `cwd` is a real
  readable directory before any Codex process starts.
- A `None` model or reasoning effort is omitted rather than sent as an empty string, matching
  the SDK's own `_without_empty` convention.

### 6.5 The Ensemble Service

**File(s):** `src/vidbyte_cli/services/ensemble/service.py`
**Type:** New file

#### What it does

Runs the three-stage algorithm. This is the "under fifty lines of core logic" the feature was
scoped around.

#### Interface / API

```python
class EnsembleService:
    def __init__(self, sdk: EnsembleSdk, prompts: EnsemblePrompts) -> None: ...
    def run(
        self, plan: RuntimeLaunchPlan, inputs: EnsembleInputs, charged_cents: int
    ) -> EnsembleResult: ...
    async def _orchestrate(
        self, factory: EnsembleSettingsFactory, inputs: EnsembleInputs, charged_cents: int
    ) -> EnsembleResult: ...
    async def _plan_roles(self, root: EnsembleAgent, inputs: EnsembleInputs) -> RolePlan: ...
    async def _propose(
        self,
        root: EnsembleAgent,
        factory: EnsembleSettingsFactory,
        role: GeneratedRole,
        inputs: EnsembleInputs,
    ) -> RoleProposal: ...
    async def _implement(
        self,
        root: EnsembleAgent,
        factory: EnsembleSettingsFactory,
        proposals: tuple[RoleProposal, ...],
        inputs: EnsembleInputs,
    ) -> tuple[str, str]: ...
    def _partition(
        self, roles: tuple[GeneratedRole, ...], outcomes: list[object]
    ) -> tuple[tuple[RoleProposal, ...], tuple[EnsembleRoleFailure, ...]]: ...
```

#### Logic / Algorithm

1. `run` is the synchronous boundary: it calls `asyncio.run(self._orchestrate(...))`, which is
   the only event loop in the process.
2. `_orchestrate` constructs the root agent, awaits `_plan_roles`, gathers `_propose` across
   every generated role with `return_exceptions=True`, partitions successes from failures,
   aborts with `EnsembleAllRolesFailed` if nothing survived, awaits `_implement`, and builds the
   result.
3. `_plan_roles` runs one turn and reads `structured`. A reply whose structured output is absent
   or has the wrong role count raises `EnsembleRolePlanInvalid`.
4. `_propose` wraps its work in `asyncio.timeout(inputs.role_timeout_seconds)`, forks the root
   read-only, runs one turn, and validates the structured proposal.
5. `_implement` forks the root with write access and runs one turn carrying every surviving
   proposal.
6. `_partition` converts a raised `TimeoutError` into a `timeout` failure record, a provider
   error into `host_error`, and a validation error into `invalid_output`, keeping the run alive
   as long as one proposal survived.

#### Edge Cases & Error Handling

- Concurrent `afork` on one root is safe: `afork` reads only `settings` and `thread_id`, neither
  of which mutates during the gather, and the SDK's transport holds no instance state.
- `asyncio.CancelledError` is never swallowed — only `TimeoutError` and provider errors are
  converted into failure records, so Ctrl-C still propagates.
- A provider failure in the planner or implementer aborts the run with its own typed failure;
  only proposal roles are individually survivable.

### 6.6 Command Surface

**File(s):** `src/vidbyte_cli/commands/runtime/same_host_ensemble.py`
**Type:** Modified

#### What it does

Parses options into `EnsembleInputs`, builds the launch plan, calls the executor, and renders
the result. Every trace of caller-supplied roles is removed.

#### Interface / API

```python
class SameHostEnsembleCommand:
    def register(self, parent: click.Group) -> None: ...
    def execute(self, context: ApplicationContext, inputs: EnsembleInputs) -> None: ...
    def _inputs(
        self,
        task: str,
        host: str,
        roles: int,
        model: str | None,
        reasoning_effort: str | None,
        role_timeout: int,
    ) -> EnsembleInputs: ...
    def _render(self, context: ApplicationContext, result: EnsembleResult) -> None: ...
```

#### Logic / Algorithm

1. `--role`, `--roles-file`, and `--implementer-prompt` are deleted outright, along with
   `_DEFAULT_ROLES`, `_parse_role`, `_read_roles_file`, `_build_roster`, and `_finish_roster`.
2. `--host` and `--reasoning-effort` use `click.Choice` built from the new enums, so the
   accepted strings and the types cannot drift.
3. `_inputs` constructs `EnsembleInputs`, converting `pydantic.ValidationError` into
   `EnsembleInputsInvalid` so no raw validation error escapes to the generic exception path.
4. `_render` emits a `runtime.ensemble` document plus a human summary listing each role's
   confidence, each failure, and the implementation text.

#### Edge Cases & Error Handling

- `--roles` outside 2–8 is rejected by the model, not by Click alone, so the same bound applies
  whether the value arrives from the CLI or from a future programmatic caller.
- A plan that resolves to a non-Codex host raises `EnsembleHostUnsupported` before the executor.

### 6.7 Executor and Failures

**File(s):** `src/vidbyte_cli/lib/runtime_primitives/executor.py`,
`src/vidbyte_cli/lib/errors/failures.py`, `src/vidbyte_cli/lib/runtime/context.py`
**Type:** Modified

#### What it does

Turns the inert boundary into the admission-then-execute path, and replaces the scaffold's
role-file failures with the failures the real algorithm can actually produce.

#### Interface / API

```python
class RuntimeExecutor:
    def __init__(self, endpoints: RuntimeEndpoints | None = None) -> None: ...
    def execute_adversarial_team(self, plan: RuntimeLaunchPlan) -> NoReturn: ...
    def execute_ensemble(
        self, plan: RuntimeLaunchPlan, inputs: EnsembleInputs
    ) -> EnsembleResult: ...
```

Failures removed: `EnsembleRoleSourceConflict`, `EnsembleRoleInvalid`,
`EnsembleRolesFileUnreadable`, `EnsembleRolesFileNotValidJson`, `EnsembleRolesFileInvalid`,
`EnsembleExecutionNotImplemented`.

Failures added: `EnsembleInputsInvalid`, `EnsembleSdkUnavailable`, `EnsembleRolePlanInvalid`,
`EnsembleAllRolesFailed`, `EnsembleImplementerFailed`, `EnsembleHostFailed`.

Failure retained: `EnsembleHostUnsupported`.

#### Logic / Algorithm

1. `execute_ensemble` loads the SDK, then requests admission through
   `admit_same_host_ensemble` with a fresh `IdempotencyKey`, then runs the service.
2. `ApplicationContext.runtime_executor()` now injects `runtime_endpoints()` so the executor can
   buy admission; the adversarial-team path does not use it and stays unchanged.

#### Edge Cases & Error Handling

- SDK resolution precedes admission, so a missing dependency never costs money.
- `ErrorHandler.handle` needs no new `case`: every failure is a `CliError` subclass and falls
  under the existing base-class case.

### 6.8 Forbidden-Token Precision

**File(s):** `scripts/test_research_only_surface.py`
**Type:** Modified

#### What it does

Narrows `FORBIDDEN_SOURCE_TOKENS` from the bare substring `"harness"` to the specific deleted
symbols and module paths, so the gate still catches everything it was written to catch while no
longer colliding with the SDK's live `CodexHarnessAgent` class name.

#### Interface / API

```python
FORBIDDEN_SOURCE_TOKENS = (
    "BaseHarness",
    "HarnessRun",
    "RepoInspector",
    "NotImplementedFeature",
    "lib.harness",
    "lib/harness",
    "commands.harness",
    "types.harness",
    "endpoints.harness",
    "vidbyte_cli.harnesses",
)
```

#### Logic / Algorithm

1. Each retained token names a symbol or module path that was actually deleted, which is what
   `check_source_prose`'s own comment says the sweep exists to catch.
2. `CodexHarnessAgent` matches none of them: lowercased it is `codexharnessagent`, which
   contains none of `lib.harness`, `baseharness`, `harnessrun`, or `vidbyte_cli.harnesses`.

#### Edge Cases & Error Handling

- This is a precision change, not a weakening: every previously-caught deleted symbol is still
  caught, and the PR body states the change explicitly for review.

### 6.9 Agent-Building Skills

**File(s):** `skills/harnesses/x402-runtime-economics/SKILL.md`,
`skills/harnesses/runtime-primitives/SKILL.md`,
`skills/harnesses/codex-harness-sdk/SKILL.md`,
`skills/harnesses/codex-harness-sdk/references/build-decisions.md`
**Type:** New files

#### What it does

Captures the background and the build procedure for this class of work, as review comments
3941844912 and 3941846360 asked. Three skills: what x402 runtime primitives are and how they are
priced and admitted; what a runtime primitive is and the shape every one of them shares; and how
to drive `CodexHarnessAgent` from `vidbyte-sdk` correctly, including the four merged-code facts
in Section 3 that a design doc alone would get wrong.

#### Logic / Algorithm

1. Each `SKILL.md` carries YAML frontmatter with `name` and `description`, matching the
   convention used by the SDK's own `skills/` folder.
2. `references/build-decisions.md` is the decision checklist comment 3941846360 asked for: the
   ordered set of choices to make when building one of these agents — host selection, sandbox
   per stage, input validation, structured output, failure partitioning, admission ordering, and
   the packaging constraint.

#### Edge Cases & Error Handling

- These files live outside `src/`, so they are not scanned by the forbidden-token sweep and are
  not packaged into the wheel.

---

## 7. Data Model Changes

### 7.1 CLI-Local Types

**Change type:** New (`types/ensemble.py`) and Modified (`types/runtime.py`)

`types/runtime.py` loses `EnsembleRole` and `EnsembleRoster`, the caller-supplied role contracts
the review rejected. Everything ensemble-specific moves to `types/ensemble.py` as described in
Section 6.1.

**Migration strategy:** N/A — Python types only, no database and no persisted CLI configuration
schema. No local user state needs migration.

---

## 8. API Changes

### 8.1 `POST /api/x402/runtime/same-host-ensemble/admissions`

**Change type:** Existing consumer, now actually invoked

**Request:**

```json
{ "client_runtime_version": "1", "host": "codex" }
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

**Error cases:**

| Status | Condition |
|--------|-----------|
| 400/422 | Invalid host or client runtime version |
| 401/403 | Missing or unscoped credentials |
| 402 | Wallet funding required |
| 404 | Route not deployed yet (backend PRs #507/#508 unmerged) |
| 409 | Idempotency key conflict |
| 429 | Rate limited |
| 503 | Backend unavailable |

The request shape is unchanged from the scaffold; this PR only starts calling it. The existing
`ApiClient` problem-mapping layer renders each status, so an undeployed route surfaces as an API
failure rather than a command-level "not implemented".

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/same-host-ensemble-implementation.md` | This design doc |
| CREATE | `src/vidbyte_cli/services/__init__.py` | New `services/` package beside `lib/` |
| CREATE | `src/vidbyte_cli/services/README.md` | Layer boundary note, matching `lib/README.md` |
| CREATE | `src/vidbyte_cli/services/ensemble/__init__.py` | Ensemble subfolder export surface |
| CREATE | `src/vidbyte_cli/services/ensemble/prompts.py` | Authored prompts, own file |
| CREATE | `src/vidbyte_cli/services/ensemble/sdk.py` | Lazy SDK resolution and protocol |
| CREATE | `src/vidbyte_cli/services/ensemble/settings.py` | Root/proposal/implementer settings |
| CREATE | `src/vidbyte_cli/services/ensemble/service.py` | The three-stage algorithm |
| CREATE | `src/vidbyte_cli/types/ensemble.py` | Inputs, enums, schemas, result |
| CREATE | `skills/harnesses/x402-runtime-economics/SKILL.md` | Review comment 3941844912 |
| CREATE | `skills/harnesses/runtime-primitives/SKILL.md` | Review comment 3941844912 |
| CREATE | `skills/harnesses/codex-harness-sdk/SKILL.md` | Review comment 3941844912 |
| CREATE | `skills/harnesses/codex-harness-sdk/references/build-decisions.md` | Review comment 3941846360 |
| MODIFY | `src/vidbyte_cli/commands/runtime/same_host_ensemble.py` | Inputs model, no caller roles |
| MODIFY | `src/vidbyte_cli/lib/runtime_primitives/executor.py` | Admission plus real execution |
| MODIFY | `src/vidbyte_cli/lib/runtime/context.py` | Inject endpoints into the executor |
| MODIFY | `src/vidbyte_cli/lib/errors/failures.py` | Replace scaffold failures with real ones |
| MODIFY | `src/vidbyte_cli/types/runtime.py` | Drop `EnsembleRole` / `EnsembleRoster` |
| MODIFY | `scripts/test_research_only_surface.py` | Precise deleted-symbol tokens |
| MODIFY | `pyproject.toml` | `codex` optional extra, mypy override |
| MODIFY | `README.md` | Document the implemented command |
| MODIFY | `docs/architecture.md` | Narrow the rule-6 exception to adversarial-team |
| MODIFY | `AGENTS.md` | Add `services/` and `skills/` to the repository Map |

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| `vidbyte-sdk[codex]` | `>=0.1.0`, optional extra | `CodexHarnessAgent`, forking, sandbox | Published 0.1.0 predates the codex module; resolved by lazy import plus `EnsembleSdkUnavailable` |
| `openai-codex` | `>=0.147,<0.148` (via the SDK extra) | Codex app-server transport | Pulled transitively; the SDK owns the pin |
| Codex executable | User-installed, found on PATH | The native host each stage runs on | Already covered by `runtime doctor` |
| Vidbyte backend | `/api/x402/runtime/same-host-ensemble/admissions` | Paid admission | Route not deployed until backend PRs land; surfaces as an API error |

The core wheel gains no new hard dependency, so `pip install vidbyte-cli` is unchanged.
`pip install "vidbyte-cli[codex]"` opts into the ensemble.

---

## 11. Rollout & Deployment

- No feature flag. The command is gated by real preconditions instead: the SDK must be
  installed with its codex extra, a Codex executable must be on PATH, and the backend admission
  route must answer.
- Not a breaking change to any shipped command. It *is* a breaking change to the unshipped
  `same-host-ensemble` scaffold's flags — `--role`, `--roles-file`, and `--implementer-prompt`
  are removed. Since the scaffold has never been released and always raised before doing
  anything, no caller can depend on them.
- Deployment order: this CLI change is independent and can merge first. Until the backend
  admission route deploys, the command runs its preconditions and then reports the API failure.
- Rollback: revert the commit. No local user state, credentials, or configuration is written by
  this feature, so nothing needs cleanup.

---

## 12. Open Questions

- [ ] Who absorbs the two cents when admission succeeds but the ensemble then fails? This PR
  charges once, before execution, and reports `charged_cents` in the result so the caller can
  see it. A refund or replay-on-failure policy is a backend decision.
- [ ] Should `--roles` upper bound stay at 8? It is a scaffold-era constant chosen before any
  real cost data existed; nine app-server startups for three roles suggests revisiting once
  per-run cost is measured.
- [ ] `vidbyte` PR #507 versus PR #508 still need reconciling in the backend catalog, and the
  admission route's final path may change. This PR consumes the path PR #25 already declared.
- [ ] Should the planner's generated roles be cached or replayable for a repeated task? Today
  every run regenerates them, which costs one turn but keeps roles matched to the current
  workspace state.

---

## 13. Alternatives Considered

### Alternative 1: Keep caller-supplied roles alongside generated ones

- What: retain `--role`/`--roles-file` as an override, and generate roles only when neither is
  given.
- Why rejected: review comment 3941890823 was explicit that predetermined roles were not asked
  for and should not exist. Keeping them as a fallback would preserve the exact code path the
  review rejected, and would leave two role-construction paths to keep in sync.

### Alternative 2: Chain the roles as sequential handoffs

- What: pass each role's output into the next role, ending at the implementer.
- Why rejected: chaining serializes work the fork API parallelizes for free, and it correlates
  the roles' errors — a bad early framing contaminates everyone downstream. Independent
  branches off one root is what makes an ensemble statistically worth its cost.

### Alternative 3: Add `vidbyte-sdk[codex]` as a hard runtime dependency

- What: put it in `[project.dependencies]` and import at module scope.
- Why rejected: the published `vidbyte-sdk==0.1.0` wheel contains no codex files, verified by
  downloading it. `run_ci.py` installs the built wheel into a clean virtualenv and runs
  `--help`, which imports every command module, so a module-scope import would fail the gate.
  The optional extra plus lazy import is also how the SDK itself handles `openai_codex`.

### Alternative 4: Use `ephemeral=True` forks so role work is never persisted

- What: rely on Codex's ephemeral threads for the "does not save results" property.
- Why rejected: ephemeral threads live only on their owning client connection, and the SDK opens
  a new connection per operation, so the fork would be dead before its child turn resumed it.
  The roadmap's checklist item L02 for ephemeral continuation is still unchecked. Read-only
  sandboxing delivers the same guarantee and is enforced by the provider rather than by
  thread lifetime.

---
