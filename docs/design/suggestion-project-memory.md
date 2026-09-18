# Design Doc: Suggestion Project Memory and Feedback Commands

**Status:** Draft
**Author:** Codex
**Created:** 2026-09-17
**Last Updated:** 2026-09-18

---

## 1. Overview

Add a small local JSON memory store to the existing `agents suggest` command family. A caller can create a project with a stable key, title, and description, list the project catalog, and record explicit accepted or rejected suggestion feedback for a project. Each project keeps its feedback in a separate JSON file, while one index JSON file holds the catalog and links each key to its memory file. An optional `--project` on `agents suggest run` loads the selected project memory into the existing bounded suggestion context so later runs can use it without requiring a backend, database server, or new dependency.

---

## 2. Goals & Non-Goals

### Goals

- Add `agents suggest project create` for a new key, title, and description.
- Add `agents suggest project list` for a credential-free catalog read.
- Store the catalog in one versioned `projects.json` file and feedback in one versioned JSON file per project.
- Add `agents suggest feedback accept` and `agents suggest feedback reject` with agent-facing help text.
- Preserve accepted and rejected feedback in append order with the original suggestion and optional user reason.
- Add optional `--project` to `agents suggest run` and include that project's metadata and feedback as context.
- Reuse `VidbytePaths`, the `lib/files` stores, `ApplicationContext`, `OutputDocument`, typed failures, and the existing command registration, help-asset, and rendering patterns.
- Keep stateless suggestion runs unchanged when `--project` is omitted.

### Non-Goals

- No MongoDB, backend endpoint, account synchronization, or cloud backup.
- No SQLite, migration framework, file watcher, repository auto-detection, or current-directory inference.
- No project update, delete, archive, or feedback removal command in this change.
- No automatic inference of user acceptance or rejection from silence, implementation, or an ambiguous response.
- No model call when creating, listing, or recording feedback.
- No model-generated feedback summaries, semantic search, embedding index, or unbounded prompt history policy.
- No redesign of the existing generator and critic workflow beyond adding project context.

---

## 3. Background & Context

- `agents suggest` already owns local suggestion commands, structured output, context assembly, and deterministic handoffs. The command family is registered in `src/vidbyte_cli/commands/agents/suggestion/__init__.py` and the service accepts typed `SuggestionRequest` values.
- The current suggestion design explicitly deferred durable project memory and database state. This feature is the small follow-up that introduces only the file state needed for project definitions and explicit feedback.
- The repository requires results on stdout, diagnostics on stderr, versioned machine envelopes, integer-returning reusable command entry points, and typed `CliError` subclasses for visible failures.
- `VidbytePaths` already selects platform-native config, data, cache, and state roots. `LocalFileStore` in `lib/files` already creates parent directories and replaces files atomically through a temp sibling.
- The project memory is deliberately local. It may contain user preferences or copied task language, so it must not require credentials or send data anywhere except a provider when a caller explicitly runs the suggestion agent.
- The existing context builder assigns stable per-run references and enforces file limits. Project memory will be converted into ordinary context items at the command boundary rather than adding a second prompt transport.

---

## 4. Requirements

### Functional Requirements

1. `agents suggest project create --key KEY --title TITLE --description DESCRIPTION` creates one project and its memory file. `KEY` must be a safe lowercase identifier and must be unique in the catalog.
2. Creating an existing key fails before writing either file and returns a typed, actionable error.
3. `agents suggest project list` reads only the catalog, returns all projects in stable key order, and succeeds with an empty list when no catalog exists.
4. The catalog is stored as a versioned JSON document at the platform-native suggestion projects path. Each entry contains `key`, `title`, `description`, and a relative `memory_file` link.
5. Each project memory file is a versioned JSON document containing its `project_key` and an ordered `feedback` array. Each feedback record contains `type`, `suggestion`, `reason` when supplied, and an ISO-8601 UTC `created_at` value.
6. `agents suggest feedback accept` appends an `accepted` record for an existing project. `agents suggest feedback reject` appends a `rejected` record for an existing project.
7. Feedback commands require a project key and nonempty suggestion text. The reason is optional for acceptance and rejection, but when supplied it is stored verbatim and is never invented by the CLI.
8. Feedback commands never infer a reaction. Their help text explicitly tells parent agents to call them only after the user clearly accepts or rejects a suggestion.
9. `agents suggest run --project KEY` loads the project catalog entry and memory file, then adds the project title, description, accepted feedback, and rejected feedback to the run's context before the existing service call.
10. A suggestion run without `--project` does not read or create project files and produces the same request shape and behavior as before this feature.
11. Project-backed results identify the selected project and include deterministic instructions for the parent agent to record explicit future acceptance or rejection. The instruction is informational and does not execute a feedback command.
12. Corrupt, unsupported, missing, or unexpectedly shaped local JSON fails with a typed error that names the relevant command and repair action. A failed write leaves the last valid document intact.
13. Project keys cannot escape the projects directory through path traversal, separators, absolute paths, or unsupported characters.
14. All new command and option help contains at least four complete caller-facing sentences covering the value, default, when to use it, and interaction with related options.

