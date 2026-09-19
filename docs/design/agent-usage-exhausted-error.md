# Design Doc: Agent-Actionable Usage Exhaustion Errors

**Status:** Draft
**Author:** Codex
**Created:** 2026-09-17
**Last Updated:** 2026-09-17

---

## 1. Overview

The CLI will preserve the backend's structured API-balance exhaustion response and render a long, step-by-step recovery message for both humans and invoking agents. It will continue to return the stable `CREDIT_EXHAUSTED` error and exit status 5, but will add machine-readable remediation fields. A new `billing top-up` command will use the existing x402 signer to fund the user's Vidbyte API balance after explicit user approval, so the error points to an executable recovery path instead of an unexplained HTTP failure.

---

## 2. Goals & Non-Goals

### Goals

- Parse only the allowlisted backend `api_usage_exhausted` payload.
- Preserve detailed remediation in human stderr and JSON/JSONL error output.
- Keep `CREDIT_EXHAUSTED` and exit code 5 stable.
- Add `vidbyte-cli billing top-up` for the existing `/agent/topup` endpoint.
- Require explicit user approval before a paid top-up is attempted.
- Reuse the existing x402 payment implementation and API credential resolution.

### Non-Goals

- Automatically top up after a 402 response.
- Accept arbitrary backend error prose or expose backend response bodies verbatim.
- Add a new payment protocol or wallet implementation.
- Change harness execution, provider billing, or existing runtime admission commands.
- Store private keys, payment headers, or wallet addresses in CLI state.

---

## 3. Background & Context

- `ApiProblemMapper` currently classifies every 402 response as `ApiCreditExhausted` without reading the body.
- `CliError` already carries agent-native `description`, `trace`, `hint`, and request ID fields, and the output manager sends failures to stderr.
- `RuntimePayment` already validates and signs x402 v2 challenges for runtime admission.
- `ApiClient.post_runtime_payment` already performs bounded challenge/retry behavior and prevents a second authorization after one is created.
- The backend top-up route is `POST /agent/topup`; its current minimum is $5.00 and it uses the same API key for identity.

---

## 4. Requirements

### Functional Requirements

1. A recognized backend `api_usage_exhausted` response MUST become `ApiCreditExhausted` with exit status 5.
2. The CLI MUST preserve a long semantic instruction message explaining the full recovery sequence.
3. Human output MUST state that no agent started and no Vidbyte usage was charged for the admission rejection.
4. JSON and JSONL output MUST include a typed remediation object with endpoint, amount, payment methods, approval requirement, browser fallback, and retry behavior.
5. Malformed, oversized, or unknown error bodies MUST fall back to static safe CLI copy; arbitrary backend text MUST NOT be displayed.
6. `vidbyte-cli billing top-up` MUST authenticate with the configured Vidbyte API key and use a fresh idempotency key for the top-up operation.
7. The top-up command MUST use the existing x402 signer, default to Base mainnet, and never launch a harness or provider agent.
8. The top-up command MUST not automatically run as a side effect of handling a 402.
9. The top-up command MUST render the credited and available balance after success.

### Non-Functional Requirements

- Existing stdout-is-results-only and stderr-for-errors rules remain unchanged.
- The parsed backend error is bounded by strict Pydantic fields and lengths.
- No secret, payment header, task text, or backend diagnostic enters output or logs.
- Top-up retries reuse one idempotency key and never create a second authorization after an ambiguous payment attempt.
- The existing canonical `python scripts/run_ci.py` gate remains the verification authority.

---

## 5. High-Level Design

The HTTP problem mapper will decode a narrow backend error model only for HTTP 402. A recognized `api_usage_exhausted` response supplies safe remediation values to `ApiCreditExhausted`; the CLI class remains responsible for static semantic prose and the normal error envelope. Any decode failure uses the current fallback class, so a backend deployment can precede the CLI deployment without breaking callers.

