---
name: codex-harness-sdk
description: How to drive the Vidbyte SDK's Codex agent from vidbyte-cli — forking, sandboxing, structured output, and the four behaviors in its merged code that its own design doc does not tell you. Read before writing any code that constructs a Codex agent.
---

# Driving the Codex Agent from the SDK

`vidbyte-sdk` exposes `CodexHarnessAgent` (`vidbyte/agents/codex/`), a thin Vidbyte facade over
a Codex-owned agent loop. It is what every local runtime primitive is built on. This skill is
what you need to know before you write against it.

## Read the merged code, not the design doc

Four behaviors matter enormously and are only visible in the implementation. Every one of them
was discovered by reading `agent.py`, `fork.py`, `transport.py`, and `config.py` after PR #409
merged, and three of them contradict what a reasonable person would assume.

### 1. There is no long-lived process

`CodexTransport.run` wraps each turn in `async with sdk.async_codex(config) as client`, and
`CodexHarnessAgent.session_persistence_supported` is `False`. Every turn and every fork opens
and closes its own Codex app-server.

**What follows:** "same host" means same machine, not same process. A three-role ensemble costs
nine app-server startups — one root turn, three forks, three role turns, one implementer fork,
one implementer turn. This is why fan-out must be concurrent: serialized, you pay that latency
end to end. It also means concurrent `afork` on one parent is safe, because the transport holds
no instance state.

### 2. You cannot fork before the first turn

`CodexFork.afork` raises when `parent_thread_id` is empty. A fork needs a provider-confirmed
thread id, and only a completed turn produces one.

**What follows:** every forking topology needs a root turn first. Do not treat it as overhead to
minimize — give it real work. In `same-host-ensemble` the mandatory root turn is what generates
the role roster, so the precondition and the feature are the same turn.

### 3. `ephemeral=True` is a trap

`thread_fork_kwargs` forwards `ephemeral`, so it looks like the way to get agent work that "does
not save". It is not. Ephemeral threads live only on their owning client connection, and
`skills/codex-harness-roadmap/references/checklist.md` item L02 — supporting ephemeral
continuation — is **unchecked**. Combined with fact 1, an ephemeral forked thread is dead before
its child turn can resume it.

**What follows:** use `ephemeral=False`. Get the no-write guarantee from the sandbox instead,
which the provider enforces rather than the thread lifetime.

### 4. An unset sandbox inherits the user's config

Sandbox is settable at two independent levels: `CodexThreadSettings.sandbox` (applied at thread
start, resume, and fork via `_thread_common`) and `CodexTurnSettings.sandbox` (applied per turn
via `turn_kwargs`). Both default to `CodexSandbox.PROVIDER_DEFAULT`, whose value is the empty
string — and `_without_empty` **strips empty values before the SDK call**.

**What follows:** leaving sandbox unset does not mean "safe default". It means the key is never
sent, so the user's own Codex configuration decides, and that may be workspace-write. If a fork
must be read-only, say so explicitly, on both levels. Verify it by constructing the settings and
asserting `settings.codex.thread.sandbox.value == "read-only"` — do not assume.

## Structured output is the proposal channel

`CodexHarnessAgentSettings.output_schema` accepts a Pydantic model class. The translator resolves
it to a JSON schema once at construction, passes it as `turn_kwargs["output_schema"]`, and the
result translator validates the reply back into `AgentMessage.structured`.

Use it whenever an agent's output will be consumed by code rather than read by a person. Prose
forces the next stage to parse; a schema makes disagreement between two agents mechanically
visible — two proposals naming the same file with different approaches is a detectable conflict,
not a paragraph someone has to notice.

`CodexForkSettings` can override the schema per fork, and `clear_output_schema=True` removes an
inherited one. The implementer fork clears it, because its output is a report for a human.

## Packaging: the SDK is optional, and the published release is behind

`CodexHarnessAgent` is on the SDK's `main`, but the published `vidbyte-sdk==0.1.0` wheel contains
**zero** codex files. Verify before assuming otherwise:

```bash
pip download vidbyte-sdk==0.1.0 --no-deps -d /tmp/check
python -c "import zipfile,glob; z=zipfile.ZipFile(glob.glob('/tmp/check/*.whl')[0]); print(len([n for n in z.namelist() if 'codex' in n]))"
```

**What follows:** never import the SDK at module scope in `vidbyte-cli`. `run_ci.py` installs the
built wheel into a clean virtualenv and runs `--help`, which imports every command module, so a
module-scope import fails the gate. Put the import inside a method, convert both `ImportError`
and `AttributeError` into a typed failure, and declare the dependency as an optional extra.
`AttributeError` matters as much as `ImportError`: an SDK at a release predating the integration
imports as a package but has no `CodexHarnessAgent`.

The SDK does exactly this for `openai_codex` in `CodexTransport._load_sdk`. Follow that pattern.

## A naming collision to know about

`scripts/test_research_only_surface.py` scans every `src/**/*.py` for tokens naming deleted
symbols. It originally banned the bare substring `"harness"`, which also matches the SDK's live
`CodexHarnessAgent`. The token list is now precise (`BaseHarness`, `lib.harness`, and so on). If
you add a token there, make it name a specific deleted symbol, never a bare word.

## Checklist before you construct an agent

- [ ] Import is inside a method, not at module scope.
- [ ] Both `ImportError` and `AttributeError` become one typed, pre-payment failure.
- [ ] Sandbox is set explicitly on `thread` **and** `turn` for every settings bundle.
- [ ] `ephemeral` is `False`.
- [ ] `thread.cwd` and `turn.cwd` are set from a validated working directory.
- [ ] A root turn runs before any `afork`.
- [ ] Any agent whose output feeds code has an `output_schema`.
- [ ] `asyncio.run` appears exactly once, at the service's synchronous boundary.
- [ ] Concurrent work uses `asyncio.gather(..., return_exceptions=True)` with a per-branch
      `asyncio.timeout`.
- [ ] `asyncio.CancelledError` is never converted into a result record.

## Related

- `references/build-decisions.md` — the ordered decisions to make when building one of these.
- `skills/harnesses/runtime-primitives/SKILL.md` — the shape every primitive shares.