### Non-Functional Requirements

- Local reads and writes should remain bounded by small JSON documents; no network or provider lookup is allowed for project, list, or feedback commands.
- Writes must use the existing atomic writer and private platform-native data roots. Read-modify-write must validate the current document before replacing it.
- The store must tolerate a missing first-run directory and preserve existing files on validation or operating-system failure.
- Project context included in a run must remain ordinary data, not privileged instruction text. The existing context limits remain the upper bound for the assembled prompt.
- Machine output must use `schema_version` and `kind`; human output must remain concise and diagnostics must not leak full suggestion or feedback bodies in errors.

---

## 5. High-Level Design

Split storage from meaning. A general `LocalDocumentStore` in `lib/files` reads, bounds, validates against a caller-supplied pydantic model, contains linked names inside its root, and atomically writes JSON documents; it knows nothing about suggestions. A `SuggestionProject` class in `services/suggestions/project.py` owns what a project is: it takes frozen input dataclasses (`SuggestionProjectKey`, `SuggestionProjectCreateInput`, `SuggestionFeedbackInput`) and exposes small decoupled operations such as `create`, `list_projects`, `project_exists`, `get_project`, `project_metadata`, `get_project_feedback`, `record_feedback`, and `context_fields`. `VidbytePaths` gains one `suggestions_dir()` root. Commands remain thin: they parse Click options, build an input dataclass, call `SuggestionProject`, and render `OutputDocument` results; every command and option help text is a Markdown asset under `commands/agents/suggestion/prompts/`.

The catalog is an index rather than an algorithmic linked list. `projects.json` contains project summaries and a relative link to each project file, so listing does not open every memory file. A project file contains only that project's ordered feedback. The stable key is validated before it becomes a filename, and the store confirms the resolved path remains inside the project-memory directory.

When `--project` is present on `suggest run`, the command loads the project record and converts its metadata and feedback to existing context fields. The request then follows the current context builder and `SuggestionService` path. The result carries the project key and a deterministic feedback-capture note; no project state is created for stateless runs.

```text
[agents suggest project create]
             |
      [projects.json] ---- memory_file ----> [projects/<key>.json]
                                                   |
[agents suggest feedback accept/reject] ----------+
                                                   |
[agents suggest run --project KEY] -> [context items] -> [SuggestionService]
                                                   |
                                      [result + feedback instructions]
```

---

## 6. Detailed Design

### 6.1 Project class and general document store

**File(s):** `src/vidbyte_cli/services/suggestions/project.py`, `src/vidbyte_cli/lib/files/documents.py`
**Type:** New files

#### What it does

`LocalDocumentStore` is the canonical, product-neutral class for small versioned JSON documents: `read(name, model)` returns `None` only when the document is absent and raises `LocalDocumentInvalid` for an oversized, unparseable, or schema-mismatched one; `write(name, document)` serializes sorted, indented JSON through `LocalFileStore`'s atomic replace; `path_of(name)` refuses absolute, `..`, or link-escaping names; `remove(name)` rolls back a document written earlier in the same mutation. `SuggestionProject` uses it for the catalog and every memory file and translates its generic failures into suggestion-specific ones in exactly two places.

#### Interface / API

