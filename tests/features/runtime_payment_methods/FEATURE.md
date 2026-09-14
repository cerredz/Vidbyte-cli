# Runtime payment methods

## Intent and contract
Runtime admission defaults to ordinary API-wallet usage. Explicit x402 pays the same
fee once; both modes require an API-key owner and database-verified admission before
local execution. The CLI never connects directly to Mongo or forwards payment secrets.

## Failure inventory
Missing payment evidence, mismatched owner/amount, invalid challenge, duplicate charge,
expired grant, altered request identity, settlement ambiguity and leaked credentials.

## Test suite map
`scripts/test-runtime-payment-methods.py` directly exercises implemented classes with
isolated external boundaries. It prints labeled outcomes and a final count. Existing
runtime admission and gatekeeper contracts protect adjacent behavior.

## Omitted strategies
No browser/UI tests: this is an HTTP and CLI feature. No live-money facilitator tests
or production Mongo writes: operator sandbox verification follows deployment. Receipt
expiry is launch admission, not a remotely enforceable single-use local execution license.
