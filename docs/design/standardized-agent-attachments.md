# Design Doc: Standardized Agent Attachments

**Status:** Draft
**Author:** Codex
**Created:** 2026-09-15
**Last Updated:** 2026-09-15

---

## 1. Overview

This feature adds a shared, integration-ready contract for attaching explicit local files to
Vidbyte agent invocations. It resolves each path once into a bounded immutable snapshot with
stable metadata, so future agent commands can expose the same repeatable `--attach PATH` option
without reimplementing file validation, hashing, limits, error handling, or provider conversion.
This change deliberately does not add the option to existing agent commands; those commands will
adopt the shared contract in a later integration change.

---

## 2. Goals & Non-Goals

### Goals

- Define typed attachment and attachment-bundle models shared by commands and services.
- Resolve explicit files deterministically before any model call, credential use, or paid admission.
- Support bounded UTF-8 text snapshots and native local-image inputs.
- Reject directories, missing files, duplicate paths, unsupported binary files, unreadable files,
  and size-limit violations with agent-actionable typed CLI failures.
- Provide a reusable Click option decorator and value resolver for future agent commands.
- Provide one lazy Codex adapter so future Codex services do not repeat provider mapping logic.
- Preserve file order, content hashes, and a body-free manifest for machine-readable output.
- Add an offline script that exercises the full resolver and adapter contract.

### Non-Goals

- Do not modify or register `--attach` on any existing command in this change.
- Do not change semantic inputs such as `--input`, `--handoff-file`, `--previous-suggestions`, or
  `--task-file`.
- Do not grant an agent filesystem permissions or expand its sandbox.
- Do not parse PDFs, DOCX files, archives, directories, globs, or arbitrary binary formats.
- Do not persist attachment bodies or add a backend endpoint.
- Do not add a new provider abstraction for hosts that the CLI does not currently integrate.

---

## 3. Background & Context

- The main branch has no generic attachment resolver. Task-board's `--task-file` reads a whole
  Markdown file as one task, which is a semantic task source rather than reusable agent context.
- `runtime persistence` currently sends only `CodexRunInput.text(prompt)` through
  `services/persistence/session.py`; `runtime same-host-ensemble` centralizes text conversion in
  `services/ensemble/sdk.py` and fans the root thread into several stages.
- The SDK pinned by this repository already exposes `FileContextItem`, `CodexLocalImageInput`, and
  `CodexRunInput.context_items`, so the CLI needs a stable local contract and a lazy adapter rather
  than a second provider protocol.
- The repository requires typed failures, stdout-only results, lazy optional SDK imports, strict
  validation before paid admission, and the canonical `scripts/run_ci.py` gate.
- Existing branch changes and untracked design documents are unrelated and must remain untouched.

---

## 4. Requirements

### Functional Requirements

1. `AttachmentResolver.resolve` accepts an ordered tuple of explicit `Path` values and returns an
   immutable `AttachmentBundle`.
2. An empty path tuple returns an empty bundle without filesystem access.
3. Each path is resolved once, must identify a regular file, and must not repeat another resolved
   path in the same bundle.
4. The resolver reads text files as UTF-8 (accepting a UTF-8 BOM), preserves their decoded body,
   and classifies known image suffixes as native images without embedding their bytes in the
   bundle.
5. A file that cannot be decoded as UTF-8 and is not a supported image is rejected as unsupported.
6. Per-file byte size, total byte size, and file-count limits are enforced before a bundle is
   returned; attachments are rejected rather than silently truncated.
7. Every attachment records the caller path, resolved path, basename, kind, byte size, and full
   SHA-256 hash. Text attachments also record decoded content.
8. `AttachmentBundle.manifest()` returns body-free dictionaries suitable for machine output.
9. `AgentAttachmentOptions.apply` declares a repeatable `--attach PATH` Click option, and
   `AgentAttachmentOptions.resolve` converts parsed values into an `AttachmentBundle`.
10. `CodexAttachmentInputBuilder.build` lazily imports the optional SDK and maps text attachments
    to `FileContextItem` context items and images to `CodexLocalImageInput` items while retaining
    the task as a text input.
11. The adapter passes no attachment bodies to diagnostics, metadata, or the backend admission
    request.
12. Existing command registration and behavior remain unchanged until a later integration PR.

### Non-Functional Requirements

