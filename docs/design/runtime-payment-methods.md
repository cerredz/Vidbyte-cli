# Design Doc: Runtime Payment Methods

**Status:** Implementation ready
**Author:** Codex
**Created:** 2026-09-07
**Last Updated:** 2026-09-07

## 1. Overview
Runtime admission defaults to the authenticated user's existing API usage wallet. An explicit --with-x402-payment option pays the same flat fee through x402 instead. The CLI asks the authenticated backend to verify both the signature and durable database payment evidence before launching Codex.

## 2. Goals & Non-Goals
### Goals
- One admission fee through exactly one selected method; wallet is default.
- Use ApiBillingCoordinator.record_usage for wallet debits.
- Implement a working x402 buyer exchange and durable backend verification.
- Preserve local prerequisites, task privacy, idempotency, safe recovery and the existing grant response shape.
### Non-Goals
- Accountless payments: both methods keep the Vidbyte key as identity.
- Model-token proxying, new runtime executors, changed prices, DRM or single-use grant consumption.
- Automatic fallback, double charging, frontend billing UI or live-money test transactions.

## 3. Background & Context
The existing CLI persistence command prepares a local Codex SDK session, admits through /api/x402/runtime/persistence/activate, verifies a signed HMAC receipt online, then launches. Runtime catalog entries currently require API keys and wallet coverage despite their x402 namespace. The gatekeeper leases wallets, claims request idempotency, records settlement crash barriers and response replay. The admission service unconditionally records usage and verification only checks signed claims. Prices remain catalog-owned: persistence and ensemble two cents; adversarial team twenty-five cents. Main was updated after audit to retain local lifecycle and supported-host metadata. Existing nested worktrees were skipped by the user-authorized stash and remain untouched.

## 4. Requirements
### Functional Requirements
1. Omitted with_x402_payment means false. CLI --with-x402-payment sends true only when selected.
2. Both modes authenticate the Vidbyte key and runtime:write scope; invalid keys never downgrade.
3. Wallet mode uses the existing normal usage debit; x402 mode bypasses wallet coverage/debit and settles only x402.
4. Validate body, supported host and signing configuration before financial effects.
5. Payment choice participates in the request fingerprint and cannot change during recovery.
6. Persist a deterministic admission with owner, key, host, payment method, amount, timestamps and settlement reference. Retries recover its original receipt without extending expiry.
7. Verification queries Mongo through the backend query layer. A wallet grant also requires its matching owner/key/amount/route usage debit; x402 requires the durable settled admission evidence. Missing/mismatched evidence fails closed.
8. CLI runs identical local admission checks for either payment method and never launches on failed online verification.
9. x402 signing uses an explicitly configured environment credential and bounded exact-payment requirements. Never sign a second authorization automatically after a failed payment response.
10. Preserve existing response DTOs and older wallet requests; expose method policy through catalog payment mode and documentation.
### Non-Functional Requirements
- Point queries use unique admission ID and ledger entry indexes; no scans or unbounded embedded history.
- No payment secrets, tasks, repository data or provider keys in admission records, tokens or diagnostics.
- Preserve durable SETTLING/SETTLED/EXECUTING barriers. Ambiguous settlement pauses automatic repayment.
- Local execution remains BYOK; no production Mongo writes or real payments during verification.

## 5. High-Level Design
The gatekeeper validates a catalog-declared runtime payment choice after key authorization. It carries the selection as trusted request identity metadata. Wallet requests retain the existing flow. Opt-in requests build a genuine x402 challenge and settle through the configured x402 rail while preserving the key principal.

The admission service reads its durable record first, then either writes ordinary usage or accepts trusted gatekeeper settlement evidence. It stores immutable admission data in a dedicated collection because x402 cannot be represented as a wallet debit. The verification route is asynchronous and reads that record; wallet verification additionally checks the existing usage ledger. Grants keep their current public shape.

The CLI loads an EVM signer only for explicit opt-in, performs an unpaid probe, validates a standard v2 exact challenge, signs once, and retries the same HTTP operation. The existing online verifier and executor remain the launch boundary.