The billing command will be a static Click group registered at the root. It will resolve the normal API client and a new endpoint method for `/agent/topup`, then use the existing `RuntimePayment` and `ApiClient.post_runtime_payment` path with a 500-cent requirement. It will not accept an arbitrary amount because the backend route's manifest owns the minimum and the client must validate the challenge it receives. The command will only be invoked explicitly; user approval is represented by the command invocation itself and any configured host-level confirmation policy.

```text
[HTTP 402 body]
        |
        v
[ApiProblemMapper -> strict problem model]
        |
        v
[ApiCreditExhausted -> stderr + JSON remediation + exit 5]

[billing top-up]
        |
        v
[API key -> POST /agent/topup -> x402 challenge/signature]
        |
        v
[credited balance result]
```

---

## 6. Detailed Design

### 6.1 Backend Error Problem Model

**File(s):** `src/vidbyte_cli/types/api.py`
**Type:** Modified

#### What it does

Defines strict, bounded types for the safe backend exhaustion payload and its remediation data.

#### Interface / API

```python
class ApiUsageRemediation(BaseModel): ...


class ApiUsageExhaustedProblem(BaseModel): ...
```

#### Logic / Algorithm

1. Require the exact stable code and safe field types.
2. Bound message, URL, command, and method strings.
3. Require the top-up path, minimum amount, supported methods, approval flag, and retry flag.
4. Ignore no unexpected fields; extra data invalidates the specialized parse.

#### Edge Cases & Error Handling

- Missing remediation or wrong code falls back to static CLI copy.
- Oversized strings fail validation before rendering.
- No raw backend body is stored on the model.

### 6.2 API Problem Mapping

**File(s):** `src/vidbyte_cli/lib/api/problem.py`, `src/vidbyte_cli/lib/errors/failures.py`
**Type:** Modified

#### What it does

Maps the safe problem model into the existing CLI failure vocabulary and carries remediation into output.

#### Interface / API

```python
class ApiCreditExhausted(CliError):
    def __init__(
        self, request_id: str | None = None, remediation: ApiUsageRemediation | None = None
    ) -> None: ...
```

#### Logic / Algorithm

1. Read the body only for status 402.
2. Validate it with `ApiUsageExhaustedProblem`.
3. Pass the typed remediation to `ApiCreditExhausted`.
4. Render long static instructions that describe approval, top-up, verification, and retry.
5. Use the existing fallback when validation fails.

#### Edge Cases & Error Handling

- The body may be empty, non-JSON, or a different 402 payment challenge.
- A direct x402 challenge is not classified as account exhaustion by this parser.
- Request ID remains available independently of the response body.

### 6.3 Error Output Remediation

**File(s):** `src/vidbyte_cli/lib/errors/cli_error.py`, `src/vidbyte_cli/lib/output/models.py`, `src/vidbyte_cli/lib/output/manager.py`
**Type:** Modified

#### What it does

Adds an optional JSON-safe remediation value to `CliError` and includes it in machine and human rendering without changing ordinary errors.

#### Interface / API

```python
CliError(..., remediation: Mapping[str, JsonValue] | None = None)
```

#### Logic / Algorithm

1. Store only validated primitive remediation data.
2. Add it to `OutputDocument.from_error` when present.
3. Render the full instructions through the existing human error fields.
4. Never render private causes or response bodies.

#### Edge Cases & Error Handling

- Existing errors have no remediation and keep their current output exactly.
- JSON serialization failure is treated as an internal software defect, as today.
- `--format none` still emits actionable errors to stderr.

### 6.4 Billing Top-Up Endpoint

**File(s):** `src/vidbyte_cli/lib/api/endpoints/billing.py`
**Type:** New file

#### What it does

Provides one explicit client operation that pays the existing $5 top-up challenge and returns the successful balance result.

#### Interface / API

```python
class BillingTopUpResult(BaseModel): ...


class BillingEndpoints:
    def top_up(self, key: str, payer: RuntimePayment) -> BillingTopUpResult: ...
```

#### Logic / Algorithm

1. Build a fresh idempotency key at the command boundary.
2. Send authenticated `POST /agent/topup` with the key.
3. On a valid x402 challenge, sign once through `RuntimePayment` at 500 cents.
4. Retry the identical request with the payment header.
5. Validate `credited_cents`, `available_balance_cents`, `rail`, and `payment_ref`.
6. Render the result without exposing payment credentials.