- Resolution is synchronous, bounded, and linear in the number of supplied files and bytes read.
- No filesystem scan, glob expansion, network call, credential read, model call, or payment occurs
  inside command registration or while rendering `--help`.
- Errors are typed `CliError` subclasses with static, agent-actionable descriptions and no file
  body or credential leakage.
- All returned models are immutable and reject unknown fields.
- Hashing is deterministic and makes a changed file distinguishable from the original snapshot.
- Limits live in `lib/constants/runtime.py` and are not duplicated in command or resolver logic.

---

## 5. High-Level Design

The shared layer has three boundaries. `AgentAttachmentOptions` owns Click syntax but no file I/O.
`AttachmentResolver` owns path validation, bounded reads, classification, hashing, and the typed
bundle. `CodexAttachmentInputBuilder` is a provider adapter that remains lazy because the CLI
must keep its command tree usable without an SDK-compatible installation. Future commands pass
the resulting bundle into their own typed request or runtime settings; this PR does not edit those
commands.

```text
[future agent command]
        |
        v
[AgentAttachmentOptions] -- parsed paths --> [AttachmentResolver]
                                                   |
                                  immutable bundle + manifest
                                                   |
                                      [future agent service]
                                                   |
                                   [CodexAttachmentInputBuilder]
                                                   |
                                        [CodexRunInput]
```

The chosen representation is a content snapshot for text and a validated path reference for
images. A snapshot is deterministic and auditable, while the agent's existing working-directory
sandbox remains the authority for edits. The resolver fails closed on incomplete inputs instead of
truncating a specification or source file and allowing an agent to act as though it saw the whole
file.

---

## 6. Detailed Design

### 6.1 Attachment Contracts

**File(s):** `src/vidbyte_cli/types/attachments.py`
**Type:** New file

#### What it does

Defines the closed attachment kind vocabulary plus frozen, extra-forbid Pydantic models for one
attachment and a bundle. The models are provider-neutral and contain no I/O behavior.

#### Interface / API

```python
class AttachmentKind(StrEnum):
    TEXT = "text"
    IMAGE = "image"


class AgentAttachment(BaseModel):
    supplied_path: Path
    resolved_path: Path
    name: str
    kind: AttachmentKind
    size_bytes: int
    sha256: str
    content: str | None = None


class AttachmentBundle(BaseModel):
    items: tuple[AgentAttachment, ...] = ()
    total_bytes: int = 0

    def manifest(self) -> tuple[dict[str, object], ...]: ...
```

#### Logic / Algorithm

1. Pydantic validates non-empty names, positive sizes, a 64-character lowercase SHA-256, and
   content only for text items.
2. The bundle validates that its total equals the sum of item sizes and that resolved paths are
   unique.
3. `manifest` emits path, name, kind, byte size, and hash only.

#### Edge Cases & Error Handling

- An empty bundle is valid and has total size zero.
- Image content remains `None`; text content must be non-empty after decoding unless the file is a
  zero-byte file, which is rejected by the resolver as unusable context.
- Unknown model fields fail validation rather than being ignored.

### 6.2 Attachment Limits

**File(s):** `src/vidbyte_cli/lib/constants/runtime.py`
**Type:** Modified

#### What it does

Adds `AttachmentLimit` as the single source for file count, per-file bytes, total bytes, and known
image suffixes.

#### Interface / API

```python
class AttachmentLimit(IntEnum):
    MAX_FILES = 50
    MAX_FILE_BYTES = 1_000_000
    MAX_TOTAL_BYTES = 8_000_000
```

The image suffix tuple is a named constant in the same module because it is a closed provider
classification vocabulary rather than a caller setting.

#### Logic / Algorithm

The resolver reads these values and never embeds a second limit or suffix list.

#### Edge Cases & Error Handling

Exactly-at-limit files are accepted; one byte or one path over a limit is rejected before later
paths are read.

### 6.3 Attachment Resolution

**File(s):** `src/vidbyte_cli/lib/io/attachments.py`
**Type:** New file

#### What it does

Reads explicit paths into validated attachment records. It is the only component allowed to touch
the filesystem for generic attachments.

#### Interface / API

```python
class AttachmentResolver:
    def resolve(self, paths: tuple[Path, ...]) -> AttachmentBundle: ...
```

#### Logic / Algorithm

