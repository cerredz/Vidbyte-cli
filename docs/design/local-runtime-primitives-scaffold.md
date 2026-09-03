# Design Doc: Local Runtime Primitives CLI Scaffold

**Status:** Draft
**Author:** Codex
**Created:** 2026-09-03
**Last Updated:** 2026-09-03

---

## 1. Overview

This change gives `vidbyte-cli` the stable shell for locally executed runtime primitives: authentication remains tied to a Vidbyte API key, the backend grants a paid and idempotent execution admission, and the CLI preserves the caller's native coding-agent environment by launching from the current working directory. The first namespace is `runtime adversarial-team`; this PR provides its commands, typed API contracts, host discovery, launch-plan boundary, and agent-readable failures, but deliberately does not spawn or orchestrate the adversarial agents.

---

## 2. Goals & Non-Goals

### Goals

- Add a static `runtime` command group with `list`, `doctor`, and `adversarial-team` commands.
- Reuse the existing login, profile, API-key, HTTP, idempotency, output, and error systems.
- Detect supported native hosts (`codex`, `claude`, and `opencode`) without invoking them.
- Build a safe local launch plan that retains the current directory and inherits the child process environment at execution time without uploading it.
- Model the backend capability catalog and paid admission contracts.
- Stop at an explicit executor seam before any sub-agent process is created or any paid admission is requested.
- Return semantic failures that tell an agent how to authenticate, install/select a host, add Vidbyte balance, or wait for the runtime implementation.

### Non-Goals

- Implementing prosecutor, defender, judge, aggregation, fan-in/fan-out, recursion, or any other runtime algorithm.
- Spawning Codex, Claude Code, OpenCode, or provider API calls.
- Copying the parent agent's hidden transcript, private tool handles, skills, or subscription credentials.
- Accepting a Vidbyte API key on the command line or persisting host/provider credentials.
- Implementing an x402 wallet or signing payments inside this CLI; external agents fund the existing Vidbyte wallet through the backend top-up route.
- Adding new test files under the no-tests workflow.

---

## 3. Background & Context

The current CLI is a typed client for hosted Vidbyte harnesses and research. Its credential resolver, keyring storage, `ApiClient`, stable error documents, and invocation-scoped dependency graph already solve the platform concerns a local runtime needs. What is missing is a separate local-runtime domain: hosted harness manifests assume the work runs on Vidbyte infrastructure, while a runtime primitive must retain the coding agent's repository, tools, skills, approvals, and subscription-backed model access.

The correct boundary is a thin local harness. Vidbyte sells admission to its orchestration algorithm; after admission, the CLI will launch the user's installed agent executable inside the existing working directory. Native child processes naturally rediscover repository instructions, local MCP/tool configuration, skills, filesystem state, and the user's own model entitlement. The CLI must not serialize the full environment to Vidbyte because environment variables routinely contain secrets.

The backend already supports API-key wallet funding via x402 at `POST /agent/topup`. A separate backend PR adds an immutable runtime capability and paid admission endpoint. This CLI consumes those contracts but does not attempt direct x402 settlement itself.

---

## 4. Requirements

### Functional Requirements

1. `vidbyte-cli runtime list` must fetch and render the backend's local-runtime capability catalog using the active profile and API key.
2. `vidbyte-cli runtime doctor` must report the current working directory and whether each supported host executable is discoverable, without launching a process.
3. `vidbyte-cli runtime adversarial-team --host auto|codex|claude|opencode <task>` must validate the task, resolve a supported host, and build a launch plan.
4. The adversarial-team command must stop with `RuntimeExecutionNotImplemented` before requesting a paid admission or starting a child process.
5. The endpoint layer must expose a future-ready `admit_adversarial_team` operation with a caller-supplied or generated idempotency key.
6. API-key authentication must continue to resolve environment, keyring, and approved restricted-file credentials through `ApplicationContext.require_credentials`.
7. HTTP 402 must remain the stable `CREDIT_EXHAUSTED` exit path and must tell an agent to fund the same API-key wallet through `POST /agent/topup`.
8. Missing executables, unsupported explicit hosts, empty tasks, invalid admission contracts, and the unimplemented execution boundary must each raise their own `CliError` subclass.
9. `--help` and `--version` must remain free of filesystem, credential, and network side effects.
10. Machine output must retain the existing versioned result/error envelope and stdout/stderr separation.

### Non-Functional Requirements

