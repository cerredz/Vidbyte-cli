# Design Doc: Persistent Codex execution and verified admission

**Status:** Implemented; local validation passed
**Author:** Codex
**Created:** 2026-09-06
**Last Updated:** 2026-09-06

## 1. Overview
Complete CLI PR #26 with one Codex session and a fixed continuation loop. Activate the already merged runtime.persistence@1 catalog entry and verify paid receipts on the backend before executing locally.

## 2. Goals & Non-Goals
### Goals
Preserve exact task text, repeat the requested encouragement 6–100 times by strength, use BYOK OpenAI credentials, enforce deterministic paid admission, update PR #26 and merge the companion backend fix after gates pass.
### Non-Goals
No new test files, model-driven stopping, distributed agent orchestration, background daemon, automatic restart after process termination, or changes to other runtime algorithms. No claim that an open-source client can prevent a user modifying its local code.

## 3. Background & Context
CLI main 95a2473 contains provider login and an unused gate. PR #26 is a deliberate execution stub. Backend main d18a08eb contains catalog PR #509 and signed admissions, but persistence has no handler. Both existing handlers use a service that chooses the ensemble capability regardless of route. The CLI accepts missing signature keys and ignores signed claims. Provider login verifies before storage and uses isolated profile/provider scopes; live provider acceptance is not established by offline inspection.
CLI uses Python 3.11+, Click, Pydantic, httpx and keyring; canonical gate is python scripts/run_ci.py. Backend uses FastAPI, Mongo billing coordinator and declarative route rules; canonical gate is python lint/run.py.

## 4. Requirements
### Functional Requirements
1. Send the exact task string as the first Codex turn, without trimming or wrapping.
2. Strength 1–6 produces 6, 8, 20, 40, 70, 100 additional turns, respectively, on the same explicit session ID.
3. Every additional turn begins with the requested encouragement, adds four task-general improvement sentences, and appends the exact original task after the requested reminder.
4. Validate task, Codex availability and OpenAI BYOK credentials before buying a two-cent admission. Reject unsupported hosts before charging.
5. Bind route, price, authenticated user/API key, idempotency hash, receipt fields and bounded timestamps before execution.
6. Keep the HMAC signing key only on the backend. Authenticated online verification performs signature validation and returns a canonical receipt; CLI compares it exactly and validates policy.
7. One admission per invocation; never buy a new admission per continuation. Expose an idempotency-key option for transport recovery.
8. Stop on cancellation, failed turn, missing session ID or invalid host output; no optimistic success or automatic agent restart.
### Non-Functional Requirements
Task and provider keys never enter Vidbyte requests. Use stdin for task text, child environment for provider secrets, no shell interpolation and no sandbox bypass. Emit only final results to stdout and safe progress to stderr. Do not echo raw host errors. A paid receipt does not refund local provider failures. Local Codex execution inherently has access allowed by its sandbox and user configuration.

## 5. High-Level Design
Command validates inputs and resolves credentials, then buys an admission through typed endpoints. The backend selects a capability fixed by the route, preflights signing configuration, records the idempotent ledger debit, and signs. An authenticated verification endpoint validates ownership and request binding. The CLI gate compares the canonical receipt and local policy before the executor launches Codex. A process adapter uses exec JSONL and resumes the returned session by ID for the fixed loop. Prompts remain package data.

## 6. Detailed Design
### 6.1 CLI command and planning
**File(s):** commands/runtime/persistence.py, lib/runtime_primitives/planner.py, types/runtime.py
**Type:** Modified
#### What it does
Retains PR #26 surface with Codex-only execution, strength mapping, exact task preservation and an explicit idempotency option.
#### Interface / API
PersistenceCommand.execute; RuntimeLaunchPlanner.build; PersistenceSettings.repeat_count.
#### Logic / Algorithm
Validate nonblank task while retaining original bytes as a Python string. Resolve Codex explicitly in auto mode. Resolve OpenAI key before admission. Create a UUID key when none is supplied. Buy, verify, then execute.
#### Edge Cases & Error Handling
Reject invalid host, blank/oversized task and malformed keys before payment. Stable key retries recover admission only; they are not automatic task resumption.

