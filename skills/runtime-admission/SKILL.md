# Skill: Runtime Admission

## Purpose

Teach contributors how to deterministically enforce that a user has paid for a local runtime primitive, without trusting model output or a context window.

## When to load

Load when you touch `lib/runtime_primitives/`, `types/runtime.py`, `commands/runtime/`, any harness that will run a local agent, or any code that handles `grant_token` or `admission_id`.

## Three-layer gate

The gate lives in `src/vidbyte_cli/lib/runtime_primitives/gate.py` and every harness must call it.

1. **Layer 1 — typed grant.** The grant must be a `RuntimeAdmissionGrant(extra="forbid", frozen=True)` with exact `capability_id == plan.capability_id`, exact `charged_cents` match to the local allow-list (2c for `same-host-ensemble`, 25c for `adversarial-team`), `execution_location=="local"`, and `admitted_at` timezone-aware and before `now`. Prefix matches fail: `runtime.same-host` does not equal `runtime.same-host-ensemble@1`.

2. **Layer 2 — signature and expiry.** The grant's `grant_token` is `base64url(canonical_json).base64url(hmac_sha256(signing_key, canonical_json))`. The gate splits on a single `.`, base64url decodes with `validate=True`, rejects >4 KiB before JSON, recomputes HMAC with `hmac.compare_digest`, and checks `expires_at > now` and `expires_at > admitted_at`. A missing or whitespace key means the local HMAC check is skipped — Layer 1 still gates — but a present key must verify.

3. **Layer 3 — optional online.** When `verify_online=True`, the gate re-fetches `GET /api/x402/runtime/admissions/{id}/verify` with the same API key. Whether Layer 3 is on or off, Layer 1 or 2 failure still fails closed. Online is additive, not a substitute.

## Required parameters

`plan: RuntimeLaunchPlan`, `grant: RuntimeAdmissionGrant | None`, `now: datetime` (injected for testability), `verification_key: str | None`, `allow_list: tuple[str,...] | None`. The executor must be called as `executor.execute_adversarial_team(plan, verdict)` — a verdict, not a raw dict or model string.

## Wiring a new harness

```python
plan = RuntimeLaunchPlanner(registry).build(task, host, cwd)
grant = RuntimeEndpoints(client).admit_adversarial_team(request, idempotency_key)
verdict = RuntimeAdmissionGate().verify(plan, grant, now=datetime.now(timezone.utc), verification_key=key, allow_list=("runtime.my-new-primitive@1",))
if not verdict.admitted:
    raise RuntimeAdmissionNotVerified(verdict.reason)
RuntimeExecutor().execute_my_harness(plan, verdict)
```

## Failure codes

`grant_missing` `grant_capability_mismatch` `grant_price_mismatch` `grant_location_invalid` `grant_token_missing` `grant_expired` `grant_signature_invalid` `online_verification_failed`. None include token or key material.

## Anti-patterns

Do not pass `json.dumps(grant)` into a prompt and ask the model "did the user pay?". Do not call the executor without a verdict. Do not accept `grant` as a plain dict — the type system is the first gate.

## Verification

Tampered token, wrong key, expired `expires_at`, extra `.` segment, or changed `charged_cents` must be rejected in <10 ms offline without network. The same `(capability, user, api_key, Idempotency-Key)` must hash to the same `admission_id` deterministically.