- Host discovery must complete using local PATH inspection only and normally finish in under 100 ms.
- No environment-variable values, API keys, prompts, repository contents, or subprocess output may appear in error metadata.
- All new Pydantic transport models must reject extra fields and bound authored strings.
- Every new command must use the invocation-scoped context and typed endpoint group; direct `httpx`, `sys.exit`, and global service instances are prohibited.
- Every function and method signature must occupy one line and be immediately followed by a concise implementation comment.
- Existing Ruff, strict mypy, compile, smoke, build, and installed-wheel gates remain required.

---

## 5. High-Level Design

`commands/runtime` adds the stable Click surface. `RuntimeHostRegistry` uses `shutil.which` to describe locally available native agent hosts. `RuntimeLaunchPlanner` validates the working directory and selected host and returns a frozen plan containing only safe execution metadata. `RuntimeExecutor` is an explicit scaffold that raises before network or subprocess work; replacing this class is the future PR's narrow implementation boundary.

`RuntimeEndpoints` and `types/runtime.py` mirror the backend catalog and admission envelopes. `ApplicationContext` lazily constructs these services, preserving the current guarantee that help paths do nothing. Authentication is unchanged: the CLI sends its stored Vidbyte key to obtain admission, while the eventual child process uses the user's existing host configuration and inherits the process environment locally.

```text
[coding agent / shell]
        |
        v
[runtime command] -> [host registry] -> [launch planner] -> [executor scaffold: STOP]
        |
        +-> [existing API key] -> [runtime endpoints] -> [Vidbyte paid admission]
                                                   (wired, not called by scaffold)

Future executor: admission grant -> native host child in current working directory
```

---

## 6. Detailed Design

### 6.1 Runtime Transport Types and Endpoints

**File(s):** `src/vidbyte_cli/types/runtime.py`, `src/vidbyte_cli/lib/api/endpoints/runtime.py`, `src/vidbyte_cli/lib/runtime/context.py`
**Type:** New files and modified composition root

#### What it does

Defines strict capability, admission request, and admission grant models and binds them to the authenticated `ApiClient`. The application context exposes one lazy endpoint instance.

#### Interface / API

```python
class RuntimeCapability(BaseModel): ...


class RuntimeCapabilityCatalog(BaseModel): ...


class RuntimeAdmissionRequest(BaseModel): ...


class RuntimeAdmissionGrant(BaseModel): ...


class RuntimeEndpoints:
    def list_capabilities(self) -> RuntimeCapabilityCatalog: ...
    def admit_adversarial_team(
        self, request: RuntimeAdmissionRequest, idempotency_key: str
    ) -> RuntimeAdmissionGrant: ...
```

#### Logic / Algorithm

1. Fetch the catalog from `GET /api/x402/runtime`.
2. Submit future admissions to `POST /api/x402/runtime/adversarial-team/admissions` with an idempotency key.
3. Validate every successful response before returning it to command code.

#### Edge Cases & Error Handling

- A malformed success response becomes the existing safe API response error.
- Authentication, scope, balance, throttling, and transport failures retain existing status-driven mappings.
- The admission method exists but is unreachable from the scaffold executor.

### 6.2 Native Host Discovery and Launch Planning

**File(s):** `src/vidbyte_cli/lib/runtime_primitives/hosts.py`, `src/vidbyte_cli/lib/runtime_primitives/planner.py`, `src/vidbyte_cli/lib/runtime_primitives/executor.py`, `src/vidbyte_cli/lib/runtime_primitives/__init__.py`
**Type:** New package

#### What it does

Discovers supported executables, selects an explicit or automatic host, validates the current directory, and creates the data that a future executor will use. It intentionally stores no environment snapshot and starts no subprocess.

#### Interface / API

```python
class RuntimeHost(str, Enum): ...


class RuntimeHostStatus(BaseModel): ...


class RuntimeLaunchPlan(BaseModel): ...


class RuntimeHostRegistry:
    def inspect(self) -> tuple[RuntimeHostStatus, ...]: ...
    def resolve(self, requested: RuntimeHost | None) -> RuntimeHostStatus: ...


class RuntimeLaunchPlanner:
    def build(
        self, task: str, requested_host: RuntimeHost | None, working_directory: Path
    ) -> RuntimeLaunchPlan: ...


class RuntimeExecutor:
    def execute_adversarial_team(self, plan: RuntimeLaunchPlan) -> NoReturn: ...
```

#### Logic / Algorithm

