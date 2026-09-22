# Suggestion agent: priced admission

## What and why

`agents suggest run` is a product with no price: it runs read-only Codex agents on the caller's
machine and never talks to Vidbyte. The owner set its price at **2 cents per 10 suggestions,
whatever the categories.** This change buys one admission before every model-backed run, the
same way `runtime stages` and `runtime task-board` do. The backend half is
`runtime.suggestion@1` in the vidbyte repo (companion PR), which accepts a `units` quantity on the
admission.

## How it works

- **Quantity.** `units = ceil(--count / 10)`. `--count` is 2 to 15, so a run buys 1 unit (2
  cents) for up to 10 suggestions and 2 units (4 cents) for 11 to 15. Categories, `--extra-compute`,
  and `--rounds` do not change the fee, only the caller's own model usage.
- **One purchase per invocation.** The request carries `units` on a single idempotency-keyed
  admission (`RuntimeSuggestionAdmissionRequest`, a subclass like `RuntimeX402AdmissionRequest`,
  so every other runtime keeps its two-field wire shape).
- **Order in `SuggestRunCommand.execute`:** validate the request, then (for a real run only)
  resolve the key, load the SDK, and plan the Codex host. Only then admit, verify the grant
  online, and run the service with the SDK that was already loaded. Everything a caller can get
  wrong fails before the wallet is touched.
- **Free paths stay free.** `--dry-run`, `categories`, `handoff`, `project`, and `feedback` never
  admit and need no Vidbyte login.
- **Gate.** `RuntimeAdmissionGate` treats the allowed price as a per-unit price:
  `verify_online(plan, grant, verified, units=...)` expects `2 * units` cents for
  `runtime.suggestion@1` and still `1 x` for every other capability.
- **Receipt in the result.** `SuggestionResult.admission` records `admission_id`,
  `charged_cents`, and `units`, and the human output prints the charge line. It is `None` for a
  dry run and for results saved before this change, so `handoff` still reads old files.
- **`--idempotency-key`** recovers an admission whose response was lost. It gets a full Markdown
  help asset, which lint rule C005 requires.

## Files

- `src/vidbyte_cli/commands/agents/suggestion/suggest.py`, `render.py`, `prompts/idempotency_key.md` (new)
- `src/vidbyte_cli/lib/api/endpoints/runtime.py`, `lib/runtime_primitives/gate.py`, `lib/runtime_primitives/planner.py`, `lib/constants/runtime.py`
- `src/vidbyte_cli/types/runtime.py`, `src/vidbyte_cli/types/suggestions.py`
- `scripts/test-suggestion-admission.py` (new), `scripts/run_ci.py`, `README.md`

## Risks and open questions

- **Deploy order.** The backend route must be live first. Against an older backend the
  admission returns 404 and the run stops before any model call, so nothing is charged and nothing
  runs.
- **Behavior change.** A real run now needs `vidbyte-cli login` and balance. Offline callers can
  still use `--dry-run` and every non-run subcommand.
- The provider key is not pre-checked before payment, because the suggestion service leaves
  credentials to Codex. A missing OpenAI key therefore fails after admission, the same as a
  provider outage. This is the existing runtime refund question, and it is not solved here.

## Verification

- `python scripts/test-suggestion-admission.py`: the units math, the per-unit gate price, a dry
  run that never admits, one admission with the right units before the service runs, an SDK
  failure that never admits, and the receipt in the result.
- `python lint/run.py`, then `python scripts/run_ci.py` (the full gate).