```python
@dataclass(frozen=True, slots=True)
class SuggestionProjectKey:
    value: str  # validated and trimmed in __post_init__


@dataclass(frozen=True, slots=True)
class SuggestionProjectCreateInput:
    key: SuggestionProjectKey
    title: str
    description: str


@dataclass(frozen=True, slots=True)
class SuggestionFeedbackInput:
    key: SuggestionProjectKey
    feedback_type: FeedbackType
    suggestion: str
    reason: str | None = None


class SuggestionProject:
    def create(self, request: SuggestionProjectCreateInput) -> SuggestionProjectRecord: ...
    def catalog(self) -> SuggestionProjectCatalog: ...
    def list_projects(self) -> tuple[SuggestionProjectRecord, ...]: ...
    def project_exists(self, key: SuggestionProjectKey) -> bool: ...
    def get_project(self, key: SuggestionProjectKey) -> SuggestionProjectRecord: ...
    def project_metadata(self, key: SuggestionProjectKey) -> tuple[str, ...]: ...
    def get_project_feedback(self, key: SuggestionProjectKey) -> tuple[SuggestionFeedback, ...]: ...
    def record_feedback(self, request: SuggestionFeedbackInput) -> SuggestionFeedback: ...
    def context_fields(self, key: SuggestionProjectKey) -> dict[str, tuple[str, ...]]: ...
    @staticmethod
    def feedback_capture(key: SuggestionProjectKey) -> SuggestionFeedbackCapture: ...


class LocalDocumentStore:
    def path_of(self, name: str | Path) -> Path: ...
    def exists(self, name: str | Path) -> bool: ...
    def read(self, name: str | Path, model: type[DocumentT]) -> DocumentT | None: ...
    def write(self, name: str | Path, document: BaseModel) -> Path: ...
    def remove(self, name: str | Path) -> None: ...
```

#### Logic / Algorithm

1. Input dataclasses validate the key pattern, title and description bounds, and feedback text bounds before any document is read.
2. For creation, read the catalog, refuse an existing key or an existing memory file, write the empty memory file, then publish the catalog entry. If the catalog write fails, remove the new memory file and re-raise.
3. For listing and lookup, treat an absent catalog as empty but an existing malformed catalog as unreadable state.
4. For feedback, resolve the project, read its linked memory, confirm its `project_key`, append one record, and replace the memory document atomically.
5. `context_fields` returns the `project` metadata lines plus `accepted_feedback` and `rejected_feedback` items rendered by `SuggestionFeedback.context_text()`.

#### Edge Cases & Error Handling

- Reject blank, uppercase, separator-containing, absolute, or traversal keys in `SuggestionProjectKey`.
- Reject duplicate keys and leftover memory files without modifying anything.
- Reject malformed JSON, unsupported schema versions, missing linked memory files, links outside the store root, and mismatched `project_key` values as `SuggestionProjectStateUnreadable`.
- Refused writes raise `SuggestionProjectWriteFailed`; the previous document stays intact.
- Do not expose feedback bodies, absolute paths, or exception tracebacks in normal error text.

### 6.2 Project and feedback data contracts

**File(s):** `src/vidbyte_cli/types/suggestions.py`
**Type:** Modified

#### What it does

Adds frozen, extra-forbid models for project catalog records, project memory documents, feedback records, and the feedback-capture instructions returned with project-backed suggestion results. Adds optional `project_key` fields to `SuggestionRequest` and `SuggestionResult` so stateless calls remain compatible.

#### Interface / API

```python
class FeedbackType(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class SuggestionProject(BaseModel):
    key: str
    title: str
    description: str
    memory_file: str


class SuggestionFeedback(BaseModel):
    type: FeedbackType
    suggestion: str
    reason: str | None = None
    created_at: str


class SuggestionProjectMemory(BaseModel):
    schema_version: Literal[1] = 1
    project_key: str
    feedback: tuple[SuggestionFeedback, ...] = ()
```

#### Logic / Algorithm

1. Keep all persisted models frozen and extra-forbid.
2. Validate lengths at the model boundary so commands and store reads share the same limits.
3. Keep `project_key` optional on request and result; only project-backed invocations populate it.
4. Keep feedback capture as a small result field or nested model, not inside the execution prompt.

#### Edge Cases & Error Handling