1. Inspect PATH for the three reviewed executable names.
2. Prefer Codex, then Claude, then OpenCode when `auto` is selected.
3. Resolve and validate the working directory and bounded non-empty task.
4. Return a frozen plan with host, executable path, working directory, primitive identity, and task.
5. Raise the typed implementation-boundary failure before admission or process creation.

#### Edge Cases & Error Handling

- No installed host raises `RuntimeHostUnavailable` with install/select guidance.
- An explicit missing host does not silently fall back to another executable.
- A nonexistent or non-directory working path raises `RuntimeWorkingDirectoryInvalid`.
- Environment values are inherited only by a future subprocess and never rendered or uploaded.

### 6.3 Runtime Commands and Presentation

**File(s):** `src/vidbyte_cli/commands/runtime/list.py`, `src/vidbyte_cli/commands/runtime/doctor.py`, `src/vidbyte_cli/commands/runtime/adversarial_team.py`, `src/vidbyte_cli/commands/runtime/__init__.py`, `src/vidbyte_cli/commands/__init__.py`
**Type:** New command package and modified registry

#### What it does

Registers the local-runtime group and presents catalog, environment diagnosis, and first-primitive launch planning through the existing output manager.

#### Interface / API

```python
class RuntimeListCommand:
    def register(self, parent: click.Group) -> None: ...
    def execute(self, context: ApplicationContext) -> None: ...


class RuntimeDoctorCommand:
    def register(self, parent: click.Group) -> None: ...
    def execute(self, context: ApplicationContext) -> None: ...


class AdversarialTeamCommand:
    def register(self, parent: click.Group) -> None: ...
    def execute(self, context: ApplicationContext, task: str, host: str) -> None: ...
```

#### Logic / Algorithm

1. Register one static `runtime` group during normal command-tree construction.
2. Keep list authenticated and network-backed; keep doctor local and read-only.
3. Let adversarial-team resolve a launch plan and pass it to the executor scaffold.

#### Edge Cases & Error Handling

- Help returns before any command service is built.
- JSON results contain only safe host/capability metadata.
- The adversarial command never reports success while execution is absent.

### 6.4 Agent-Native Failures and Documentation

**File(s):** `src/vidbyte_cli/lib/errors/failures.py`, `README.md`, `docs/architecture.md`
**Type:** Modified

#### What it does

Adds specific local-runtime failures and documents the local execution/payment boundary.

#### Interface / API

```python
class RuntimeHostUnavailable(CliError): ...


class RuntimeWorkingDirectoryInvalid(CliError): ...


class RuntimeTaskInvalid(CliError): ...


class RuntimeExecutionNotImplemented(CliError): ...
```

#### Logic / Algorithm

1. Raise failures at the layer that has enough context to classify them.
2. Let the existing single `ErrorHandler` match the common `CliError` base.
3. Keep descriptions and traces static and secret-free.

#### Edge Cases & Error Handling

- HTTP 402 guidance names the central top-up route without echoing a backend response body.
- Debug output remains frame-only and redacted.

---

## 7. Data Model Changes

### 7.1 CLI Runtime Contracts

**Change type:** New

```json
{
  "capability_id": "runtime.review.adversarial-team",
  "version": "1",
  "execution_location": "local",
  "supported_hosts": ["codex", "claude", "opencode"],
  "admission_price_cents": 25
}
```

**Migration strategy:**

- Forward migration: additive Python types; no persisted CLI schema changes.
- Rollback plan: remove the command group and types; existing credentials/configuration remain untouched.

---

## 8. API Changes

### 8.1 GET /api/x402/runtime

**Change type:** New consumer

**Request:**

```json
{}
```

**Response:**

```json
{
  "capabilities": [
    {
      "capability_id": "runtime.review.adversarial-team",
      "version": "1",
      "execution_location": "local",
      "supported_hosts": ["codex", "claude", "opencode"],
      "admission_price_cents": 25
    }
  ],
  "topup_path": "/agent/topup"
}
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| 401 | API key is absent or rejected |
| 403 | API key lacks runtime read scope |
| 503 | Backend is unavailable |

### 8.2 POST /api/x402/runtime/adversarial-team/admissions

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
  "capability_id": "runtime.review.adversarial-team@1",
  "execution_location": "local",
  "charged_cents": 25,
  "admitted_at": "RFC 3339 timestamp"
}
```

**Error cases:**

