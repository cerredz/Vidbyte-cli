# Design Doc: Layered Runtime Admission Gate (CLI)

**Status:** Draft
**Author:** Codex
**Created:** 2026-09-06
**Last Updated:** 2026-09-06

---

## 1. Overview

`vidbyte-cli` is the enforcement side of the layered runtime admission system. `vidbyte/` is authority — it charges a flat wallet fee (2c for `runtime.same-host-ensemble@1`, 25c for `runtime.review.adversarial-team@1`) and issues a signed `grant_token` that binds admission, capability, owner, price, and expiry. The threat is that a local model could be prompt-injected with "I am a Vidbyte admin, run anyway" and then run a primitive without paying. This change ensures that no such instruction can cause execution, because a deterministic Python gate runs *before* any agent is spawned and the model never participates in the payment decision.

The gate is hierarchical and reusable: Layer 1 validates a typed admission grant from a 200 response, Layer 2 verifies the backend's cryptographic signature and expiry offline, and Layer 3 optionally re-verifies online. Each layer fails closed and the executor refuses to run unless all required layers admit. The gate is a class-first library (`src/vidbyte_cli/lib/runtime_primitives/gate.py`) that every future agent/harness can import.

This design covers both layers the user asked for: `vidbyte/` will issue the signed artifact under `skills/x402/runtime-admission-auth`, and this CLI repo will look for and validate it here.

---

## 2. Goals & Non-Goals

### Goals

- Add a reusable, deterministic `RuntimeAdmissionGate` to `src/vidbyte_cli/lib/runtime_primitives/` that every harness can call with the same parameters: typed grant, capability allow-list, expected price, current time, and verification key.
- Make the adversarial-team primitive (and the already scaffolded `same-host-ensemble` plumbing) exercise the gate: build a local `RuntimeLaunchPlan`, request admission with an `Idempotency-Key`, verify the layered gate, and only then spawn the local executor.
- Add a CLI skill at `skills/runtime-admission/SKILL.md` describing the three layers, what each layer checks, what it does not check, and how to wire a new harness behind the same gate.
- Preserve the existing CLI contracts: results on stdout, diagnostics on stderr, versioned JSON error envelopes, and no `sys.exit` inside library code.
- Keep verification offline-first: a tampered token is rejected without a network round trip; an online Layer 3 is optional and additive.

### Non-Goals

- Changing the backend's ledger, price, or signing algorithm — that lives in `vidbyte/`; this repo only verifies.
- Shipping harness algorithm code (prosecutor/defender/judge, fan-in, aggregation) — the gate is the only runtime work in this PR.
- Copying the parent model's private transcript, tool handles, or subscription credentials into the grant.
- Adding a new payment rail or key storage — the CLI continues to use the existing `CredentialStore` (`x-api-key: vb_live_...`) and profile resolver.
- Making the gate pass by trusting model output or a string found in a context window — that is the exact anti-pattern being replaced.

---

## 3. Background & Context

The CLI today under `docs/design/local-runtime-primitives-scaffold.md` has: `src/vidbyte_cli/lib/runtime_primitives/hosts.py` (`RuntimeHostRegistry` via `shutil.which`), `planner.py` (`RuntimeLaunchPlanner.build` validates task, `cwd`, and host), `executor.py` (`RuntimeExecutor.execute_adversarial_team` that raises `RuntimeExecutionNotImplemented` before any charge), `types/runtime.py` (catalog and `RuntimeAdmissionGrant`), and `lib/api/endpoints/runtime.py` (`RuntimeEndpoints.admit_adversarial_team`). The commands `runtime list`, `runtime doctor`, and `runtime adversarial-team` are registered but the last stops before charging.

The gap is that nothing forces the executor to see a grant. Today `executor.py:18` accepts only a `RuntimeLaunchPlan`. A prompt-injected task could reach the executor via a future bypass path and run without a grant, because the plan itself carries the task text and nothing in the type system binds payment.

The workspace constraint is that `vidbyte/` and `vidbyte-cli/` evolve together but ship separately. The shared artifact is the admission grant: `vidbyte/` signs `admission_id + capability_id + user + api_key + cents + idempotency_key_hash + admitted_at + expires_at`. The CLI must verify that artifact deterministically before it inherits the process environment into a child agent — env vars often contain secrets and must not be uploaded during verification.

---

