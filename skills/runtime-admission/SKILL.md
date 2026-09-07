# Skill: Runtime Admission

## Purpose
Enforce paid local runtime admission in deterministic Python before any model turn.

## When to load
Read when changing runtime commands, receipts, verification or local execution.

## Execution contract
Persistence buys one receipt through POST /api/x402/runtime/persistence/activate, then calls
POST /api/x402/runtime/grants/verify with the same authenticated API key, opaque grant_token,
and SHA256 idempotency_key_hash. The backend keeps the HMAC signing secret and checks
signature, owner, request binding, catalog price and bounded lifetime. Never distribute that
secret to ordinary CLI installations.

RuntimeAdmissionGate.verify_online(plan, grant, verified) compares the verified canonical
receipt against the original. It enforces exact capability and price, local execution,
nonempty receipt ID and token, and admitted_at <= now < expires_at with at most one hour of
lifetime. RuntimeExecutor requires its successful matching verdict before launching Codex.
Failed API calls and negative verdicts stop execution.

Offline verify(plan, grant, now, key) is for trusted integrations and diagnostics. It fails
closed without a key and compares all signed public fields. It does not replace server-side
ownership verification in the shipped CLI path.

## Adding a primitive
Register its canonical capability and price, mount the backend handler and route policy,
expose typed admission and verification, then require the verdict at execution. Task text
and provider credentials stay local. Tokens and raw idempotency keys never enter prompts.

## Verification
Run python scripts/run_ci.py. The existing admission script covers tampering, missing keys,
receipt substitution, expiry, denial-before-execution and fixed same-session turn counts.
Provider login checks also run in the canonical gate.
