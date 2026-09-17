# Design Doc: Suggestion Project Memory and Feedback Commands

**Status:** Draft
**Author:** Codex
**Created:** 2026-09-17
**Last Updated:** 2026-09-17

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
- Reuse `VidbytePaths`, `AtomicFileWriter`, `ApplicationContext`, `OutputDocument`, typed failures, and the existing command registration and rendering patterns.
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

- `agents suggest` already owns local suggestion commands, structured output, context assembly, and deterministic handoffs. The command family is registered in `src/vidbyte_cli/commands/agents/__init__.py` and the service accepts typed `SuggestionRequest` values.
- The current suggestion design explicitly deferred durable project memory and database state. This feature is the small follow-up that introduces only the file state needed for project definitions and explicit feedback.
- The repository requires results on stdout, diagnostics on stderr, versioned machine envelopes, integer-returning reusable command entry points, and typed `CliError` subclasses for visible failures.
- `VidbytePaths` already selects platform-native config, data, cache, and state roots. `AtomicFileWriter` already creates private parent directories and replaces JSON files atomically.
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

Create one `SuggestionProjectStore` service under `services/suggestions` that owns path resolution, JSON validation, project creation, catalog listing, memory loading, and feedback appends. Extend `VidbytePaths` with three suggestion-memory paths and reuse `AtomicFileWriter` for every replacement. Commands remain thin: they parse and validate Click options, call the store, and render `OutputDocument` results through `ApplicationContext`.

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

### 6.1 Project persistence service

**File(s):** `src/vidbyte_cli/services/suggestions/project_store.py`
**Type:** New file

#### What it does

Owns the local JSON documents and keeps commands independent from filesystem details. It exposes project creation, catalog listing, project lookup, memory loading, and feedback append operations. It uses Pydantic models defined in `types/suggestions.py` so both disk documents and command results have one validation vocabulary.

#### Interface / API

```python
class SuggestionProjectStore:
    def create(self, key: str, title: str, description: str) -> SuggestionProject: ...
    def list(self) -> tuple[SuggestionProject, ...]: ...
    def get(self, key: str) -> SuggestionProject: ...
    def load_memory(self, key: str) -> SuggestionProjectMemory: ...
    def append_feedback(
        self, key: str, feedback_type: FeedbackType, suggestion: str, reason: str | None
    ) -> SuggestionFeedback: ...
```

#### Logic / Algorithm

1. Resolve the platform-native suggestion directory from `VidbytePaths` and create it only inside an authorized write operation.
2. For creation, normalize and validate the key, read the current catalog, reject duplicate keys, write the new project memory file, then atomically write the catalog entry.
3. If catalog replacement fails after the memory file is written, remove only the newly-created memory file when it did not exist before, or leave a valid orphan for the next repair command without touching other projects. The implementation should prefer validating all inputs before the first write.
4. For listing and lookup, treat an absent catalog as an empty catalog, but treat an existing malformed catalog as an error.
5. For feedback, load and validate the catalog and linked memory file before appending. Write a new validated memory document atomically.
6. Use the relative `memory_file` recorded in the catalog for lookup, but reject links that resolve outside the project directory.

#### Edge Cases & Error Handling

- Reject blank, uppercase, separator-containing, absolute, or traversal keys.
- Reject duplicate keys without modifying files.
- Reject malformed JSON, unsupported schema versions, missing linked memory files, and mismatched `project_key` values.
- Convert `OSError`, decoding, JSON, and Pydantic failures into command-specific typed failures at the command boundary.
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

**File(s):** `src/vidbyte_cli/commands/agents/suggestion_projects.py`, `src/vidbyte_cli/commands/agents/suggestion_feedback.py`
**Type:** New files

#### What it does

Registers `project create`, `project list`, `feedback accept`, and `feedback reject`. Each command calls `SuggestionProjectStore`, emits a versioned output envelope, and remains credential-free and model-free.

#### Interface / API

```text
agents suggest project create --key KEY --title TITLE --description DESCRIPTION
agents suggest project list
agents suggest feedback accept --project KEY --suggestion TEXT [--reason TEXT]
agents suggest feedback reject --project KEY --suggestion TEXT [--reason TEXT]
```

#### Logic / Algorithm

1. Click parses the options and passes an invocation context to a testable `execute` method.
2. `create` validates nonempty fields, calls `store.create`, and renders `suggestions.project.created`.
3. `list` calls `store.list`, sorts by key, and renders `suggestions.projects`.
4. `accept` and `reject` select the enum value in the command class, call `append_feedback`, and render `suggestions.feedback.recorded`.
5. Each command catches store failures and raises the typed failure whose hint names the exact project or feedback repair action.

#### Edge Cases & Error Handling

- Help works without creating a data directory or importing provider SDK symbols.
- Unknown project feedback fails before any write.
- A reason is optional; omitted reasons are serialized as absent or null according to the result contract, never as fabricated prose.
- Human output names the key and disposition without dumping the entire memory file.

