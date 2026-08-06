# Product features

Each folder owns one product's domain, application use cases, command adapters,
presentation, and optional transport adapter. Reusable HTTP, storage, output, and polling
mechanisms stay in `lib/`.

Feature domain/application packages must not import Click or HTTPX. This keeps business
rules independently reviewable and prevents transport changes from rewriting product logic.