- Empty feedback arrays and empty project catalogs are valid.
- `reason: null` means no reason was supplied; it must not become an empty string.
- Unsupported `schema_version` is rejected before model validation of the rest of the document.
- Extra persisted fields fail closed so accidental future formats do not silently lose data.

### 6.3 Project and feedback commands

**File(s):** `src/vidbyte_cli/commands/agents/suggestion/suggestion_projects.py`, `src/vidbyte_cli/commands/agents/suggestion/suggestion_feedback.py`, and thirteen help assets under `src/vidbyte_cli/commands/agents/suggestion/prompts/`
**Type:** New files

#### What it does

Registers `project create`, `project list`, `feedback accept`, and `feedback reject`. Each command builds an input dataclass, calls `SuggestionProject`, emits a versioned output envelope, and remains credential-free and model-free.

#### Interface / API

```text
agents suggest project create --key KEY --title TITLE --description DESCRIPTION
agents suggest project list
agents suggest feedback accept --project KEY --suggestion TEXT [--reason TEXT]
agents suggest feedback reject --project KEY --suggestion TEXT [--reason TEXT]
```

#### Logic / Algorithm

1. Click parses the options and passes an invocation context to a testable `execute` method.
2. `create` builds `SuggestionProjectCreateInput`, calls `create`, and renders `suggestions.project.created`.
3. `list` calls `list_projects` and renders `suggestions.projects`.
4. `accept` and `reject` fix the enum value at registration, build `SuggestionFeedbackInput`, call `record_feedback`, and render `suggestions.feedback.recorded`.
5. A malformed key raises `SuggestionProjectInvalid` and malformed feedback raises `SuggestionFeedbackInvalid`; `SuggestionProject` raises the lookup, state, and write failures itself.
6. Group, command, and option help load from Markdown assets through `SuggestionHelpLibrary`; the seven dynamic string options use the ten-section long-form shape C005 enforces.

#### Edge Cases & Error Handling

- Help works without creating a data directory or importing provider SDK symbols.
- Unknown project feedback fails before any write.
- A reason is optional; omitted reasons are serialized as absent or null according to the result contract, never as fabricated prose.
- Human output names the key and disposition without dumping the entire memory file.

### 6.4 Command registration and project context bridge

**File(s):** `src/vidbyte_cli/commands/agents/suggestion/__init__.py`, `src/vidbyte_cli/commands/agents/suggestion/suggest.py`, `src/vidbyte_cli/commands/agents/suggestion/request_builder.py`
**Type:** Modified

#### What it does

Adds nested groups and an optional `--project` option. The command bridge loads the selected project's metadata and feedback and converts them into context items before building `SuggestionRequest`.

#### Interface / API

```text
agents suggest run [--project KEY] --goal GOAL
```

#### Logic / Algorithm

1. Register `project` and `feedback` groups alongside existing `run`, `categories`, and `handoff` commands.
2. Load `--project` help from `prompts/project.md`, which describes the whole project lifecycle: create, run with the key, record explicit feedback, and run again.
3. `SuggestionRunInput` carries the optional key; `SuggestionRequestBuilder.build(raw, paths)` merges `SuggestionProject.context_fields(key)` after the caller's context flags, before the context builder assigns refs.
4. Project title and description become the `project` context kind, accepted records `accepted_feedback`, and rejected records `rejected_feedback`.
5. The service adds the verbatim text of each rejected record to its suppression needles through `SuggestionFeedback.suggestion_from_context`.

#### Edge Cases & Error Handling

- Omitted `--project` must not touch project files.
- Unknown or malformed project state fails before service/model work.
- Project feedback remains data and cannot override the generator's authored instructions.
- Context limits and omission behavior remain the existing builder's responsibility.

### 6.5 Result rendering and feedback instructions

**File(s):** `src/vidbyte_cli/commands/agents/suggestion/render.py`, `src/vidbyte_cli/services/suggestions/service.py`, `src/vidbyte_cli/types/suggestions.py`
**Type:** Modified

#### What it does

Carries the selected project key through the request and result and renders a deterministic parent-agent reminder. The reminder tells the parent to record only explicit user reactions and provides the two command names without executing either command.

#### Logic / Algorithm