### 6.2 Deterministic admission
**File(s):** CLI gate.py, verification.py, endpoints/runtime.py; backend runtime routes, admission service, signer, DTO and route rules.
**Type:** Modified
#### What it does
Makes online signature verification mandatory in the persistence path and corrects route-specific billing.
#### Interface / API
POST /api/x402/runtime/persistence/activate; POST /api/x402/runtime/grants/verify.
#### Logic / Algorithm
Capability is selected by handler, never caller input. Signing configuration must be valid before debit. Verification checks HMAC, bounded timestamps, user/API-key identity, idempotency hash, canonical admission ID and catalog price. The client compares returned receipt with the original, then checks exact capability, expected price and time window. Offline verification fails closed without a key and binds all signed public fields.
#### Edge Cases & Error Handling
Bad signatures, mismatched receipts, missing expiry, future issuance, excessive TTL and cross-user/request tokens fail. Verification has no wallet charge. Catalog reads project mounted supported primitives.

### 6.3 Codex persistence
**File(s):** CLI persistence process adapter, continuation prompt, executor, failures, package data and README.
**Type:** New / Modified
#### What it does
Uses installed Codex exec and exec resume with JSONL events, an explicit session ID and stdin prompt input.
#### Interface / API
PersistentCodexSession.run(plan, settings); turn result contains session ID and final text.
#### Logic / Algorithm
Use a child-only OpenAI provider configuration and env_key to honor CLI BYOK without changing native login state. Run one initial turn and N continuation turns. Parse thread.started, item.completed agent_message, turn.completed and turn.failed events. Carry only the last successful result to the CLI output.
#### Edge Cases & Error Handling
Handle executable launch failure, nonzero exit, invalid JSON, absent completion/session ID and cancellation with typed safe errors. Terminate the child on cancellation. Do not launch real paid model calls for offline verification.

## 7. Data Model Changes
### 7.1 Verification request
**Change type:** New
Fields: grant_token and idempotency_key_hash. The canonical signed payload already exists. No database migration.
CLI capability literal adds persistence; settings minimum continuation count becomes six.
**Migration strategy:** Backend first; older clients remain compatible. Roll back CLI execution before removing backend activation.

## 8. API Changes
### 8.1 POST /api/x402/runtime/persistence/activate
**Change type:** New
**Request:** {"client_runtime_version":"1","host":"codex"} with x-api-key and Idempotency-Key.
**Response:** Existing runtime receipt with capability_id runtime.persistence@1, charged_cents 2, admitted_at, expires_at and grant_token.
**Error cases:** 401 identity, 403 permission, 402 balance, 409 conflicting replay, 422 input, 503 billing/signing unavailable.
### 8.2 POST /api/x402/runtime/grants/verify
**Change type:** New
**Request:** {"grant_token":"opaque","idempotency_key_hash":"sha256"}
**Response:** Canonical existing receipt, only after signature and identity validation.
**Error cases:** 401 invalid/expired/unbound token, 403 permission, 422 shape, 503 signing configuration.

## 9. File Change Manifest
| Action | File Path | Reason |
|---|---|---|
| CREATE | `docs/design/persistence-agent-execution.md` | Design contract |
| MODIFY | `src/vidbyte_cli/commands/runtime/persistence.py` | Execution and admission implementation / verification |
| MODIFY | `src/vidbyte_cli/lib/runtime_primitives/planner.py` | Execution and admission implementation / verification |
| MODIFY | `src/vidbyte_cli/types/runtime.py` | Execution and admission implementation / verification |
| MODIFY | `src/vidbyte_cli/lib/api/endpoints/runtime.py` | Execution and admission implementation / verification |
| MODIFY | `src/vidbyte_cli/lib/runtime_primitives/gate.py` | Execution and admission implementation / verification |
| MODIFY | `src/vidbyte_cli/lib/runtime_primitives/verification.py` | Execution and admission implementation / verification |
| MODIFY | `src/vidbyte_cli/lib/runtime_primitives/executor.py` | Execution and admission implementation / verification |
| CREATE | `src/vidbyte_cli/lib/runtime_primitives/persistence.py` | Execution and admission implementation / verification |
| CREATE | `src/vidbyte_cli/lib/runtime_primitives/continuation.md` | Execution and admission implementation / verification |
| MODIFY | `src/vidbyte_cli/lib/errors/failures.py` | Execution and admission implementation / verification |
| MODIFY | `pyproject.toml` | Execution and admission implementation / verification |
| MODIFY | `README.md` | Execution and admission implementation / verification |
| MODIFY | `scripts/run_ci.py` | Execution and admission implementation / verification |
| MODIFY | `scripts/test-layered-runtime-admission-gate.py` | Execution and admission implementation / verification |