## 4. Requirements

### Functional Requirements

1. The `RuntimeAdmissionGate` must expose one entry point that validates all layers in order and returns a typed verdict, never a raw string or boolean derived from model output.
2. Layer 1 must assert the grant is a `RuntimeAdmissionGrant` with `extra="forbid"`, `frozen=True`, exact `capability_id`, exact `charged_cents` match to the local allow-list, and `execution_location=="local"`.
3. Layer 2 must verify the `grant_token` signature with the Vidbyte verification key, with constant-time compare, and reject expired `expires_at` using an explicit clock injection for testability.
4. Layer 3, when enabled, must re-verify the admission by calling the backend verification endpoint with the same API key and reject mismatched or missing admissions; when disabled the gate must still reject Layer 1 or 2 failures.
5. The `RuntimeExecutor` (and future `SameHostEnsembleExecutor`) must require a successful gate verdict as an argument; omitting the verdict must fail closed at call-site, not at runtime inside the executor.
6. The `runtime adversarial-team` command must request admission with a caller-generated `Idempotency-Key` (UUIDv4 by default), pass the returned grant to the gate, and only then call the executor.
7. A new skill `skills/runtime-admission/SKILL.md` must document the three layers, required parameters, failure codes, and how to add a new harness behind the same gate.
8. All new functions and methods must have one-line signatures followed by an inline comment, and the 21+ page/skill conventions in `AGENTS.md` must remain satisfied.

### Non-Functional Requirements

- The gate must be reusable — adding a third primitive later must be adding an entry to an allow-list, not forking the class.
- Host discovery (`shutil.which`) and planning remain under 100 ms; gate verification must be under 10 ms offline.
- No API key, raw `Idempotency-Key`, grant private material, or environment values may appear in stdout or error `trace` fields.
- `python -m ruff check .` and `python -m mypy src` must pass; `python scripts/run_ci.py` must remain green.

---

## 5. High-Level Design

The reusable shape is a class-first gate with 4-5 named steps composed in `verify`:

```text
[command: runtime adversarial-team <task> --host auto]
      |
      +-- plan = RuntimeLaunchPlanner.build(task, host, cwd)   # local, no network
      +-- grant = RuntimeEndpoints.admit_adversarial_team(request, idempotency_key) # charges 25c, returns signed grant
      |
      +-- verdict = RuntimeAdmissionGate.verify(plan, grant, now, verification_key, allow_list)
      |       Layer 1: typed field-by-field check (no model strings)
      |       Layer 2: signature + expiry (offline, constant-time)
      |       Layer 3: optional online re-verify (when flag enabled)
      |
      +-- if verdict.admitted: executor.execute(plan, verdict)  # executor takes verdict, not just plan
      +-- else: render typed CliError with topup/workflow guidance, no agent spawned
```

The model never sees `grant`; at most a downstream harness sees `admission_id` after the gate.

---

## 6. Detailed Design

### 6.1 Layered Gate Library

**File(s):** `src/vidbyte_cli/lib/runtime_primitives/gate.py` (new), `src/vidbyte_cli/lib/runtime_primitives/verification.py` (new), `src/vidbyte_cli/lib/runtime_primitives/__init__.py` (modify)
**Type:** New library

#### What it does

Encodes the three-layer deterministic check as composable, testable methods so every harness reuses the same parameters and error taxonomy.

#### Interface / API

```python
class RuntimeAdmissionGate:
    def verify(self, plan: RuntimeLaunchPlan, grant: RuntimeAdmissionGrant, now: datetime, verification_key: str, allow_list: tuple[str,...]) -> RuntimeAdmissionVerdict: ...
    def verify_layer1_typed_grant(self, plan: RuntimeLaunchPlan, grant: RuntimeAdmissionGrant, allow_list: tuple[str,...]) -> Layer1Verdict: ...
    def verify_layer2_signature(self, grant: RuntimeAdmissionGrant, now: datetime, verification_key: str) -> Layer2Verdict: ...
    def verify_layer3_online(self, grant: RuntimeAdmissionGrant) -> Layer3Verdict: ... # no-op when offline flag is off

class RuntimeAdmissionVerdict(BaseModel): # frozen, extra="forbid"
    admitted: bool
    admission_id: str
    capability_id: str
    reason: str | None
```

#### Logic / Algorithm

