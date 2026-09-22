**Idempotency Key**
Idempotency Key is the replay key for the one Vidbyte admission that a model-backed suggestion run buys before any model is called.
Every run that is not a dry run buys exactly one admission, priced at two cents for each block of up to ten requested suggestions.
The key names that single purchase, so the backend can tell a retried request apart from a genuinely new run.
When the option is absent, the command generates a fresh random key for every invocation.
When the option is present, the backend returns the purchase already made under that key instead of charging again.
The key never carries the goal, the context, or any idea, because the admission request holds only the host and the unit count.

**Purpose of Idempotency Key**
The purpose of Idempotency Key is to recover an admission whose response you never saw, without paying for it twice.
A network drop, a timeout, or a killed terminal can end the command after the backend charged the balance but before the receipt arrived.
Rerunning with the same key returns that same receipt, so the balance is debited once however many times the request is sent.
The receipt is then verified online exactly as a first attempt would be, and the run continues from admission onward.
This makes an automated caller safe to retry an admission failure without first asking whether the charge went through.
It is a billing safeguard only and does not store, cache, or replay any suggestion output.

**When not to use Idempotency Key**
Do not pass Idempotency Key on an ordinary run, because the generated key already makes every new invocation a separate purchase.
Do not reuse a key to get a new set of ideas for free, because the ideas are always generated again and the key only recovers the purchase.
Do not reuse a key after changing the requested count across a block of ten, because a different quantity under the same key is refused as a conflict.
Do not share one key across different goals or different projects, since each separate piece of work deserves its own purchase record.
Do not pass it with a dry run, because a dry run never buys an admission and the key is ignored.
Do not treat the key as a secret or as authentication, because the Vidbyte API key alone identifies you.

**Idempotency Key inputs**
The value is one string of 8 to 128 characters made of letters, digits, dots, underscores, colons, or hyphens.
A value outside that pattern is rejected before the SDK is loaded, before any host is discovered, and before any money moves.
Surrounding whitespace is not trimmed, so pass the key exactly as it was used on the attempt you are recovering.
A UUID, a CI job identifier, or a short label with a date are all valid choices that are easy to repeat later.
Only one key is accepted per run, because one run buys exactly one admission.
The key is sent to the backend as a request header and its hash ties the verification step to this invocation.

**Defaults and precedence for Idempotency Key**
The default is a fresh random UUID generated for each invocation, which makes every ordinary run its own purchase.
No environment variable, configuration value, or project setting can supply a key implicitly.
An explicit key always takes precedence over generation, and the generated key is never written anywhere you would need to find later.
The unit count is computed from the requested count, so the same key and the same count always describe the same purchase.
The key does not change the count, the categories, the rounds, or any other setting of the run.
Every other option is read from the command line exactly as it would be without a key.

**Idempotency Key output contract**
The key is not printed as a progress message, because stdout is reserved for the command result.
A successful run records the admission identifier, the charged amount, and the number of units in the admission field of the result.
Human output prints one line with the Vidbyte charge and the admission identifier after the ranked ideas.
A recovered purchase reports the same admission identifier and the same charge as the original attempt.
A dry run returns a null admission field, which is how a caller can confirm that nothing was bought.
The key never appears in the idea text, the handoff packets, or the project feedback files.

**How to use Idempotency Key**
Leave the option out for every normal run and let the command generate a key.
If an admission attempt fails with a network or timeout error, rerun the identical command with an explicit key you choose.
For automation that may retry, pick the key before the first attempt and reuse it on every retry of that one run.
Keep the goal and the requested count unchanged between attempts, so the recovered purchase matches the request.
After the run completes, use a new key or no key for the next run.
Check the admission field of the result to confirm which purchase the run used.

```text
vidbyte-cli agents suggest run --goal "{goal}" --idempotency-key "{key}"
```

**Examples for Idempotency Key**
A minimal example runs one suggestion pass with no key, which is the normal case.
A retry example passes a key chosen before the first attempt so a lost response can be recovered safely.
A CI example uses the job identifier as the key so a re-queued job never buys a second admission.
A JSON example lets another agent read the admission field and confirm the charge programmatically.
If a retry fails with a purchase conflict, the count changed across a block of ten, so restore the original count or use a new key.
If a retry fails for insufficient balance, add balance first and then rerun with the same key.

```text
vidbyte-cli agents suggest run --goal "{goal}"
vidbyte-cli agents suggest run --goal "{goal}" --count 5 --idempotency-key "{key}"
vidbyte-cli --json agents suggest run --goal "{goal}" --idempotency-key "ci-{job-id}"
```

**Related commands for Idempotency Key**
Use agents suggest run with dry-run first to validate a request for free before any purchase exists.
Use vidbyte-cli whoami to confirm which account an admission will be charged to.
Use vidbyte-cli runtime list to see the per-unit price the backend currently admits for the suggestion agent.
Use agents suggest handoff after a paid run exactly as after any other run, since handoff never buys anything.
Use agents suggest categories, project, and feedback freely, because none of them calls a model or needs a key.
Runtime commands such as runtime stages accept an idempotency key with the same meaning for their own purchases.

**Failure modes for Idempotency Key**
A key that does not match the allowed pattern fails as a usage error before any file, SDK, or network work begins.
A key reused with a different number of units fails as a purchase conflict, and nothing is charged a second time.
A missing login fails before admission, so an unauthenticated retry never creates a purchase.
An insufficient balance fails as payment required, and the same key can be reused after adding balance.
A receipt whose price does not match the requested units is refused locally, and no model is called.
A provider failure after admission does not refund the purchase, and rerunning with the same key buys nothing new.

**Authentication and permissions for Idempotency Key**
Buying an admission requires a stored Vidbyte API key, created at the Vidbyte website and saved with vidbyte-cli login.
The purchase is charged to the prepaid balance of the account that key belongs to.
The key itself grants no permission and identifies nobody, because it only names one purchase.
The admission request carries the host and the unit count, and never the goal, the context, or a file path.
The OpenAI credentials used by Codex are never sent to Vidbyte by this option or by the admission.
The suggestion agents stay read-only on this machine whether or not a key is passed.
