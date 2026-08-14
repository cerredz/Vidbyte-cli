# Harness Runtime and CLI Scaffold

> **Status: Superseded for CLI platform evolution.** This document remains the historical
> source for the accepted generic harness abstraction. The approved seven-PR Python CLI
> platform and research feature program now lives in
> [python-cli-research-harness-program.md](python-cli-research-harness-program.md). Where the
> two documents differ on executable lifecycle, I/O, configuration, HTTP, polling,
> idempotency, research commands, or verification, the newer approved document governs.

Design for the universal Vidbyte CLI and the per-harness sub-CLI runtime it hosts.

## Goal

Ship one client that authenticates against Vidbyte, submits harness runs for the current
repository, and retrieves results — where **each harness is effectively its own sub-CLI**
(`vidbyte-cli harness <name> <command> ...`) whose command set can grow without a CLI
release. Harnesses execute on the backend; the CLI is a thin, typed submit/track/render
client.

## Non-goals

- Running harness logic locally. Execution is entirely backend-side.
- Holding third-party tokens (e.g. GitHub). Linkage lives on the backend.
- A plugin marketplace. Hand-written harnesses are an enrichment set, not the catalog.

## The central decision: manifest-driven, not hardcoded

Harness commands could be (a) compiled into the CLI, one folder per harness, or (b)
described by the backend and built at runtime. A "universal" CLI must not re-couple its
release cycle to the harness catalog, so **(b) is the default**: the backend serves a
*manifest* describing each harness's commands, and the CLI renders it into click commands.
Hand-written modules exist only where a harness deserves richer UX than a manifest can
express — and they satisfy the *same* contract, so everything downstream is identical.

### The manifest

`GET /harness/{name}/manifest` returns (`types/manifest.py`):

```
HarnessManifest { name, version, min_cli_version, description, commands[] }
HarnessCommandSpec { name, description, args[], options[], mode }
ArgSpec { name, required, description }
OptionSpec { name, type: string|number|boolean|path, required, default, description }
```

Per-harness (lazy) rather than one catalog-wide manifest, so a namespace costs one
round-trip and caches independently. A manifest is untrusted-ish input: it is validated
(pydantic) and used only to build flags and help text — never executed.

### The invocation envelope

Every generated command — and the low-level `harness run` — collapses to one request
(`types/api.py`):

```
HarnessRunCreateRequest { harness, command, args: dict, options: dict, repo }
```

So the CLI needs no per-harness request code. `args` are positional inputs, `options` are
flags; both validate against the manifest before submission.

## The harness abstraction (`lib/harness/`)

Every harness command repeats three concerns; the abstraction owns the identical parts and
exposes the varying parts as small typed hooks with defaults.

| Concern | Varies per harness | Identical (in `lib/harness`) |
| --- | --- | --- |
| Declare | command names, args, options | walking specs → click subtree |
| Translate | which field → which invocation | creds guard, repo inspect, submit, poll |
| Present | how results/errors look | error envelope → CliError, secret stripping |

- **`HarnessModule` (protocol)** — the whole contract: `name`, `description`,
  `commands(ctx)`, `register(parent, ctx)`.
- **`BaseHarness`** — implements `register` (builds the click subtree) and `dispatch` (the
  shared lifecycle: `require_credentials` → `repo.as_repo_ref` → translate → `create_run` →
  optional `wait` → present → `map_harness_error`). Authors never touch click or httpx.
- **`HarnessCommandDef`** — a command as data plus two optional hooks (`to_invocation`,
  `present`). Composition over deep inheritance: a trivial command overrides nothing.
- **`HarnessContext`** — injected services (endpoints, repo, credentials, logger, renderer).
  The extensibility seam: new capabilities are added here, not to every subclass. Building
  the command tree never touches these, so `--help` stays free of credential/network I/O.
- **`ManifestHarness(BaseHarness)`** — maps a manifest's specs to `HarnessCommandDef`s with
  default translation/presentation. The zero-code path.
- **`HarnessCatalog`** — fetch + cache manifests under `~/.vidbyte/manifests`; enforces
  `min_cli_version`.
- **`InvocationBuilder`** — the single layer that turns parsed CLI params + a command into a
  `HarnessRunCreateRequest`, with the shared parsing rules and agent-native error messages.
- **`HarnessRegistry`** — owns both sources (the static hand-written map + the catalog) and
  `resolve(name)`: hand-written module wins, else `ManifestHarness`.

### Integration model (`harnesses/<name>/`)

Four steps, mirroring `harnesses/software_engineering/`: `types.py` (data) → `commands.py`
(declare + optional hooks) → `harness.py` (`BaseHarness` subclass, `requires_repo` when it
runs on the caller's checkout) → register in `harnesses/__init__.py`. Nothing else changes.

## CLI wiring (`cli.py`)

- **Static/dynamic seam.** Platform commands and generic harness verbs (`run`, `status`,
  `list`, `catalog`) register synchronously in `commands/__init__.py`.
- **Two-pass argv peek.** click builds its tree synchronously but a manifest is async, so
  `cli.py` scans argv: if it is `harness <name> ...` with `<name>` not a generic verb, it
  loads that one harness (cache-first) and attaches its subtree before parsing. `login`
  never hits the network.
- **Central error trap.** `CliError` → render + exit with its code; `click.ClickException`
  keeps click's formatting/exit code; anything else exits 70.

## Failure modes handled by design

- **Version skew** — manifest `min_cli_version`; fail loudly, don't drop unknown flags.
- **Offline** — cached manifests keep `--help` working.
- **Secret leakage** — the API key is never logged; `map_harness_error` centralizes error
  text so no backend payload leaks the key.
- **Naming collision** — `list` = your runs; `catalog` = available harnesses. Generic verbs
  are reserved and can't be shadowed by a harness namespace.

## Open questions

- Manifest granularity confirmed per-harness; revisit if the catalog is small and static.
- Whether `harness --help` should eagerly list available namespaces (needs a catalog fetch)
  or stay lazy (current behavior).
- Final production API host and the `vidbyte` vs `vidbyte-cli` command name.