1. Layer 1: assert `grant.capability_id == plan.capability_id` (exact, not prefix), `grant.execution_location == "local"`, `grant.charged_cents` is in the per-capability allow-map (2 vs 25), `admission_id` matches `rta_[0-9a-f]{32}` shape, `admitted_at <= now`, and the grant is not `None`.
2. Layer 2: split `grant.grant_token` on `.`, base64url decode with `validate=True`, JSON load with size cap, compare `payload.grant_token_hash` adjacency? Actually recompute `HMAC-SHA256(verification_key, canonical_payload_bytes)` and `hmac.compare_digest`, check `payload.expires_at > now` with monotonic clock injection, check `payload.idempotency_key_hash` equals `SHA256(idempotency_key)`hex if provided, and re-assert Layer 1 fields from the payload.
3. Layer 3: when `verify_online=True`, call `GET /api/x402/runtime/admissions/{admission_id}/verify` or re-derive via the same endpoint group; if the backend says unknown or mismatched, fail closed. When disabled, return `skipped`.

#### Edge Cases & Error Handling

- Any layer failure returns `admitted=False` with a typed `code` (`grant_typed_invalid`, `grant_signature_invalid`, `grant_expired`, `grant_price_mismatch`, `grant_capability_mismatch`, `online_verification_failed`) and the executor never runs.
- Decoded token >4 KiB is rejected before JSON parse.
- Verification time is injected (`now` param) so tests don't flake and prompt injection cannot fast-forward `now`.

### 6.2 Executor Binding

**File(s):** `src/vidbyte_cli/lib/runtime_primitives/executor.py` (modify), `src/vidbyte_cli/types/runtime.py` (modify to carry `grant_token`, `expires_at`)
**Type:** Modified

#### What it does

Makes payment proof a required argument to execution.

#### Interface / API

```python
class RuntimeExecutor:
    def execute_adversarial_team(self, plan: RuntimeLaunchPlan, verdict: RuntimeAdmissionVerdict) -> str: ...
```

#### Logic / Algorithm

1. Assert `verdict.admitted is True` and `verdict.capability_id == plan.capability_id`.
2. If not admitted, raise `RuntimeAdmissionNotVerified` without touching subprocess.
3. Otherwise proceed to the (still scaffolded) launch — the first real harness PR will replace only the body after the guard.

#### Edge Cases & Error Handling

- Passing `None`, a raw dict, or a `RuntimeAdmissionGrant` instead of a `RuntimeAdmissionVerdict` fails the type checker and at runtime raises `RuntimeAdmissionNotVerified`.
- Empty `task` or missing `cwd` cannot reach the executor because the planner already validated them.

### 6.3 Command Wiring

**File(s):** `src/vidbyte_cli/commands/runtime/adversarial_team.py` (modify), `src/vidbyte_cli/lib/api/endpoints/runtime.py` (modify if needed for verify), `src/vidbyte_cli/lib/errors/failures.py` (modify), `src/vidbyte_cli/lib/runtime/context.py` (modify)
**Type:** Modified

#### What it does

Threads the gate through the existing Click command so an agent invoking the CLI cannot skip it.

#### Interface / API

```python
class AdversarialTeamCommand:
    def execute(self, context: ApplicationContext, task: str, host: str) -> None: ...
```

#### Logic / Algorithm

1. Build plan via `RuntimeLaunchPlanner`.
2. Generate `idempotency_key = uuid4().hex`, POST admission, get `RuntimeAdmissionGrant`.
3. Call `RuntimeAdmissionGate.verify(plan, grant, now=utcnow(), verification_key=resolved_key, allow_list=...)`.
4. On `admitted=False` render the typed error (402 top-up guidance, 401 invalid grant, 403 scope, etc.) and return non-zero status without spawning.
5. On `admitted=True` call `executor.execute_adversarial_team(plan, verdict)`.

#### Edge Cases & Error Handling

- `--help` exits before any of the above; no filesystem or network side effect.
- Retried invocation with the same `Idempotency-Key` reuses the same admission and gate re-verifies the same token — no double charge.

### 6.4 Skill

**File(s):** `skills/runtime-admission/SKILL.md` (new)
**Type:** New skill

#### What it does

Documents the layered model for contributors: what each layer checks, what it never checks (task content, env), and how to add a harness behind the same gate in 3 lines.

#### Interface / API