### 6.4 Command registration and project context bridge

**File(s):** `src/vidbyte_cli/commands/agents/__init__.py`, `src/vidbyte_cli/commands/agents/suggest.py`
**Type:** Modified

#### What it does

Adds nested groups and an optional `--project` option. The command bridge loads the selected project's metadata and feedback and converts them into context items before building `SuggestionRequest`.

#### Interface / API

```text
agents suggest run [--project KEY] --goal GOAL
```

#### Logic / Algorithm

1. Register `project` and `feedback` groups alongside existing `run`, `categories`, and `handoff` commands.
2. Add a four-sentence `--project` help constant explaining that it is optional, local, and used to load prior feedback.
3. Before the existing `_fields`/`_files` context build, load the project when the option is present.
4. Add project title and description as a `project` context item, accepted records as `accepted-feedback`, and rejected records as `rejected-feedback`.
5. Preserve current `--input` mutual-exclusion behavior. If a structured input document later needs a project key, accept it only through the same validated request path rather than silently mixing sources.

#### Edge Cases & Error Handling

- Omitted `--project` must not touch project files.
- Unknown or malformed project state fails before service/model work.
- Project feedback remains data and cannot override the generator's authored instructions.
- Context limits and omission behavior remain the existing builder's responsibility.

### 6.5 Result rendering and feedback instructions

**File(s):** `src/vidbyte_cli/commands/agents/render.py`, `src/vidbyte_cli/services/suggestions/service.py`, `src/vidbyte_cli/types/suggestions.py`
**Type:** Modified

#### What it does

Carries the selected project key through the request and result and renders a deterministic parent-agent reminder. The reminder tells the parent to record only explicit user reactions and provides the two command names without executing either command.

#### Logic / Algorithm

1. Copy the optional project key from `SuggestionRequest` into `SuggestionResult` on complete, partial, and dry-run paths.
2. Render a short human footer when a result is project-backed.
3. Add a machine-readable instruction object with project key and accept/reject command templates.
4. Keep the existing handoff execution prompt focused on execution; feedback capture remains a separate field.

#### Edge Cases & Error Handling

- Stateless results omit project metadata and the project-specific footer.
- The reminder must say that silence and ambiguity are not feedback.
- Rendering must not fail if no ideas are returned.

### 6.6 Local paths, failures, and documentation

**File(s):** `src/vidbyte_cli/lib/config/paths.py`, `src/vidbyte_cli/lib/errors/failures.py`, `README.md`, `src/vidbyte_cli/commands/agents/README.md`
**Type:** Modified

#### What it does

Adds platform-native suggestion paths, typed errors for project and feedback operations, and user-facing command documentation. Error subclasses follow the repository's agent-native description, trace, hint, and retryability contract.

#### Logic / Algorithm

1. Add `suggestions_dir`, `suggestion_projects_file`, and `suggestion_project_memory_dir` methods to `VidbytePaths`.
2. Add failures for invalid project input, duplicate projects, unknown projects, unreadable project state, and invalid feedback.
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
| CREATE | `src/vidbyte_cli/services/suggestions/project_store.py` | Read, validate, and atomically write the catalog and per-project memory files. |
| CREATE | `src/vidbyte_cli/commands/agents/suggestion_projects.py` | Register project create and list commands. |
| CREATE | `src/vidbyte_cli/commands/agents/suggestion_feedback.py` | Register accepted and rejected feedback commands. |
| CREATE | `scripts/test_suggestion_project_memory.py` | Run the complete deterministic verification matrix. |
| MODIFY | `src/vidbyte_cli/lib/config/paths.py` | Add platform-native suggestion-memory paths. |
| MODIFY | `src/vidbyte_cli/types/suggestions.py` | Add persisted project/feedback contracts and optional project result context. |
| MODIFY | `src/vidbyte_cli/commands/agents/__init__.py` | Register project and feedback subgroups. |
| MODIFY | `src/vidbyte_cli/commands/agents/suggest.py` | Add optional `--project` loading and context bridging. |
| MODIFY | `src/vidbyte_cli/services/suggestions/service.py` | Preserve the project key and feedback-capture metadata in results. |
| MODIFY | `src/vidbyte_cli/commands/agents/render.py` | Render project feedback instructions. |
| MODIFY | `src/vidbyte_cli/lib/errors/failures.py` | Add typed project and feedback failures. |
| MODIFY | `src/vidbyte_cli/commands/agents/README.md` | Document the expanded agents command family. |
| MODIFY | `README.md` | Document public commands, JSON layout, and examples. |
| MODIFY | `scripts/run_ci.py` | Run the feature verification script in the canonical gate. |
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
| Existing `AtomicFileWriter` | Local implementation | Private, atomic JSON replacement. | Filesystem failure; previous valid document remains. |
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

