---
name: add-harness
description: Add a new hand-written harness to the Vidbyte CLI, or wire the invocation layer, following this repo's harness standard. Use when creating or modifying anything under src/vidbyte_cli/harnesses/ or src/vidbyte_cli/lib/harness/, or when a task mentions "harness", "harness command", "invocation layer", or "manifest harness".
---

# Adding a harness to the Vidbyte CLI

This is the end-to-end standard for extending the CLI's harness surface. Read it before
touching `src/vidbyte_cli/harnesses/` or `src/vidbyte_cli/lib/harness/`. The reference
implementation is `harnesses/software_engineering/` — copy its shape.

## Mental model

- **`lib/harness/` is the mechanism; `harnesses/` is the policy.** The runtime (base class,
  registry, invocation layer, manifest support) is generic. A harness is a small, declarative
  package that plugs into it.
- **Two ways a harness exists.** If the backend publishes a manifest, the harness needs
  **zero** code here — `HarnessRegistry` serves it via `ManifestHarness`. You only hand-write
  a harness to enrich UX beyond what a manifest can express (typed inputs, custom rendering).
- **One protocol, one lifecycle.** Every harness — hand-written or manifest-generated —
  satisfies `HarnessModule` and runs the same `dispatch` lifecycle:
  `guard → translate → submit → (await) → present → map-errors`. You never touch click or
  httpx.

## The invocation layer (read this before writing a `to_invocation` hook)

`lib/harness/invocation.py` (`InvocationBuilder`) is the **single, universal layer** that
turns parsed CLI params + a command definition (+ an optional repo) into one
`HarnessRunCreateRequest`. It exists because **agents call this CLI heavily and
programmatically**, so two things must be identical for every command and never re-derived
per harness:

1. **Parsing rules** — click hands callbacks flat, lowercased, underscored kwargs
   (`--dry-run` → `dry_run`); the layer maps them back to the declared args/options by name.
2. **Agent-native errors** — a bad invocation raises a `CliError` that names the exact
   argument and command and exits `2` (usage error), so a programmatic caller can branch on
   "I called it wrong" vs. a backend failure.

**Principle: never build a `HarnessRunCreateRequest` by hand in ad-hoc code.** A command that
needs richer handling supplies a `to_invocation` hook that validates into its own typed input
first — but it still produces the same envelope shape, and simple commands must fall through
to `InvocationBuilder.build`. If you find yourself writing request-shaping or param-parsing
logic outside `invocation.py` or a `to_invocation` hook, it belongs in the layer instead.

## The four steps to hand-write a harness

Create `src/vidbyte_cli/harnesses/<name>/` with:

1. **`types.py`** — the harness's own pydantic models (its "custom dataclasses"). These are
   the typed inputs your hooks validate CLI kwargs into. Keep them here, not in the shared
   `types/` package — only this harness understands them.

2. **`commands.py`** — a `build_commands() -> list[HarnessCommandDef]`. Each command is data
   plus optional hooks:
   - `args` / `options` are `ArgSpec` / `OptionSpec` from `types/manifest.py`.
   - `mode` is `"submit"` (fire and return the queued run), `"await"` (poll to completion), or
     `"read"` (one GET).
   - Add a `to_invocation` hook **only** when you need to validate into a typed input before
     shaping the envelope; add a `present` hook **only** when the default status renderer
     isn't good enough. Commands that need neither override nothing.

3. **`harness.py`** — a `BaseHarness` subclass binding `name`, `description`, and
   `commands()`. Set **`requires_repo = True`** when the harness runs against the caller's
   git checkout (the runtime then attaches the repo ref); leave it `False` otherwise. **Not
   every harness runs against a repo — never assume one.**

4. **Register** the instance in `harnesses/__init__.py` by adding it to `HARNESSES`.

Optionally add a `render.py` for the `present` hook (pure string formatting only).

## Invariants (do not break these)

- **Nothing in `commands/`, `cli.py`, or the click wiring changes** when you add a harness.
  The `HarnessRegistry` discovers the module by namespace. If a change forces edits there,
  it's in the wrong layer.
- **Building the command tree touches no services.** `commands()` and `register()` must stay
  free of credential/network I/O so `--help` works offline. Services arrive via
  `HarnessContext` only inside `dispatch`.
- **All logic lives on a class** — no loose module-level helper functions in `base.py` /
  `manifest_harness.py`. Translation/parsing logic lives in the invocation layer; per-command
  variation lives in hooks.
- **`repo` is optional** on `HarnessRunCreateRequest`. Only `requires_repo` harnesses send it.

## Worked example

`harnesses/software_engineering/` is the canonical reference: `fix` overrides both hooks
(validates a `FixInput`, renders a custom result) and `review` uses every default. Mirror it.