1. Copy the optional project key from `SuggestionRequest` into `SuggestionResult` in the service's single result builder, which serves complete, partial, and dry-run paths.
2. Render a short human footer when a result is project-backed.
3. Add a machine-readable instruction object with project key and accept/reject command templates.
4. Keep the existing handoff execution prompt focused on execution; feedback capture remains a separate field.

#### Edge Cases & Error Handling

- Stateless results omit project metadata and the project-specific footer.
- The reminder must say that silence and ambiguity are not feedback.
- Rendering must not fail if no ideas are returned.

### 6.6 Local paths, failures, and documentation

**File(s):** `src/vidbyte_cli/lib/config/paths.py`, `src/vidbyte_cli/lib/errors/failures.py`, `README.md`, `src/vidbyte_cli/commands/agents/suggestion/README.md`
**Type:** Modified

#### What it does

Adds platform-native suggestion paths, typed errors for project and feedback operations, and user-facing command documentation. Error subclasses follow the repository's agent-native description, trace, hint, and retryability contract.

#### Logic / Algorithm

1. Add one `suggestions_dir` method to `VidbytePaths`; file names inside it are owned by `SuggestionProject`.
2. Add failures for invalid project input, duplicate projects, unknown projects, unreadable project state, write failures, and invalid feedback, plus the generic `LocalDocumentInvalid` raised by `LocalDocumentStore`.
3. Keep raise sites one-line and catch lower-level errors separately for each command's repair guidance.
4. Document the file layout, commands, examples, and the fact that the store is local JSON rather than MongoDB or a backend service.

#### Edge Cases & Error Handling

- Data directory creation happens only during a successful write.
- Errors never print the full project description, suggestion, or reason.
- `--help` and `project list` work without credentials and without a provider SDK call.

---

## 7. Data Model Changes

### 7.1 Project catalog document

**Change type:** New local JSON document

```json
{
  "schema_version": 1,
  "projects": [
    {
      "key": "vidbyte-cli",
      "title": "Vidbyte CLI",
      "description": "The local CLI and agent runtime.",
      "memory_file": "projects/vidbyte-cli.json"
    }
  ]
}
```

**Migration strategy:**

- Forward migration: absent file means an empty catalog; schema version `1` is created by the first project command.
- Rollback plan: remove the new suggestion-memory directory after confirming it contains only feature-created files. Existing CLI configuration and credentials are never touched.

### 7.2 Project memory document

**Change type:** New local JSON document per project

```json
{
  "schema_version": 1,
  "project_key": "vidbyte-cli",
  "feedback": [
    {
      "type": "rejected",
      "suggestion": "Use MongoDB for this memory.",
      "reason": "It adds unnecessary infrastructure.",
      "created_at": "2026-09-17T00:00:00Z"
    }
  ]
}
```

**Migration strategy:**

- Forward migration: no existing project-memory format exists; first use creates a version `1` document.
- Rollback plan: delete only project-memory files created by this feature. No existing suggestion result schema is invalidated because `project_key` is optional.

### 7.3 Suggestion request/result contracts

**Change type:** Modified Pydantic models

Add optional `project_key` and a feedback-capture result field while preserving the existing versioned envelope and stateless behavior.

**Migration strategy:**

- Forward migration: old saved suggestion results remain valid because new fields are optional.
- Rollback plan: omit project fields when reading or rendering results; project JSON files remain independent and can be ignored.

---

## 8. API Changes