## 6. Detailed Design
### 6.1 Backend policy and payment
Files: backend/lib/runtime/payment_policy.py, backend/lib/dataclasses/middleware.py, backend/lib/x402/catalog.py, backend/middleware/gatekeeper.py, backend/lib/usage/rails/x402_rail.py.
Modified/new as listed in the manifest. Add a declared runtime payment-choice route field and identity choice flag. Strictly parse RuntimeAdmissionRequestDto before claiming/charging. The x402 branch selects only the configured x402 rail and generates its standard PAYMENT-REQUIRED header using the installed SDK's server adapter. Return 503 if unavailable. Supply trusted settlement on request state. Keep key identity after account-linked settlement. Validate an exact positive amount and nonempty transaction/payer before issuing admission; retain ambiguous outcomes for reconciliation.
### 6.2 Admission storage and verification
Files: backend/database/queries/runtime_admissions.py, backend/lib/enums/runtime.py, backend/database/indexes/billing.py, backend/lib/dtos/runtime_primitives.py, backend/services/runtime_primitives/admission.py, backend/lib/api/dependencies.py, backend/routes/x402_runtime.py, backend/lib/errors/runtime_primitives.py.
Repository returns typed projections; collection/index names are enums. Atomic set-on-insert by admission ID returns the persisted canonical document. A partial unique settlement-reference index prevents a transaction funding multiple admissions. Wallet evidence query filters ledger entry ID, user, key, capability route, debit direction, usage type and exact cents. Request verification binds owner and idempotency hash before database reads and compares persisted receipt fields. Database outages return safe 503; absent evidence is invalid admission. Default wallet debit uses record_usage with the existing deterministic entry ID. Expired purchases never mint refreshed grants. No direct Mongo access from CLI.
### 6.3 CLI transport and gate
Files: src/vidbyte_cli/lib/api/runtime_payment.py, src/vidbyte_cli/lib/api/client.py, src/vidbyte_cli/lib/api/endpoints/runtime.py, src/vidbyte_cli/types/runtime.py, src/vidbyte_cli/commands/runtime/persistence.py, src/vidbyte_cli/lib/runtime_primitives/gate.py, src/vidbyte_cli/lib/constants/runtime.py, src/vidbyte_cli/lib/errors/failures.py.
Add --with-x402-payment. Use VIDBYTE_X402_PRIVATE_KEY for the opt-in signer and VIDBYTE_X402_NETWORK (default Base eip155:8453) for an explicit allowed network. Register the installed x402 EVM exact client. Read PAYMENT-REQUIRED; require v2, matching resource path/origin, exact fee, configured network and canonical USDC asset; sign one accepted requirement and reuse its headers across bounded network retries. Keep nonpayment methods on existing transport. Add a typed safe payment failure and preserve stdout contracts. Clear payment credentials from child env. Document that a Vidbyte key is still required and local model usage remains separate.
### 6.4 Documentation and verification
Files listed in Section 9. Update discovery descriptions, runtime skill reference and README. Add feature contracts and executable scripts. Integrate the CLI script into canonical CI. Script cases directly import implemented modules and use fake databases/facilitators or loopback transport; no real financial side effects.

## 7. Data Model Changes
### 7.1 Runtime admissions
New collection runtime_admissions: admission_id, user_id, api_key_id, host, with_x402_payment, idempotency_key_hash, receipt (existing response DTO), settlement (x402 reference/rail/payer/amount only).
Unique admission_id plus partial unique settlement.payment_ref for settled x402 records; immutable records have no TTL. Existing api_billing_ledger entry_id index serves wallet proof checks.
Migration: create indexes before enabling writes, no backfill fabricated from signatures. Previously issued grants without durable admission records fail closed after deployment; their ten-minute TTL bounds impact. Deploy after existing grant TTL or communicate retry policy. Rollback code retains records and indexes; never delete billing evidence.

## 8. API Changes
### 8.1 POST /api/x402/runtime/* admission routes
Modified request: {"host":"codex","client_runtime_version":"1","with_x402_payment":false}. Omitted boolean preserves wallet behavior. x402 true initiates a standard challenge then accepts PAYMENT-SIGNATURE. Idempotency-Key and x-api-key remain required. Response remains RuntimeAdmissionReceiptDto unchanged.
### 8.2 POST /api/x402/runtime/grants/verify
Same request and response shapes; now signature plus database payment evidence verification, no additional monetary charge.
| Status | Condition |
|---|---|
| 401/403 | Invalid identity, scope or grant/evidence |
| 402 | Wallet insufficient or x402 challenge/rejection |
| 409 | Conflicting request or ambiguous/in-progress recovery |
| 422 | Invalid request or unsupported host |
| 503 | Database, signing or payment infrastructure unavailable |

## 9. File Change Manifest
This document's repository is vidbyte-cli. The counterpart design carries its own manifest. Amend this manifest before implementing any additional file.
| Action | File Path | Reason |
|---|---|---|
| CREATE | `docs/design/runtime-payment-methods.md` | Runtime payment policy, durable verification, client integration or executable contract. |
| CREATE | `src/vidbyte_cli/lib/api/runtime_payment.py` | Runtime payment policy, durable verification, client integration or executable contract. |
| CREATE | `scripts/test-runtime-payment-methods.py` | Runtime payment policy, durable verification, client integration or executable contract. |
| CREATE | `tests/features/runtime_payment_methods/FEATURE.md` | Runtime payment policy, durable verification, client integration or executable contract. |
| MODIFY | `src/vidbyte_cli/types/runtime.py` | Runtime payment policy, durable verification, client integration or executable contract. |
| MODIFY | `src/vidbyte_cli/lib/api/client.py` | Runtime payment policy, durable verification, client integration or executable contract. |
| MODIFY | `src/vidbyte_cli/lib/api/endpoints/runtime.py` | Runtime payment policy, durable verification, client integration or executable contract. |
| MODIFY | `src/vidbyte_cli/commands/runtime/persistence.py` | Runtime payment policy, durable verification, client integration or executable contract. |
| MODIFY | `src/vidbyte_cli/lib/runtime_primitives/gate.py` | Runtime payment policy, durable verification, client integration or executable contract. |
| MODIFY | `src/vidbyte_cli/lib/constants/runtime.py` | Runtime payment policy, durable verification, client integration or executable contract. |
| MODIFY | `src/vidbyte_cli/lib/errors/failures.py` | Runtime payment policy, durable verification, client integration or executable contract. |
| MODIFY | `pyproject.toml` | Runtime payment policy, durable verification, client integration or executable contract. |
| MODIFY | `scripts/run_ci.py` | Runtime payment policy, durable verification, client integration or executable contract. |
| MODIFY | `README.md` | Runtime payment policy, durable verification, client integration or executable contract. |
| MODIFY | `.env.example` | Runtime payment policy, durable verification, client integration or executable contract. |
| MODIFY | `skills/runtime_primitives/references/runtime-primitives.md` | Runtime payment policy, durable verification, client integration or executable contract. |

