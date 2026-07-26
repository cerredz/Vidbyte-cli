# Research application layer

`ResearchService` owns idempotent start/add/resume orchestration and prompt-free recovery
journaling. `ResearchWatcher` adapts research status to the generic polling platform.
Query/export services preserve opaque IDs and cursors.

These use cases depend on `ResearchGateway`, not HTTP routes. They import neither Click nor
HTTPX, so PR 6 can add UX and PR 7 can add transport without changing research policy.