| Status | Condition |
|--------|-----------|
| 400/422 | Invalid host or runtime version |
| 401/403 | API key invalid or missing execution scope |
| 402 | Wallet must be funded through `POST /agent/topup` |
| 409 | Idempotency key reused with different input |
| 429 | API-key request budget exhausted |
| 503 | Billing or backend unavailable |

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/local-runtime-primitives-scaffold.md` | Source-of-truth CLI design and boundary |
| CREATE | `src/vidbyte_cli/types/runtime.py` | Typed catalog, admission, host, and plan contracts |
| CREATE | `src/vidbyte_cli/lib/api/endpoints/runtime.py` | Typed runtime backend operations |
| CREATE | `src/vidbyte_cli/lib/runtime_primitives/__init__.py` | Runtime package exports |
| CREATE | `src/vidbyte_cli/lib/runtime_primitives/hosts.py` | Native agent executable discovery |
| CREATE | `src/vidbyte_cli/lib/runtime_primitives/planner.py` | Safe launch-plan construction |
| CREATE | `src/vidbyte_cli/lib/runtime_primitives/executor.py` | Explicit no-execution scaffold boundary |
| CREATE | `src/vidbyte_cli/commands/runtime/__init__.py` | Runtime command exports |
| CREATE | `src/vidbyte_cli/commands/runtime/list.py` | Capability catalog command |
| CREATE | `src/vidbyte_cli/commands/runtime/doctor.py` | Local host/environment diagnostics |
| CREATE | `src/vidbyte_cli/commands/runtime/adversarial_team.py` | First primitive command shell |
| MODIFY | `src/vidbyte_cli/commands/__init__.py` | Register the static runtime group |
| MODIFY | `src/vidbyte_cli/lib/runtime/context.py` | Lazily compose runtime services |
| MODIFY | `src/vidbyte_cli/lib/runtime/application.py` | Update root help for local runtimes |
| MODIFY | `src/vidbyte_cli/lib/errors/failures.py` | Add typed runtime failures and top-up guidance |
| MODIFY | `README.md` | Document commands, local execution, and payment model |
| MODIFY | `docs/architecture.md` | Document the local-runtime layer and executor seam |
| MODIFY | `scripts/test_research_only_surface.py` | Reconcile the existing exact command-surface gate |

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Vidbyte backend | `/api/x402/runtime`, `/agent/topup` | Capability discovery, paid admission, wallet funding | CLI and backend contracts must deploy compatibly |
| Codex CLI | User-installed | Future native-agent host | Command-line invocation contract can change by host version |
| Claude Code | User-installed | Future native-agent host | Subscription and permissions remain user-managed |
| OpenCode | User-installed | Future native-agent host | Executable availability and flags vary by installation |

No new Python package dependency is added.

---

## 11. Rollout & Deployment

- Merge and deploy the backend capability/admission PR before releasing a CLI that invokes admission.
- This scaffold may ship first because the executor raises before the paid request and the list command reports backend availability honestly.
- The future executor PR must change the execution boundary only after its primitive algorithm is implemented and verified.
- The change is additive; existing commands, profiles, and credentials require no migration.
- Roll back by removing the runtime command registration; no local user state needs cleanup.

---

## 12. Open Questions

- [x] Should the CLI upload a full environment snapshot? No; the native child inherits environment locally and secrets never cross the admission API.
- [x] Should this CLI sign x402 payments? No; the central backend top-up route is the payment protocol boundary.
- [x] Should the scaffold charge before the runtime exists? No; the executor fails before calling admission.
- [ ] Which reviewed non-interactive invocation contract should the first executor use for each host?
- [ ] Should a later release permit an explicit environment allowlist in addition to natural child-process inheritance?

---

## 13. Alternatives Considered

### Alternative 1: Extend Hosted Harness Manifests

- What: Model adversarial-team as another backend harness command.
- Why rejected: Hosted execution loses the parent coding agent's local tools, skills, approvals, repository state, and subscription-backed model access.

### Alternative 2: Reimplement Every Agent Host

- What: Build Vidbyte-owned filesystem, shell, skill, MCP, permission, and context systems for every runtime.
- Why rejected: It duplicates the core value of native coding agents and creates a large, permanently drifting compatibility surface.

### Alternative 3: Upload the Whole Process Environment

- What: Serialize environment variables and local configuration into the admission request.
- Why rejected: It creates a severe credential-exfiltration boundary and is unnecessary when the primitive runs as a local child process.

### Alternative 4: Charge Provider Usage Through Vidbyte

- What: Route every sub-agent model call through Vidbyte-owned API keys and meter tokens centrally.
- Why rejected: It strips the user's native agent subscription and host features; the flat admission charges for Vidbyte's algorithm while model usage remains with the user's host.
