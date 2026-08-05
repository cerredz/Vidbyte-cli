# API transport boundary

Endpoint groups declare Vidbyte routes and response shapes. `ApiClient` alone owns HTTPX,
authentication headers, request identity, timeouts, and retry orchestration. `response.py`
validates bounded JSON and `problem.py` maps failures without exposing response prose.

Mutations are retryable only with a stable idempotency key. Feature packages do not import
HTTPX; their adapters depend on endpoint groups or gateway protocols.