## 10. Testing Plan
### Unit Tests
- [Edge Case] Default/false/true request choices, malformed booleans, unsupported hosts, missing/zero/incorrect payment amounts.
- [Hidden Assumption] Missing/revoked key or wrong scope is denied before payment; x402 requires an explicit opt-in.
- [Silent Failure] Wallet records one normal usage debit, x402 records zero wallet debits, each returns correct capability and cents.
- [Hidden Failure] Missing database evidence and database outages deny verification without launch.
- [Silent Failure] Signed token with wrong owner/key/route/amount/record fields cannot pass database verification.
- [Hidden Failure] Duplicate purchase recovers identical timestamps and grant; changing method/host with the same identity conflicts.
- [Hidden Assumption] x402 settled=True without exact amount, payer or transaction is not usable payment evidence.
- [Edge Case] Expired grants and local price mismatch never launch or refresh payment.
### Integration Tests
- [Hidden Failure] Key-authenticated x402 bypasses wallet checks, preserves identity, and retries settled claims without settling twice.
- [Silent Failure] CLI default sends no payment signature; opt-in probes, signs once, submits unchanged body/idempotency and verifies before execution.
- [Hidden Assumption] Nonstandard/oversized/wrong-network/wrong-asset/wrong-resource/overpriced challenges fail before signing.
- [Hidden Failure] 401, 403, timeout, repeated 402 and ambiguous settlement do not cause fallback, repeated authorization or local launch.
- [Hidden Assumption] Payment secrets never reach native child environment or safe errors.
### Manual / QA Test Cases
- [Edge Case] Help shows --with-x402-payment and default invocation requires no x402 credential (automated CLI contract).
- [Silent Failure] Feature scripts print PASS/FAIL per case and total; canonical CLI gate and both backend lint surfaces pass.
- [Hidden Failure] Real facilitator/on-chain integration is operator sandbox verification after deployment; intentionally no live payment during implementation. Real Mongo durability uses existing transaction mechanisms; index/schema checks are automated against a faithful fake collection, with deployment index creation required.

## 11. Dependencies & External Services
| Dependency | Version / Endpoint | Purpose | Risk |
|---|---|---|---|
| x402 Python SDK | 2.8.0 locally inspected; CLI pinned 2.8.0 EVM extra | Standard buyer signing and server challenge | SDK protocol shapes and facilitator availability |
| Existing MongoDB | Existing configured database | Usage ledger and immutable admissions | Partial write/recovery and index rollout |
| Existing x402 facilitator | Existing server configuration | Verify/settle exact payment | Ambiguous outcomes require reconciliation |
| Existing Vidbyte SDK | CLI's current pinned revision | Local Codex persistence | No SDK change |
Official reference: https://docs.x402.org/getting-started/quickstart-for-buyers. Implementation interfaces are checked against installed source.

## 12. Rollout & Deployment
Backend/indexes first, CLI second. Omitted request boolean stays wallet; grant response fields stay unchanged. x402 requires configured ready rail and explicit CLI flag. Keep the current signing key. Wait one grant TTL before switching strict verification if old grants exist. Roll back CLI opt-in then backend code; keep immutable evidence. Never reinterpret uncertain settlement as permission to charge again.

## 13. Open Questions
- Accountless x402 is intentionally outside this change; the existing key ownership contract is retained.
- No automatic local-start refund or grant renewal; retry recovers original admission, and expiry requires a deliberate new invocation/key.
- Real facilitator credentials and production index deployment remain operator responsibilities; implementation uses no live money.

## 14. Alternatives Considered
### Alternative 1: Change route access only
Rejected: handler still needs API-key ownership and would debit wallet after x402 settlement.
### Alternative 2: Direct Mongo access from CLI
Rejected: database credentials must remain server-side; authenticated verification is the existing boundary.
### Alternative 3: Represent x402 as a wallet top-up and debit
Rejected: the user requested a direct alternative and ordinary usage debit only for API-key payment; top-up would create misleading wallet activity.
### Alternative 4: New grant format and single-use consumption
Deferred: the existing signed receipt can be compared with durable evidence without breaking clients or introducing launch-acknowledgment semantics.