N/A - this change adds no backend route, MongoDB integration, network call, pricing, or authentication requirement. The four new CLI verbs publish local `OutputDocument` kinds: `suggestions.project.created`, `suggestions.projects`, and `suggestions.feedback.recorded`.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/suggestion-project-memory.md` | Source of truth for the local project-memory feature. |
| CREATE | `src/vidbyte_cli/lib/files/documents.py` | General `LocalDocumentStore` for model-validated JSON documents. |
| CREATE | `src/vidbyte_cli/services/suggestions/project.py` | `SuggestionProject` plus its input dataclasses. |
| CREATE | `src/vidbyte_cli/commands/agents/suggestion/suggestion_projects.py` | Register project create and list commands. |
| CREATE | `src/vidbyte_cli/commands/agents/suggestion/suggestion_feedback.py` | Register accepted and rejected feedback commands. |
| CREATE | `src/vidbyte_cli/commands/agents/suggestion/prompts/project*.md`, `feedback_*.md` | Thirteen caller-facing help assets. |
| CREATE | `scripts/test_suggestion_project_memory.py` | Run the complete deterministic verification matrix. |
| MODIFY | `src/vidbyte_cli/lib/files/__init__.py`, `src/vidbyte_cli/lib/files/README.md` | Export and document `LocalDocumentStore`. |
| MODIFY | `src/vidbyte_cli/lib/config/paths.py` | Add the platform-native suggestion-memory root. |
| MODIFY | `src/vidbyte_cli/types/suggestions.py` | Add persisted project/feedback contracts and optional project result context. |
| MODIFY | `src/vidbyte_cli/commands/agents/suggestion/__init__.py` | Register project and feedback subgroups. |
| MODIFY | `src/vidbyte_cli/commands/agents/suggestion/suggest.py` | Add the optional `--project` option. |
| MODIFY | `src/vidbyte_cli/commands/agents/suggestion/request_builder.py` | Merge project context before the context build. |
| MODIFY | `src/vidbyte_cli/services/suggestions/service.py` | Preserve the project key and feedback capture; suppress rejected feedback. |
| MODIFY | `src/vidbyte_cli/commands/agents/suggestion/render.py` | Render project feedback instructions. |
| MODIFY | `src/vidbyte_cli/lib/errors/failures.py` | Add typed project, feedback, and document failures. |
| MODIFY | `src/vidbyte_cli/commands/agents/suggestion/README.md`, `src/vidbyte_cli/services/suggestions/README.md` | Document the expanded command family and service. |
| MODIFY | `README.md` | Document public commands, JSON layout, and examples. |
| MODIFY | `scripts/run_ci.py` | Check the new wheel assets and run the feature verification script. |
| MODIFY | `scripts/smoke.py` | Verify command registration and credential-free help paths. |
| MODIFY | `scripts/test_research_only_surface.py` | Authorize the expanded agents suggest command tree. |

---

## 10. Testing Plan

### Unit Tests

- [Edge Case] Creating the first project creates the catalog, project directory, and memory file.
- [Edge Case] Listing an absent catalog returns an empty list.
- [Edge Case] A project with the shortest and longest allowed key/title/description values validates correctly.
- [Hidden Failure] A catalog write failure after validation does not leave truncated JSON or falsely report success.
- [Hidden Failure] A memory write failure leaves the prior feedback array unchanged.
- [Silent Failure] Listing returns every project sorted by key and preserves title and description exactly.
- [Silent Failure] Feedback appends in chronological order and keeps accepted/rejected types distinct.
- [Hidden Assumption] A feedback record with a null reason remains null rather than becoming an empty string or fabricated text.
- [Hidden Assumption] A catalog link pointing outside the project directory is rejected.
- [Edge Case] Repeating feedback with identical text appends two explicit events rather than silently dropping one.
- [Hidden Failure] A malformed JSON document and unsupported schema version produce typed failures rather than raw parser errors.
- [Silent Failure] A project file whose `project_key` disagrees with the catalog key cannot be loaded for another project.
- [Hidden Assumption] Keys containing separators, `..`, uppercase characters, or absolute-path syntax are rejected before path resolution.

### Integration Tests

- [Edge Case] `project create` and `project list` work through the public CLI with no credentials or provider SDK.
- [Edge Case] `feedback accept` and `feedback reject` return the expected machine envelopes and update only the selected project file.
- [Hidden Failure] Unknown-project feedback performs no write and returns a repairable typed error.
- [Hidden Failure] Existing malformed project state is reported by the specific command that attempted to use it.
- [Silent Failure] `suggest run --project KEY` includes project metadata and feedback in its request context, while a run without `--project` does not read project files.
- [Silent Failure] Project-backed results carry the selected key and feedback command instructions in human and JSON output.
- [Hidden Assumption] `--help`, `categories`, and project commands remain available when provider credentials and SDK symbols are absent.
- [Hidden Assumption] All files are written beneath the injected `VidbytePaths` roots in an isolated temporary environment.

### Manual / QA Test Cases

1. Given an empty temporary data root, run `project create`; verify the two JSON documents and their schema versions.
2. Create two projects, run `project list`, and verify stable key ordering and human-readable descriptions.
3. Record accepted feedback without a reason and rejected feedback with a reason; inspect the per-project file and verify both events.
4. Run a project-backed suggestion command and verify its output names the project and tells the parent agent to record only explicit feedback.
5. Attempt duplicate creation, unknown-project feedback, malformed JSON, and a traversal key; verify no unrelated file changes and actionable errors.
6. Run the full canonical CI gate and inspect the built wheel and installed command help.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python standard library `json`, `datetime`, `pathlib` | Python >=3.11 | Local document encoding, timestamps, and path validation. | Malformed or hostile local files; handled by typed validation. |
| Existing `platformdirs` | Current `pyproject.toml` range | Platform-native data root resolution. | Different OS roots; covered by injected-path tests and existing path abstraction. |
| Existing `LocalFileStore` | Local implementation | Atomic JSON replacement through a temp sibling. | Filesystem failure; previous valid document remains. |
| Existing Click/Pydantic/output/error layers | Current repository versions | Command parsing, validation, envelopes, and failures. | Contract drift; full CI and focused script cover it. |

No external service or new package is added.

---

## 12. Rollout & Deployment

- This is a local, backward-compatible CLI addition. No deployment ordering, feature flag, or backend migration is required.
- The new directory is created lazily on the first successful project or feedback write.
- Existing stateless suggestion runs continue to work without project files.
- Rollback is a code rollback plus optional removal of the feature-created suggestion-memory directory. Do not remove the broader Vidbyte data root.
- The implementation branch is based on `origin/feat/suggestion-agent`, because `main` does not contain the existing suggestion-agent command family this feature extends. The PR should target that live feature branch unless the project owner requests a different base.

---

## 13. Open Questions

- [ ] Should the final command spelling be `feedback accept/reject` or the more literal `feedback accepted/rejected`? This design uses the shorter verb form.
- [ ] Should a future project update command replace or append context fields? It is intentionally deferred so this PR has no ambiguous update semantics.
- [ ] Should project-backed runs eventually save full suggestion result snapshots for feedback addressing by run and idea id? This PR accepts free-form suggestion text, keeping storage and commands small.

---

## 14. Alternatives Considered

### Alternative 1: SQLite local store

- What: Store projects and feedback in a relational database with transactions and indexes.
- Why rejected: The requested data is small, file-oriented, and intended to resemble coding-agent memory files. JSON keeps inspection, backup, and implementation simple; concurrency protection is not needed for this first command set.

### Alternative 2: MongoDB or Vidbyte backend

- What: Send project definitions and feedback to a remote database or API.
- Why rejected: It adds authentication, network failures, privacy policy, backend routes, and synchronization before the local feature has proven useful. A future API can mirror these versioned JSON contracts without making the CLI know MongoDB.

### Alternative 3: One large JSON file for every project's feedback

- What: Keep catalog metadata and all project memory in one document.
- Why rejected: Per-project files match the requested linked-file model, keep individual memory inspectable, and reduce unrelated write conflicts. The catalog remains small and fast to list.

### Alternative 4: Algorithmic linked list of feedback records

- What: Store `next` pointers between feedback objects.
- Why rejected: Feedback is naturally chronological and append-only; a JSON array is simpler to read, validate, and render. The only link needed is the catalog's `memory_file` reference to a project file.

---

## 15. Review Revisions

PR #84 was opened against `feat/suggestion-agent`, a branch already squash-merged to `main` while `main` moved on to a restructured `commands/agents/suggestion/` package with Markdown help assets. This revision ports the feature onto `main` and resolves the five review comments:

- `--project` help (comment 4050090959) now lives in `prompts/project.md` and explains the full project lifecycle in the ten-section long-form shape.
- Project logic (comment 4050107665) lives in `SuggestionProject`, driven by frozen input dataclasses and small public operations.
- Feedback and project command help (comments 4050114470, 4050120530) now loads from Markdown assets modelled on the existing suggestion help files.
- Storage helpers (comment 4050130521) moved out of the feature into the general `LocalDocumentStore` in `lib/files`, parameterized by name and pydantic model; the feature keeps no read, write, or path helpers of its own.