#### Edge Cases & Error Handling

- Missing signer configuration raises the existing typed CLI error before any request is paid.
- A malformed challenge is rejected by `RuntimePayment`.
- A timeout after signing never signs again; the same idempotency key can be used for recovery.
- A non-402 failure uses the existing API problem mapper.

### 6.5 Billing Command

**File(s):** `src/vidbyte_cli/commands/billing/__init__.py`, `src/vidbyte_cli/commands/billing/top_up.py`, `src/vidbyte_cli/commands/__init__.py`
**Type:** New files / Modified

#### What it does

Registers `billing top-up` as an explicit, user-invoked command.

#### Interface / API

```text
vidbyte-cli billing top-up
```

#### Logic / Algorithm

1. Resolve API credentials and configuration lazily.
2. Validate x402 environment configuration before network payment.
3. Create the payment signer and fresh top-up idempotency key.
4. Call the billing endpoint.
5. Render a structured result with credited and available cents.

#### Edge Cases & Error Handling

- No API key produces the existing authentication error.
- No private key produces a new typed repair message naming the required environment variable.
- The command never runs from error handling automatically.

### 6.6 CLI Tests and Verification Script

**File(s):** `scripts/test-agent-usage-error.py`, `scripts/test_research_only_surface.py`
**Type:** New file / Modified

#### What it does

Verifies error propagation, safe fallback, long instructions, top-up payment flow, and command registration using fake HTTP responses.

#### Interface / API

Tests import the implementation directly and never send real money.

#### Logic / Algorithm

1. Feed valid, malformed, oversized, and unrelated 402 responses to the mapper.
2. Assert human and JSON output contains all recovery steps.
3. Exercise the top-up command against a fake x402 challenge and successful balance response.
4. Assert one signing attempt and stable idempotency across retries.
5. Run the script through every listed category before the canonical CI gate.

#### Edge Cases & Error Handling

- Empty and non-JSON bodies use the safe fallback.
- Payment challenge rejection never launches a local agent.
- Secrets are absent from stdout, stderr, and serialized output.

---

## 7. Data Model Changes

### 7.1 CLI error remediation

**Change type:** Modified

```json
{
  "action": "top_up_api_balance",
  "requires_user_approval": true,
  "topup_path": "/agent/topup",
  "minimum_topup_cents": 500,
  "supported_payment_methods": ["x402", "mpp"],
  "cli_command": "vidbyte-cli billing top-up",
  "browser_url": "https://vidbyte.pro/settings/api",
  "retry_original_operation": true
}
```

**Migration strategy:** No persisted migration. The output schema is additive and remains backward-compatible for consumers that only inspect `code` and `exit_code`.

---

## 8. API Changes

### 8.1 `POST /agent/topup`

**Change type:** Existing endpoint consumed by a new CLI operation.

**Request:** Authenticated API key, fresh `Idempotency-Key`, and no body required by the route.

**Response:** Existing top-up success response with credited and available balance.

**Error cases:**

| Status | Condition |
|--------|-----------|
| 401 | API key is missing or invalid. |
| 402 | Payment challenge is missing, invalid, or unsettled. |
| 503 | Payment settled but balance credit cannot be confirmed. |

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| MODIFY | `src/vidbyte_cli/types/api.py` | Strict backend exhaustion/remediation models. |
| MODIFY | `src/vidbyte_cli/lib/api/problem.py` | Parse the allowlisted 402 payload. |
| MODIFY | `src/vidbyte_cli/lib/errors/cli_error.py` | Carry safe remediation data. |
| MODIFY | `src/vidbyte_cli/lib/errors/failures.py` | Long recovery prose and typed top-up failures. |
| MODIFY | `src/vidbyte_cli/lib/output/models.py` | Serialize remediation for agents. |
| CREATE | `src/vidbyte_cli/lib/api/endpoints/billing.py` | Typed top-up API operation. |
| CREATE | `src/vidbyte_cli/commands/billing/__init__.py` | Billing command group. |
| CREATE | `src/vidbyte_cli/commands/billing/top_up.py` | Explicit top-up command. |
| MODIFY | `src/vidbyte_cli/commands/__init__.py` | Register billing group. |
| CREATE | `scripts/test-agent-usage-error.py` | Executable feature verification. |
| MODIFY | `scripts/test_research_only_surface.py` | Keep the static command-surface contract in sync with billing. |
| MODIFY | `scripts/run_ci.py` | Run the feature verification in the canonical repository gate. |
| CREATE | `docs/design/agent-usage-exhausted-error.md` | Record the CLI design and contract. |

