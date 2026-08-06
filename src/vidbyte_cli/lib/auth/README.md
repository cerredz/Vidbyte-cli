# Authentication boundary

This package keeps secret resolution separate from non-secret configuration.
`CredentialResolver` applies environment → OS keyring → restricted-file precedence.
`CredentialStore` writes the OS keyring by default and requires explicit caller consent
before its fallback file can be used. Entries are scoped to profile and normalized API host.

Login input never accepts a raw token argv value, and the `CredentialVerifier` protocol
enforces verify-before-persist. The HTTP-backed verifier lands with the reusable networking
platform in PR 4; this PR leaves a safe, non-persisting seam.