1. Reject more than `MAX_FILES` paths.
2. Resolve each path and reject missing paths, directories, duplicate resolved paths, and unreadable
   files with typed CLI failures.
3. Read bytes once, reject zero-byte files and per-file/total byte overflow, and compute SHA-256.
4. Classify known image suffixes as `IMAGE`; decode all other bytes as UTF-8 with BOM support.
5. Reject non-UTF-8 non-image bytes.
6. Construct the immutable bundle in caller order.

#### Edge Cases & Error Handling

- No paths performs no I/O.
- A symlink is accepted only when its resolved target is a regular file selected explicitly by the
  caller; its resolved target participates in duplicate detection.
- A file changed between stat and read is represented by the bytes actually read; the resolver does
  not rely on a stale pre-read size.
- Any `OSError`, decode failure, duplicate, unsupported type, or limit violation becomes a
  dedicated `CliError` subclass without embedding the path or body in its authored prose.

### 6.4 Reusable Command Option

**File(s):** `src/vidbyte_cli/commands/agent_options.py`
**Type:** New file

#### What it does

Provides one Click decorator and one typed extraction method for future agent commands. It is not
registered on any command in this PR.

#### Interface / API

```python
class AgentAttachmentOptions:
    def apply(self, callback: CommandCallback) -> CommandCallback: ...
    def resolve(self, values: Mapping[str, object]) -> AttachmentBundle: ...
```

#### Logic / Algorithm

1. `apply` adds repeatable `--attach`, stores values under `attachments`, and uses the four-sentence
   caller-facing help constant.
2. `resolve` accepts Click's tuple of `Path` values and delegates all validation to
   `AttachmentResolver`.
3. Missing values become an empty bundle; no default path is invented.

#### Edge Cases & Error Handling

- The option may be repeated in any order and preserves occurrence order.
- Programmatic callers passing a non-tuple or non-`Path` value receive an invalid-argument failure,
  not an accidental iteration over a string.
- Because no command uses this decorator yet, current `--help` output is unchanged.

### 6.5 Codex Input Adapter

**File(s):** `src/vidbyte_cli/lib/io/codex_attachments.py`
**Type:** New file

#### What it does

Maps the provider-neutral bundle into the pinned SDK's native Codex input types without importing
the optional SDK during module import.

#### Interface / API

```python
class CodexAttachmentInputBuilder:
    def build(self, prompt: str, bundle: AttachmentBundle) -> object: ...
```

#### Logic / Algorithm

1. Import `CodexRunInput`, `CodexTextInput`, `CodexLocalImageInput`, and `FileContextItem` inside
   `build`.
2. Start with one text input containing the prompt.
3. Add each image as a local-image input.
4. Add each text attachment as a `FileContextItem` carrying its original path, resolved path, byte
   size, decoded content, language, and hash metadata.
5. Return one `CodexRunInput` with the text/image items and context items.

#### Edge Cases & Error Handling

- An empty bundle produces the same semantic request as a text-only turn.
- Missing SDK symbols raise the existing typed SDK-unavailable failure at the future service
  boundary; this module does not turn import failures into silent text-only execution.
- The adapter never reads the filesystem, so it cannot observe a different body from the resolver's
  snapshot.

### 6.6 Typed Attachment Failures

**File(s):** `src/vidbyte_cli/lib/errors/failures.py`
**Type:** Modified

#### What it does

Adds dedicated usage failures for missing files, directories, unreadable files, unsupported file
types, duplicate paths, empty files, and limit violations. Each carries static message,
description, trace, and hint text compatible with human and machine error output.

#### Interface / API

```python
class AttachmentFileNotFound(CliError): ...


class AttachmentDirectory(CliError): ...


class AttachmentUnreadable(CliError): ...


class AttachmentUnsupported(CliError): ...


class AttachmentDuplicate(CliError): ...


class AttachmentEmpty(CliError): ...


class AttachmentTooLarge(CliError): ...


class AttachmentLimitExceeded(CliError): ...
```

#### Logic / Algorithm

The resolver raises exactly one class for each failure category. Error handling continues to use
the existing central `ErrorHandler`; no raw `OSError` or `UnicodeDecodeError` escapes.

#### Edge Cases & Error Handling

Descriptions name the corrective action and state that no model, credentials, or admission was
started. They do not include private paths, file bodies, hashes, or secrets.

### 6.7 Public I/O Facade

