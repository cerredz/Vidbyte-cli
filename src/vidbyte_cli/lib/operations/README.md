# Durable local operations

This package owns client-side recovery identity, not remote work. Every costly mutation
receives one idempotency key and a prompt-free journal record before it is sent. Acceptance
adds only the opaque remote ID and recovery command.

Operation files live in the platform state directory and use the shared atomic writer.
They never contain prompts, credentials, request bodies, artifacts, or provider output.