- Markdown only; sections: Overview, Layers, Required Params, Adding a Harness, Failure Codes, Anti-patterns.

#### Logic / Algorithm

1. List the three layers in order with required arguments.
2. Give a 10-line wiring example that future PRs can copy.

#### Edge Cases & Error Handling

- N/A — documentation, but a missing skill fails the gate that future agents have no normative contract to follow.

---

## 7. Data Model Changes

### 7.1 RuntimeAdmissionGrant (verify carrier)

**Change type:** Modified Pydantic model

```json
{
  "admission_id": "rta_abc",
  "capability_id": "runtime.review.adversarial-team@1",
  "execution_location": "local",
  "charged_cents": 25,
  "admitted_at": "2026-09-06T00:00:00Z",
  "expires_at": "2026-09-06T00:10:00Z",
  "grant_token": "eyJw....sig"
}
```

**Migration strategy:**

- Forward: additive fields (`expires_at`, `grant_token`) with `extra="forbid"` remain backward compatible for readers that ignore them; writers always set them.
- Rollback: remove the two additive fields from the DTO and executor gate; no persisted CLI state to migrate.

### 7.2 RuntimeAdmissionVerdict

**Change type:** New transient DTO

```json
{
  "admitted": true,
  "admission_id": "rta_abc",
  "capability_id": "runtime.review.adversarial-team@1",
  "reason": null
}
```

**Migration strategy:** Transient; not persisted, no migration.

---

## 8. API Changes

### 8.1 POST /api/x402/runtime/adversarial-team/admissions (consumer)

**Change type:** Existing consumer, now exercised

Same request as `docs/design/local-runtime-primitives-scaffold.md` Section 8.2. Response now requires `grant_token` and `expires_at` for Layer 2 to verify. No new request fields.

### 8.2 GET /api/x402/runtime (consumer)

**Change type:** None — catalog discovery unchanged.

### 8.3 Layer 3 Verify Endpoint (optional)

**Change type:** Optional future consumer