**File(s):** `src/vidbyte_cli/lib/io/__init__.py`
**Type:** Modified

#### What it does

Exports `AttachmentResolver` and the lazy Codex adapter from the existing I/O facade. Future
commands import the provider-neutral bundle types from `vidbyte_cli.types.attachments`, keeping
the I/O facade focused on process-boundary behavior.

#### Interface / API

The existing stream and prompt exports remain unchanged; attachment exports are additive.

#### Logic / Algorithm

No runtime logic is added. Importing the facade remains free of SDK imports and filesystem access.

#### Edge Cases & Error Handling

Importing `vidbyte_cli.lib.io` must work in a clean environment without Codex installed.

---

## 7. Data Model Changes

### 7.1 AgentAttachment and AttachmentBundle

**Change type:** New local, in-memory types

```python
AgentAttachment(
    supplied_path: Path,
    resolved_path: Path,
    name: str,
    kind: AttachmentKind,
    size_bytes: int,
    sha256: str,
    content: str | None,
)

AttachmentBundle(items: tuple[AgentAttachment, ...], total_bytes: int)
```

**Migration strategy:** N/A - no persisted documents or wire schemas change. Future
command-specific context manifests can consume the shared models without a migration.

---

## 8. API Changes

N/A - this change adds no HTTP endpoint and sends no attachment metadata to the backend admission
routes.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/standardized-agent-attachments.md` | Source-of-truth design and integration contract |
| CREATE | `src/vidbyte_cli/types/attachments.py` | Typed provider-neutral attachment models |
| CREATE | `src/vidbyte_cli/lib/io/attachments.py` | Bounded explicit-file resolver |
| CREATE | `src/vidbyte_cli/lib/io/codex_attachments.py` | Lazy Codex input conversion |
| CREATE | `src/vidbyte_cli/commands/agent_options.py` | Reusable future `--attach` Click option |
| MODIFY | `src/vidbyte_cli/lib/io/README.md` | Document the shared attachment I/O modules |
| MODIFY | `src/vidbyte_cli/commands/README.md` | Document the reusable agent option helper |
| MODIFY | `src/vidbyte_cli/lib/io/__init__.py` | Export the shared attachment resolver |
| MODIFY | `src/vidbyte_cli/lib/constants/runtime.py` | Centralize attachment limits and image suffixes |
| MODIFY | `src/vidbyte_cli/lib/errors/failures.py` | Add typed attachment failures |
| MODIFY | `scripts/run_ci.py` | Run the attachment verification script in the canonical gate |
| MODIFY | `lint/baseline.json` | Ratchet the already-improved C002 allowance from 3 to 2 |
| CREATE | `scripts/test-agent-attachments.py` | Offline unit/integration verification for every requirement |

No files are deleted. Existing agent command files are intentionally not modified.

---

## 10. Testing Plan

### Unit Tests

- `AttachmentBundle` accepts an empty tuple and reports zero total bytes. **[Edge Case]**
- A text file at exactly `MAX_FILE_BYTES` is accepted and one byte over is rejected. **[Edge Case]**
- Exactly `MAX_FILES` paths are accepted and one additional path is rejected. **[Edge Case]**
- An empty path tuple performs no filesystem access. **[Hidden Assumption]**
- UTF-8 BOM text decodes without the BOM in content. **[Silent Failure]**
- A file containing only a UTF-8 BOM raises `AttachmentEmpty` after decoding. **[Edge Case]**
- Text content and SHA-256 match the bytes used to build the bundle. **[Silent Failure]**
- A known image suffix creates an image attachment with no embedded text content. **[Edge Case]**
- A non-UTF-8 non-image file raises `AttachmentUnsupported`. **[Hidden Failure]**
- A missing path raises `AttachmentFileNotFound`. **[Hidden Failure]**
- A directory raises `AttachmentDirectory`. **[Hidden Failure]**
- An unreadable path raises `AttachmentUnreadable`. **[Hidden Failure]**
- A zero-byte file raises `AttachmentEmpty`. **[Edge Case]**
- The same file supplied through two path spellings raises `AttachmentDuplicate`. **[Hidden Assumption]**
- Total bytes exactly at the limit pass and one byte over raises `AttachmentLimitExceeded`. **[Edge Case]**
- Manifest entries contain no content field or body. **[Silent Failure]**
- Unknown Pydantic fields are rejected for attachment and bundle models. **[Hidden Assumption]**
- A non-tuple programmatic Click value raises a typed invalid-argument failure. **[Hidden Failure]**
- Repeated Click values preserve their order. **[Silent Failure]**

### Integration Tests

- `AgentAttachmentOptions.apply` renders a repeatable `--attach PATH` option without changing
  unrelated command registration. **[Hidden Assumption]**
- `AgentAttachmentOptions.resolve` returns the same ordered bundle as direct resolver use.
  **[Silent Failure]**
- `CodexAttachmentInputBuilder` maps one text and one image into text/native-image inputs plus a
  `FileContextItem`, using a fake SDK module boundary and no live Codex process. **[Hidden Failure]**
- Importing `vidbyte_cli.lib.io` and the option helper succeeds when the SDK import is unavailable.
  **[Hidden Assumption]**
- The adapter's file context contains the resolver snapshot even after the source file changes.
  **[Silent Failure]**
- The adapter does not expose attachment bodies through its manifest or metadata. **[Hidden Failure]**

### Manual / QA Test Cases

1. Given a future command decorated with `AgentAttachmentOptions`, when invoked with two
   `--attach` flags, then help describes the option and execution receives both files in order.
2. Given a missing or oversized attachment, when the future command is invoked, then the command
   exits with the standard usage status before credentials, payment, or model startup.
3. Given `--help` in an environment without the optional Codex SDK, when the CLI starts, then help
   still renders because the adapter is lazy and no existing command imports it eagerly.
4. Given a text file changed after resolution, when a future agent executes, then it sees the
   captured hash and body, not a second read with different content.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python standard library | 3.11+ | `pathlib`, hashing, UTF-8 decoding, and dataclasses/helpers | Low; already required |
| Pydantic | `>=2.6,<3` | Frozen, strict attachment contracts | Low; existing dependency |
| Click | `>=8.1,<9` | Reusable command option decorator | Low; existing dependency |
| Vidbyte SDK | Existing pinned Codex revision, lazy | Convert bundles to native Codex input records | Medium; optional import and provider API shape |

No network service, database, credential store, or backend route is used.

---

## 12. Rollout & Deployment

- No feature flag is needed because no existing command is changed.
- The change is additive and therefore backward compatible.
- Merge the design and shared infrastructure first. A later PR can add `--attach` to individual
  agent commands and choose each command's attachment audience and output manifest policy.
- Rollback is a normal revert of the additive commits. No migration or persisted state cleanup is
  required.

---

## 13. Open Questions

- [ ] Should later command integrations expose all generic text files, or add explicit parsers for
  PDF/DOCX and other binary formats?
- [ ] Should a future command allow attachments outside its working directory when content is
  snapshotted, or restrict paths to the workspace for simpler operator expectations?
- [ ] Should future domain-specific context flags become aliases for `--attach`, or retain their
  own semantics?
- [ ] Should task-board attachments be global to every task agent or support a future per-task
  attachment alignment?

---

## 14. Alternatives Considered

### Alternative 1: One global root-level `--attach` option

- What: Add attachments to the root parser so every command accepts the flag.
- Why rejected: Administrative and API-read commands have no agent input, and a global option would
  advertise meaningless behavior while complicating root-prefix inspection and help contracts.

### Alternative 2: Add file reads independently to each future agent command

- What: Let every future command read, classify, and hash its own files.
- Why rejected: It recreates the exact duplication this feature is intended to remove and would let
  limits, decoding, truncation, and error wording drift.

### Alternative 3: Pass only live paths in the prompt

- What: Add path strings to the task and let each agent open files itself.
- Why rejected: It is not deterministic, fails for paths outside a sandbox, makes text snapshots
  impossible to audit, and allows a file to change between validation and execution.

### Alternative 4: Truncate files to fit a model budget

- What: Silently keep a prefix of oversized attachments.
- Why rejected: A source file or specification can appear complete while missing the decisive tail.
  The first shared contract fails closed; a later explicit excerpt mode can carry its own visible
  truncation semantics.

### Alternative 5: Introduce an abstract base class for every agent command

- What: Require all future commands to inherit common admission, output, attachment, and execution
  methods.
- Why rejected: The existing command families have materially different transport, payment,
  topology, and output behavior. A small typed bundle and option helper solve the common problem
  without creating a framework with one implementation per method.