---

## 10. Testing Plan

### Unit Tests

- `ApiProblemMapper` -> `[Edge Case]` valid exhaustion payload maps to `CREDIT_EXHAUSTED` with exit 5.
- `ApiProblemMapper` -> `[Hidden Failure]` empty, non-JSON, oversized, and wrong-code bodies use safe fallback.
- `ApiCreditExhausted` -> `[Silent Failure]` human copy contains every top-up and retry step.
- `OutputDocument.from_error` -> `[Hidden Assumption]` remediation appears only for this error and never serializes `cause`.
- `BillingEndpoints.top_up` -> `[Edge Case]` successful credit response validates all fields.
- `BillingEndpoints.top_up` -> `[Hidden Failure]` a second 402 after signing raises without a second authorization.

### Integration Tests

- API client -> `[Hidden Assumption]` the same API key and idempotency key survive the unpaid and paid top-up attempts.
- Billing command -> `[Silent Failure]` success renders credited and available cents and no secret.
- Billing command -> `[Hidden Failure]` signer or challenge errors stop before any local agent starts.
- Root registration -> `[Edge Case]` `billing top-up --help` works without opening credentials or a network connection.

### Manual / QA Test Cases

1. `[Edge Case]` Invoke a harness with an empty API balance and confirm the detailed error appears on stderr with exit 5.
2. `[Hidden Failure]` Run with `--json` and confirm stdout remains empty while stderr contains one structured error record.
3. `[Silent Failure]` Read the error as a fresh agent and verify it names approval, environment, command, endpoint, payment, success verification, and retry.
4. `[Hidden Assumption]` Run `billing top-up` with a fake challenge and confirm exactly one authorization is created.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Existing x402 Python SDK | Current `pyproject.toml` dependency | Signs exact payment challenge. | SDK shape changes could break challenge validation. |
| Vidbyte API | `POST /agent/topup` | Credits the API wallet. | Payment or response contract changes require synchronized updates. |
| Vidbyte API settings | `https://vidbyte.pro/settings/api` | Browser fallback. | Product URL must remain valid. |

---

## 12. Rollout & Deployment

- Deploy backend contract support first; old CLIs continue to use their fallback 402 error.
- Deploy CLI parsing and the top-up command second.
- No feature flag or persisted migration is required.
- Roll back by reverting the CLI command/parser and backend payload additions independently; the HTTP 402 and exit 5 contract remain safe.

---

## 13. Open Questions

- [ ] Should `billing top-up` support MPP in the first implementation, or only x402 because the CLI already has an x402 signer?
- [ ] Should the command require an explicit `--confirm` flag in addition to explicit invocation for financial safety?

---

## 14. Alternatives Considered

### Alternative 1: Keep all recovery instructions as static CLI prose

- What: Do not parse backend remediation and only edit `ApiCreditExhausted`.
- Why rejected: Direct API agents would still receive incomplete guidance, and the CLI could not reflect the backend’s route or amount contract safely.

### Alternative 2: Display arbitrary backend error bodies

- What: Forward the 402 JSON or text body verbatim.
- Why rejected: It can contain secrets, prompt text, account data, or unstable internal details. The parser must be strict and allowlisted.

### Alternative 3: Automatically top up when a harness receives 402

- What: The error handler immediately pays the top-up challenge and retries.
- Why rejected: It creates an unapproved financial side effect and makes an error path perform an irreversible operation.
