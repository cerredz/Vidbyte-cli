# Transport boundary

`ApiClient` is the only place in the CLI that speaks HTTP. Commands reach the backend through
a typed endpoint group under `endpoints/`, never through httpx directly, so timeout policy,
header injection, response bounds, and failure classification are decided once.

The client resolves nothing. Host, timeout, and credential all arrive as an already-validated
`ResolvedConfig` and `Credentials`, because reading the environment here would let a stale
variable outrank an explicit option and would skip the origin checks `ApiOrigin` has already
performed.

Three rules are load-bearing rather than stylistic:

- **Redirects are never followed.** A redirect would replay the `x-api-key` header to whatever
  host it names. A 3xx is classified as a plain failure instead.
- **Request paths must be relative.** `_url` refuses an absolute or protocol-relative path
  before a socket is opened, for the same reason.
- **Success is never read from the status alone.** `_decode` checks media type, size, JSON
  validity, and the declared model, so a captive portal or proxy error page arriving with a 200
  cannot be mistaken for an approval.

Failures are classified by HTTP status only. The backend serves several different error-body
shapes, so no single `code` field is a platform contract; a client that knew one route's
spelling would be wrong for the next one. The endpoint group or its caller owns any check that
depends on a specific route's vocabulary — `ApiCredentialVerifier` checks `success` for exactly
that reason.

`httpx` is imported inside `ApiClient._send`, not at module scope. Every command module is
imported eagerly when the command tree is built, so a module-scope import would put the httpx
import cost on `--help` and `--version`. `scripts/smoke.py` asserts the boundary.

There are exactly two endpoint groups, because there are exactly two route families an API key
may call: `auth.py` (one key-validation route) and `research.py` (the six research routes).
An endpoint method is added only once the backend serves the route — writing one against a
planned route is designing against an imagined API, which is how this client accumulated a
`/harness/*` group for routes that were never built.

`ResponseShape.ENVELOPE` is the default for `get` and `post` but nothing uses it today: the
research surface returns its DTOs directly and declares `DIRECT` at every call site. It stays
because it is the shape the older public resources use, and the next non-research route will
need it.