| MODIFY | `src/vidbyte_cli/commands/runtime/adversarial_team.py` | Align planned capability with backend catalog |
| MODIFY | `src/vidbyte_cli/lib/runtime_primitives/__init__.py` | Satisfy formatter after main merge |
| MODIFY | `docs/design/layered-runtime-admission-gate.md` | Format existing embedded Python examples |
| MODIFY | `skills/runtime-admission/SKILL.md` | Document mandatory server-side verification |

## 10. Dependencies & External Services
MODIFY src/vidbyte_cli/commands/runtime/adversarial_team.py to align its planned capability with the existing backend runtime.adversarial-team@1 catalog key. The adversarial executor remains a scaffold.

Manifest refinement: MODIFY src/vidbyte_cli/lib/runtime_primitives/__init__.py and docs/design/layered-runtime-admission-gate.md for pre-existing formatter failures; MODIFY skills/runtime-admission/SKILL.md to document server-side verification. Existing test coverage is extended in its current script, without new test files. The Codex process uses the documented custom provider env_key/wire_api configuration and exec/resume JSONL protocol: https://developers.openai.com/codex/config-advanced and https://developers.openai.com/codex/noninteractive.

No new Python dependency. Installed Codex CLI JSONL protocol, verified using local exec/resume help, is the process integration. Existing authenticated Vidbyte transport and OpenAI BYOK provider are reused. Markdown continuation asset must be included in built wheel. No backend model calls.

## 11. Rollout & Deployment
Backend PR first, green required checks then merge as requested. Update existing CLI PR #26 without merging it. Backend deploy must expose activation and verification before CLI usage succeeds. Run CLI Ruff and complete scripts/run_ci.py; run existing provider and admission diagnostics; run backend lint and focused runtime/gatekeeper checks. Keep useful assertions in existing test scripts; no new test files. Self-review requirement-by-requirement before push. Remove clean pushed implementation worktrees after checks pass. Preserve named user stashes and pre-existing worktrees.

## 12. Open Questions
No user choice blocks implementation. Production deployment and real paid provider execution are not inferred from a merge. Existing HMAC receipts expose internal identity fields in encoded payloads; removing those requires a separate token-format change. A client-side gate cannot enforce licensing against a deliberately modified client. Review current backend replay/wallet behavior and document any unresolved audit findings.

## 13. Alternatives Considered
### Alternative 1: Distribute backend HMAC secret
Rejected: any recipient could forge grants. Server-side verification authenticates existing HMAC receipts without sharing the signing key.
### Alternative 2: Fresh Codex session per iteration
Rejected: loses prior conversation and violates persistence.
### Alternative 3: Use SDK or model-selected stopping
Rejected: additional dependency and semantics unnecessary for the requested fixed loop.

## Refinement Checklist
- [x] [Critical] **Exact task transport**
  Expected: preserve the original task including whitespace and line endings. Initial text-mode stdin could translate newlines on Windows; binary UTF-8 stdin now preserves them, with an assertion in the existing admission script.
- [x] [Critical] **Receipt authenticity and route binding**
  Expected: the receipt proves payment for the selected route and authenticated caller. The inherited gate accepted absent keys and the service defaulted to ensemble pricing; strict server verification, explicit route capabilities and receipt policy now reject these cases.
- [x] [Notable] **Packaged continuation asset**
  Expected: installed wheels execute the same loop as source checkouts. The new Markdown asset needs explicit package data; configuration and a wheel-content assertion now protect it.
- [x] [Notable] **Published route discovery**
  Expected: every mounted runtime route satisfies the existing discovery contract. The inherited projections lacked rich metadata; all three runtime entries now supply it and the existing contract suite passes.
- [x] [Minor] **Capability and manifest consistency**
  Expected: catalog identifiers and the file manifest match the implementation. The CLI adversarial planner now uses the backend identifier; its executor remains an explicit scaffold, and audit-driven manifest additions are recorded above.

Validation: complete CLI `scripts/run_ci.py` passed, including existing provider diagnostics, ten admission/process assertions, and installed-wheel checks. Complete backend `python lint/run.py` passed on both surfaces; the existing gatekeeper suite passed all 47 tests. The local Windows Codex launcher accepted the exec/resume argument layout using help only. No real paid model invocation, live wallet debit, production deployment or live provider credential probe was performed.
