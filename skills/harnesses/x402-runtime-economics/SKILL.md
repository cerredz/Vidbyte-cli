---
name: x402-runtime-economics
description: How Vidbyte prices and admits locally-executed runtime primitives through the x402 catalog — what the backend is allowed to know, why the fee is flat rather than metered, and how a CLI capability and its catalog entry must agree. Read before adding a priced capability or changing an admission call.
---

# x402 Runtime Economics

x402 is Vidbyte's capability catalog: one immutable, versioned declaration per sellable product,
which the gatekeeper turns into a route rule with a price. Runtime primitives are a category
inside it, and they price differently from everything else Vidbyte sells.

## The economics of a local primitive

Every other Vidbyte product runs on Vidbyte's own compute, so its cost scales with usage and its
price is metered. A runtime primitive runs on the caller's machine, against the caller's own
Codex subscription. Vidbyte spends nothing on inference and nothing on execution.

So the fee is **flat and small** — `PREPAID_WALLET_FLAT`, two cents per activation for
`runtime.same-host-ensemble@1`. It buys the orchestration, not the compute. The catalog entry
says this in its own description, and that wording is the contract we are held to:

> The activation costs a flat, non-metered two-cent fee per invocation because all model and
> provider usage runs locally under the caller's own Codex credentials rather than accruing
> backend usage.

**What follows for pricing:** do not meter a local primitive. `admission_floor_cents` with
`metered=False` is the right shape. If you find yourself wanting a per-token price for something
that runs on the user's machine, you are billing for tokens you did not pay for.

**What follows for honesty:** the two cents is not the run's real cost to the user. A three-role
ensemble is nine Codex app-server startups against their subscription. Say so in the CLI docs.
A user who thinks a two-cent command costs two cents has been misled by omission.

## What the backend is allowed to know

Admission carries exactly two fields:

```json
{ "client_runtime_version": "1", "host": "codex" }
```

No task text. No prompts. No file paths. No proposal bodies. No result. The catalog entry commits
to this explicitly — "Vidbyte's backend does not execute, review, or persist the intermediate
proposal agents or their draft output; it only admits the run under the caller's API key and
licenses the local invocation."

**Rule:** if a change would send execution content across the admission boundary, it is a
different product, not an extension of this one. Stop and reconsider.

## Catalog and client must agree, and the catalog wins

The capability declaration in `backend/lib/x402/catalog.py` owns the route path, the method, the
permission, and the price. The CLI is a consumer of that declaration.

This has already gone wrong once. `vidbyte-cli` PR #25 scaffolded the admission call against
`/api/x402/runtime/same-host-ensemble/admissions`, while the backend catalog entry (`vidbyte`
PR #508) declared `/api/x402/runtime/same-host-ensemble/activate`. Two unmerged PRs in two
repositories, each internally consistent, disagreeing with each other. The implementation PR
aligned the CLI to the catalog, because the catalog is the authority.

**Check before writing any admission call:**

```bash
grep -n "<capability-id>" backend/lib/x402/catalog.py
```

Read the `path`, `method`, `permission`, and `admission_floor_cents` off the declaration. Do not
infer a path from a sibling capability's naming, and do not assume a design doc's proposed path
survived review.

## Declaring a capability before its route exists

A catalog entry can legally precede its mounted route. `ROUTE_TABLE.validate_against_app` would
normally reject a declaration with no matching route, and `_X402_MOUNTED_CATEGORY_PREFIXES` is
the filter that lets the `runtime` category be declared ahead of its endpoints.

**What follows:** do not remove that filter while adding runtime capabilities whose routes are
not mounted. And do not read a catalog entry as proof the endpoint is live — check for the route
itself.

**What follows for the CLI:** a capability whose route is not yet mounted returns 404. That is a
normal API failure and the existing problem-mapping layer renders it. It is *not* a reason for the
command to answer "not implemented" — the CLI's own rule is that a command's surface never says
that, and an honest upstream 404 is a different thing from a stubbed command.

## Where admission sits in the sequence

```
input validation -> SDK availability -> host discovery -> ADMISSION -> execution
```

Everything before admission is free and local. This ordering is the whole cost-safety story: a
user with no Codex on PATH, or an SDK too old to have the integration, is never charged.

**Rule:** one idempotency-keyed purchase per invocation. `IdempotencyKey.create(None)` generates
a fresh UUID; the backend collapses duplicates so a retried HTTP request cannot double-charge.

**Rule:** report `charged_cents` from the grant in the result document. The caller should see
what a run cost without consulting the backend.

**Open question this project has not settled:** who absorbs the fee when admission succeeds and
execution then fails. Today the caller pays and the result reports it. A refund or
replay-on-failure policy is a backend decision, and it is tracked as an open question in
`docs/design/same-host-ensemble-implementation.md`.

## Related

- `skills/harnesses/runtime-primitives/SKILL.md` — the shape every primitive shares.
- `skills/harnesses/codex-harness-sdk/SKILL.md` — driving the agent that the admission licenses.
- `backend/lib/x402/catalog.py` — the authority for every capability's path and price.