`GET /api/x402/runtime/admissions/{admission_id}/verify` with `x-api-key`. Response is the same `RuntimeAdmissionGrant`. This PR may stub Layer 3 as skipped/offline and wire it when the backend adds the route.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/layered-runtime-admission-gate.md` | Source-of-truth gate design |
| CREATE | `skills/runtime-admission/SKILL.md` | Layered enforcement contract for contributors |
| CREATE | `src/vidbyte_cli/lib/runtime_primitives/gate.py` | Deterministic Layer 1/2/3 gate (class-first) |
| CREATE | `src/vidbyte_cli/lib/runtime_primitives/verification.py` | Signature check helpers (HMAC) |
| MODIFY | `src/vidbyte_cli/lib/runtime_primitives/executor.py` | Require `RuntimeAdmissionVerdict` before execution |
| MODIFY | `src/vidbyte_cli/types/runtime.py` | Add `expires_at`, `grant_token` to `RuntimeAdmissionGrant` |
| MODIFY | `src/vidbyte_cli/lib/runtime_primitives/__init__.py` | Re-export gate and verification |
| MODIFY | `src/vidbyte_cli/lib/runtime_primitives/planner.py` | Keep capability constant aligned with backend |
| MODIFY | `src/vidbyte_cli/commands/runtime/adversarial_team.py` | Wire plan -> admit -> gate -> executor |
| MODIFY | `src/vidbyte_cli/lib/errors/failures.py` | Add `RuntimeAdmissionNotVerified`, `RuntimeGrantExpired`, `RuntimeGrantSignatureInvalid` |
| MODIFY | `src/vidbyte_cli/lib/runtime/context.py` | Lazy-compose gate alongside endpoints |
| MODIFY | `README.md` | Document layered gate and primitive pricing |

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| `vidbyte/` backend | `/api/x402/runtime/*` (`adversarial-team/admissions`) | Charges 25c and returns signed grant | CLI and backend DTOs must stay in sync |
| `RUNTIME_ADMISSION_SIGNING_KEY` verification path | Env via backend | Verifies grant_token offline | Public verification artifact must be reachable; missing key fails closed |
| Native hosts | `codex`, `claude`, `opencode` (user-installed) | Local execution after gate admits | Host CLI contract can vary by version |

No new pip dependency; uses `hashlib`, `hmac`, `base64`, `hmac.compare_digest` from stdlib.

---

## 11. Rollout & Deployment

- Release backend signing PR first; CLI verification has nothing to verify before the backend emits `grant_token`.
- Ship this CLI PR next: first wire the gate where the executor currently raises `RuntimeExecutionNotImplemented`, keep the raise after the gate for this increment if the full primitive loop is not yet implemented — the gate itself is still exercised.
- Verify locally with loopback backend: 402 when balance low, 200 with verifiable token when funded, tampered token rejected in under 10 ms, retry with same `Idempotency-Key` reuses admission, `--help` still has zero side effects.
- Roll back by reverting `executor.py` to the pre-gate signature and removing `gate.py` from the command path; no user data migrates.

---

## 12. Open Questions

- [x] Should the CLI sign x402 payments itself? No — top-up remains `POST /agent/topup`.
- [x] Should the gate ever trust model output? No — prompt injection is the exact threat.
- [ ] Should Layer 3 be on by default or opt-in per primitive? Default offline-only (Layer 1+2) for this release; Layer 3 is additive when backend adds the verify route.
- [ ] Should the gate cache successful verifications per `(admission_id, idempotency_key_hash)` to avoid re-checking within the 10-minute TTL, or re-verify on every harness entry?

---

## 13. Alternatives Considered

### Alternative 1: Pass grant JSON into the agent context and ask the model "is this paid?"

- What: Append the admission receipt to the main agent's transcript and instruct it to enforce payment.
- Why rejected: A model that can be prompt-injected can be instructed to ignore the receipt; a Python `if` before model start cannot.

### Alternative 2: Always query the backend before each harness entry

- What: Require `GET /api/x402/runtime/admissions/{id}` before every local step.
- Why rejected: It couples local execution to backend availability and doubles latency; offline signature verification already blocks forgery and the ledger remains the financial truth.

### Alternative 3: Rely only on HTTP 200 vs 402

- What: Run if the POST returned 200, regardless of grant shape.
- Why rejected: A 200 with a forged or replayed grant body (different `capability_id` or `charged_cents`) would still pass; Layer 1 exact field checks and Layer 2 signature prevent that class of silent failure.

### Alternative 4: Embed the whole `task` in the signed token and have the backend re-validate it

- What: Sign the user's task text alongside admission so the backend can check task == grant.task at execution time.
- Why rejected: It would require uploading secrets and full task text during admission, violates the local-only data boundary, and the gate's job is to prove payment, not to judge task content.

---

## 14. Testing Plan

### 14.1 Gate library

- [Silent Failure] Gate accepts a `grant` whose `capability_id` is a prefix of the plan's (`runtime.same-host`) — must require exact `==`.

- [Edge Case] Empty token string, missing dot, three segments, trailing dot, or non-base64url chars -> Layer 2 returns `signature_invalid`, never an exception with secret material.

- [Edge Case] Decoded payload >4 KiB — rejected before JSON parse.

- [Silent Failure] Token with `charged_cents=1` when plan expects 25 is treated as admitted — must be `price_mismatch`.

- [Hidden Failure] Swapped `admission_id` case or different `idempotency_key_hash` still verifies because comparison is case-insensitive — must use exact `hmac.compare_digest` on raw bytes.

- [Edge Case] `expires_at == now` is treated as admitted — must be strictly `expires_at > now`; `expires_at == now + 600` is admitted.

- [Hidden Assumption] Verification clock is the caller's system clock — violate by injecting a far-future `now` and assert token is correctly seen as expired without network.

- [Silent Failure] `extra` field in grant JSON is silently ignored — must be `extra="forbid"` and Layer 1 rejects unknown fields.

- [Hidden Assumption] Gate will always be called — violate by calling `executor.execute_adversarial_team(plan)` without a verdict and assert the executor fails closed.

### 14.2 Command wiring

- [Hidden Failure] `runtime adversarial-team` swallows a 402 and still constructs a plan that reaches the executor — assert 402 renders `CREDIT_EXHAUSTED` and executor is never called.

- [Edge Case] `--help` exits with 0 and does not construct a gate or call the network.

---

## Appendix: Skill Contract

- `skills/runtime-admission/SKILL.md` is normative for this repo: it names the three layers, the required parameters (`plan`, `grant`, `now`, `verification_key`, `allow_list`), and the two anti-patterns (model-based enforcement, unwrapped string grants).

