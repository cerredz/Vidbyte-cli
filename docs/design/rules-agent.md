# Design Doc: Rules Agent (`vidbyte-cli agents rules`)

**Status:** Draft
**Author:** Claude
**Created:** 2026-09-23
**Last Updated:** 2026-09-23

---

## 1. Overview

`vidbyte-cli agents rules` reads the prompts a person has typed into coding agents (Claude Code, Codex, Grok Build, OpenCode) from the transcripts those hosts already save on disk. It sends them in small paid batches to Vidbyte's hosted rules agent (`runtime.rules@1`, companion PR cerredz/Vidbyte#560). There, TypeSafe Jev picks out the prompts that state a lasting preference or correction, and a hosted writer agent turns them into standing rules. The CLI then collects every batch's rules into **one Markdown document**. The main command is `rules scan`. The user controls exactly what is read and spent through:
- host, date, project, session, and prompt limits,
- a hard spend cap,
- a wall-clock time limit,
- the batch size.

Every scan is stored locally, so an interrupted or capped scan continues with `rules resume <scan-id>`. The CLI supports no BYOK: all model usage is billed as metered usage to the caller's Vidbyte API wallet.

## 2. Goals & Non-Goals

### Goals
- A new `agents rules` command group with seven verbs:
  - `scan`,
  - `resume`,
  - `hosts` (which transcript sources exist),
  - `sessions` (which sessions a scope selects),
  - `limits` (defaults and hard caps),
  - `list` (past scans),
  - `show` (re-print one scan's rules).
- Readers for the four hosts' on-disk transcript formats that extract user-typed prompt text, with a stable `prompt_id` per prompt.
- Scope controls: `--host` (repeatable), `--since`, `--until`, `--project`, `--max-sessions`, `--max-prompts`.
- Limit controls: `--max-spend`, `--time-limit`, `--batch-size`, `--max-batch-cost`.
- Batched, idempotent, authenticated calls to `POST /api/x402/runtime/rules/batches`, with the spend cap enforced both locally (cumulative `charged_cents`) and server-side (`max_cost_cents` per batch).
- A durable local scan: a manifest plus per-batch records under the CLI data directory, and a resume that never re-buys a completed batch.
- One Markdown rules document per scan, written to the scan folder and optionally to `--out`, plus the standard human/JSON result envelopes.

### Non-Goals
- Filtering out injected or system messages, pairing prompts with the agent's previous action, removing duplicates, or merging rules across batches (the owner explicitly deferred these).
- Applying rules to CLAUDE.md or AGENTS.md, or installing live hooks.
- BYOK or local model execution.
- Any change to other command families.

## 3. Background & Context

- The product idea came from the 2026-09-23 conversation: backfill past transcripts, find repeated corrections, and return one rules document. The owner chose Jev for classification and a Vidbyte-hosted agent for writing, with usage charged and no BYOK.
- The CLI is a thin transport and presentation layer (see AGENTS.md). It already has what this needs:
  - the typed `ApiClient` with idempotency keys and retry,
  - the problem-to-`CliError` mapping,
  - the `OutputDocument` envelope, `LocalDocumentStore` for small JSON documents, and `VidbytePaths`.
- On-disk formats, checked on the owner's machine on 2026-09-23:
  - **Claude Code** `~/.claude/projects/<slug>/<session>.jsonl`: lines with `type: "user"`, `message.content` (a string or a block list), `timestamp`, `sessionId`, `cwd`, `isSidechain`, and `isMeta`.
  - **Codex** `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`: a `session_meta` payload (`id`, `cwd`, `timestamp`); human prompts as `event_msg` + `payload.type == "user_message"` + `payload.message`; otherwise `response_item` + `payload.role == "user"` with `input_text` blocks.
  - **Grok Build** `~/.grok/sessions/<encoded-cwd>/<session-id>/`: `chat_history.jsonl` lines `{type: "user", content: [{type: "text", text}], synthetic_reason?}`, plus `summary.json` (`created_at`).
  - **OpenCode** `~/.local/share/opencode/storage/`: `session/<project>/<ses>.json` (`directory`, `time.created`), `message/<ses>/<msg>.json` (`role`, `time.created`), and `part/<msg>/<prt>.json` (`type: "text"`, `text`).

## 4. Requirements

### Functional Requirements
1. `agents rules hosts` lists each supported host with its transcript root, whether the root exists, its session count, and its newest session time. It needs no credentials and costs nothing.
2. `agents rules sessions` applies the scope options and lists the selected sessions (host, session ID, project, start time, prompt count). It needs no credentials and costs nothing.
3. `agents rules limits` prints the default and maximum values for every scan limit and the backend's per-batch bounds. It needs no credentials.
4. `agents rules scan` runs these steps in order:
   1. Resolve scope and limits, and reject invalid input before any credential or network use.
   2. Read and select prompts: newest sessions first, stopping at `--max-sessions`, then at `--max-prompts`.
   3. Truncate each prompt to the backend's maximum characters.
   4. Split the prompts into batches of `--batch-size`.
   5. Write the manifest.
   6. Run the batches.
   7. Write the rules document.
   8. Print the result.
5. `--dry-run` stops after step 5. It reports the prompt and batch counts and the spend cap, and makes no request.
6. Before each batch the runner stops with a recorded `stop_reason` when either of these is true:
   - `time_limit`: the elapsed time is at or past `--time-limit`,
   - `spend_limit`: the remaining budget (`max_spend_cents - spent_cents`) is below the backend's admission floor (10¢).
7. Each batch sends `max_cost_cents = min(--max-batch-cost, remaining budget)`, and the idempotency key `rules-<scan_id>-<batch_index>`.
8. After each successful batch, the runner writes its record and updates the manifest (completed batches, spent cents, rule count) before the next batch starts.
9. A batch failure stops the scan and records the reason:
   - `credit_exhausted` for 402-class problems,
   - `batch_failed` for anything else.

   The manifest is saved, the rules document is still written from the batches that completed, and the command exits with a partial outcome, repeating the failure's repair hint.
10. `agents rules resume <scan-id>` reloads the manifest and re-reads transcripts with the stored scope. It skips completed batches, uses the stored limits (the spend cap counts what was already spent), and continues. Prompts whose IDs no longer resolve are left out of their batch, and a batch with none left is marked complete.
11. `agents rules list` prints stored scans, newest first: ID, created time, status, batches done/total, spent, and rule count.
12. `agents rules show <scan-id>` prints the stored rules document, or the JSON rules in `--json` mode.
13. Every result returns `scan_id`, the absolute `scan_dir`, `document_path`, and a paste-ready `resume` command whenever work remains.

### Non-Functional Requirements
- **Output contract:** results go to stdout. Progress goes to stderr through `OutputManager.diagnostic`.
- **Security:** prompt text is sent only in batch bodies. It never appears in progress lines, errors, or logs. The API key is used only through the existing client.
- **Performance:** batches run one at a time, which keeps the wallet lease and cost cap simple. Each request uses a longer timeout (180 seconds) than the default 30.
- **Resilience:** a completed batch is never paid for twice. If a crashed request is resent with the same idempotency key, the gatekeeper replays the stored response.

## 5. High-Level Design

```
agents rules scan ──► RulesScopeOptions / RulesLimitOptions (validate)
                  ──► TranscriptLibrary.prompts(scope)  (ClaudeTranscripts, CodexTranscripts, GrokTranscripts, OpenCodeTranscripts)
                  ──► RulesScanPlanner.plan(...) → RulesScanManifest ──► RulesScanStore (LocalDocumentStore under data/rules/<scan_id>/)
                  ──► RulesScanRunner.run(manifest, prompts) ──► RulesEndpoints.run_batch(request, key) ──► backend runtime.rules@1
                                                     └─► RulesBatchRecord per batch, manifest after each batch
                  ──► RulesDocumentRenderer.render(manifest, records) → rules.md (+ --out copy)
                  ──► RulesRenderer (OutputDocument + human text)
```

Commands parse input and render output. `services/rules/` owns transcript reading, planning, running, storing, and rendering the document. `lib/api/endpoints/rules.py` owns the one HTTP operation. `types/rules.py` owns the wire and local models. Storage uses `LocalDocumentStore` rooted at `VidbytePaths.rules_dir()`: one folder per scan, holding `manifest.json`, `batch-0000.json`, and so on, plus `rules.md`.

Key decisions:
- **The manifest stores prompt IDs, not prompt text.** Resume re-reads the transcripts, which don't change for past sessions. This keeps the manifest small and puts no prompt text in Vidbyte-owned state.
- **Batches run one at a time.** This keeps the spend cap exact and avoids contention on the backend's wallet lease.
- **The spend cap is enforced twice.** The CLI stops before a batch it can't afford, and the backend's `max_cost_cents` run cap stops a batch that tries to spend more than it may.

## 6. Detailed Design

### 6.1 Types
**File:** `src/vidbyte_cli/types/rules.py` (new)
- `RulesHost(StrEnum)`: `claude`, `codex`, `grok`, `opencode`.
- `RuleScope(StrEnum)`, and `RulesScanStatus(StrEnum)`: `planned`, `running`, `completed`, `stopped`.
- `RulesStopReason(StrEnum)`: `spend_limit`, `time_limit`, `credit_exhausted`, `batch_failed`.
- Wire models, mirroring the backend DTOs: `RulesPromptPayload`, `RulesBatchRequest`, `Rule`, `RulesBatchResult` (`extra="ignore"` on responses).
- Local models: `RulesScanScope`, `RulesScanLimits`, `RulesScanManifest`, `RulesBatchRecord`.

### 6.2 Transcript readers
**File:** `src/vidbyte_cli/services/rules/transcripts.py` (new)
```python
@dataclass(frozen=True) class TranscriptPrompt: host, session_id, prompt_id, text, project, created_at
@dataclass(frozen=True) class TranscriptSession: host, session_id, path, project, started_at, prompts: tuple[TranscriptPrompt, ...]
class TranscriptLibrary:
    def hosts(self) -> tuple[TranscriptSource, ...]
    def sessions(self, scope: RulesScanScope) -> list[TranscriptSession]
    def prompts(self, scope: RulesScanScope) -> list[TranscriptPrompt]
```
- There is one reader class per host. Each exposes `root()` and `read_sessions(since)`. Every reader pre-filters on file modification time (`mtime`) before parsing, skips unreadable or malformed lines, and never raises on a malformed file.
- `prompt_id = f"{host}:{session_id}:{ordinal}"`, where `ordinal` is the prompt's position within its session.
- `sessions()` filters by host, time window, and project (a path prefix compared case-insensitively on Windows), then sorts newest first and applies `max_sessions`. `prompts()` flattens those sessions, then applies `max_prompts`.

### 6.3 Store
**File:** `src/vidbyte_cli/services/rules/store.py` (new): `RulesScanStore(root)` wraps `LocalDocumentStore`. Its methods are `create_scan_id()`, `scan_dir(id)`, `save_manifest`, `load_manifest` (raises `RulesScanNotFound`), `save_batch`, `load_batches`, `write_document`, `read_document`, and `list_manifests()`. The feature's typed failures wrap any `LocalDocumentInvalid` or `LocalFile*` error.

### 6.4 Planner and runner
**File:** `src/vidbyte_cli/services/rules/runner.py` (new)
- `RulesScanPlanner.plan(scan_id, scope, limits, prompts) -> RulesScanManifest` splits prompts into batches of `limits.batch_size` and stores their ID lists.
- `RulesScanRunner.run(manifest, prompts_by_id) -> RulesScanManifest` repeats this loop for each pending batch:
  1. Check the time limit, then the spend limit.
  2. Build the request.
  3. Call `run_batch`.
  4. Save the batch record.
  5. Update and save the manifest.

  It catches a batch `CliError`, sets the stop reason (`credit_exhausted` when the error code is `CREDIT_EXHAUSTED`, otherwise `batch_failed`), saves, and returns. The caller re-raises nothing, because the result reports the stop instead.

### 6.5 Document
**File:** `src/vidbyte_cli/services/rules/document.py` (new): `RulesDocumentRenderer.render(manifest, records) -> str` produces:
- a heading,
- a scan summary (scope, prompts, batches, spend, status),
- rules grouped by scope (global, project, host), each with its title, instruction, "Applies when", rationale, and evidence prompt IDs,
- a footer telling the reader to resume if the scan stopped early.

### 6.6 Endpoint
**File:** `src/vidbyte_cli/lib/api/endpoints/rules.py` (new): `RulesEndpoints.run_batch(request, key) -> RulesBatchResult` is a POST to `/api/x402/runtime/rules/batches` with `ResponseShape.DIRECT` and an idempotency key. `ApplicationContext.rules_endpoints()` builds it on an `ApiClient` whose timeout is `max(config timeout, RULES_REQUEST_TIMEOUT_SECONDS)`.

### 6.7 Commands
**Files:** `src/vidbyte_cli/commands/agents/rules/{__init__,options,scan,resume,hosts,sessions,limits,history,show,render}.py` (new), and `commands/agents/__init__.py` (registers the group).
- `options.py` holds:
  - `RulesScopeOptions`: `--host` (multiple, choices), `--since` / `--until` (a duration such as `30d`/`12h`/`45m`, or an ISO date/time), `--project`, `--max-sessions`, `--max-prompts`,
  - `RulesLimitOptions`: `--max-spend` in dollars (e.g. `2.50`), `--time-limit` as a duration, `--batch-size` (1–20), `--max-batch-cost` in dollars,
  - `DurationParser`.
- `scan.py` adds `--out PATH` and `--dry-run`. `show` and `resume` take `SCAN_ID`.
- Every help string meets lint rule C001: at least four sentences averaging eight or more words.

### 6.8 Constants, paths, failures
- `src/vidbyte_cli/lib/constants/rules.py` (new): backend bounds (`RULES_BATCH_MAX_PROMPTS = 20`, `RULES_PROMPT_MAX_CHARS = 6000`, `RULES_ADMISSION_FLOOR_CENTS = 10`, `RULES_MAX_BATCH_COST_CENTS = 500`) and CLI defaults (`--since 30d`, `--max-spend 2.00`, `--batch-size 20`, `--max-batch-cost 0.50`, request timeout 180 s).
- `lib/config/paths.py`: `rules_dir()` returns `data_root / "rules"`.
- `lib/errors/failures.py` adds four failures:
  - `RulesInputInvalid` (usage),
  - `RulesNoPromptsFound` (usage),
  - `RulesScanNotFound` (usage),
  - `RulesScanStorageFailed` (operational).

  Each has a static, agent-native description and hint.

## 7. Data Model Changes

These are local files only (no server storage), under `<data_root>/rules/<scan_id>/`:
- `manifest.json` (`RulesScanManifest`): `schema_version`, `scan_id`, `created_at`, `updated_at`, `scope`, `limits`, `batches: list[list[str]]`, `completed_batches: list[int]`, `spent_cents`, `rule_count`, `status`, `stop_reason`, `document_path`.
- `batch-NNNN.json` (`RulesBatchRecord`): `batch_index`, `completed_at`, `result: RulesBatchResult`.
- `rules.md`: the rendered document.

Migration is N/A, because these are new files.

## 8. API Changes

N/A for this repo: it consumes the new `POST /api/x402/runtime/rules/batches` defined in cerredz/Vidbyte#560 (request/response in that doc's §8.1).

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `src/vidbyte_cli/types/rules.py` | Wire and local models |
| CREATE | `src/vidbyte_cli/lib/constants/rules.py` | Bounds and defaults |
| MODIFY | `src/vidbyte_cli/lib/config/paths.py` | `rules_dir()` |
| MODIFY | `src/vidbyte_cli/lib/errors/failures.py` | Four typed failures |
| CREATE | `src/vidbyte_cli/lib/api/endpoints/rules.py` | Batch endpoint |
| MODIFY | `src/vidbyte_cli/lib/runtime/context.py` | `rules_endpoints()` with long timeout |
| CREATE | `src/vidbyte_cli/services/rules/__init__.py` | Package |
| CREATE | `src/vidbyte_cli/services/rules/transcripts.py` | Host readers + library |
| CREATE | `src/vidbyte_cli/services/rules/store.py` | Scan storage |
| CREATE | `src/vidbyte_cli/services/rules/runner.py` | Planner + runner |
| CREATE | `src/vidbyte_cli/services/rules/document.py` | Markdown document |
| CREATE | `src/vidbyte_cli/commands/agents/rules/{__init__,options,scan,sources,history,execution,render}.py` | Seven verbs + options + shared execution + renderer |
| MODIFY | `scripts/test_research_only_surface.py` | Pin the new `agents rules` surface |
| MODIFY | `src/vidbyte_cli/commands/agents/__init__.py` | Register `rules` |
| MODIFY | `README.md` | Command reference entry |

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Vidbyte API | `POST /api/x402/runtime/rules/batches` (Vidbyte#560) | Jev + writer per batch | Must deploy before this CLI release |
| Host transcript formats | Claude Code, Codex, Grok Build, OpenCode (undocumented) | Prompt source | Formats drift; readers skip unknown lines |

## 11. Rollout & Deployment

- There is no flag. Deploy backend #560 (with `TYPESAFE_API_KEY` set) first, then merge this.
- It is not a breaking change: new commands only.
- Rollback: revert. Local scan folders are inert.

## 11a. Implementation notes (deviations from the first draft)

- **File layout.** The seven verbs live in fewer files: `scan.py` holds `scan` and `resume`, `sources.py` holds `hosts`, `sessions`, and `limits`, and `history.py` holds `list` and `show`. Both paid verbs share `execution.py` (`RulesScanExecution`), so run, publish, and report exist once.
- **Stopped scans exit 0.** Requirement 9 said a stopped scan would exit with a partial outcome. The CLI has no pattern for "print a result, then exit non-zero", because a raised `CliError` replaces the result document. A stopped scan therefore prints its full result (`status: stopped`, `stop_reason`, and `resume`) on stdout, adds a stderr warning with the continuation command, and exits 0. Agents branch on `data.status`.
- **Resume drops count caps on re-read.** It drops `max_sessions` and `max_prompts` when re-reading transcripts, so newer sessions can't push planned prompts out of the window. Planned prompts are then looked up by ID.
- **`--dry-run` stores a real plan and writes an empty document.** Running `resume` with the printed command executes that plan.
- **Surface contract.** `scripts/test_research_only_surface.py` pins `agents` to `{suggest, rules}` and pins the seven rules verbs.
- **Verification.**
  - `python scripts/run_ci.py` passes (exit 0). It needs a working `vidbyte` SDK on `PYTHONPATH`, because this machine's editable SDK install is stale, which is a known pre-existing issue.
  - The readers were run against real local transcripts on all four hosts.
  - A loopback stand-in for the batch route exercised the paid flow end to end: spend-limit stop, resume with a raised cap, `--out`, a 402 leading to `credit_exhausted`, and the dry-run plan executed through `resume`.

## 12. Open Questions

- [ ] Defaults: `--since 30d` and `--max-spend $2.00`?
- [ ] Should a first scan get free credit, as the growth hook discussed on 2026-09-23?

## 13. Alternatives Considered

### Alternative 1: Store prompt text in the manifest
- Why rejected: it grows the manifest without bound (past `LocalDocumentStore`'s 1 MB cap) and keeps a second copy of private text. Re-reading the transcripts is cheap and deterministic.

### Alternative 2: Parallel batches
- Why rejected: it makes the spend cap approximate and would collide on the backend's per-wallet gate lease (409s).

### Alternative 3: One `scan` command with flags for everything (`--list`, `--show`, `--resume`)
- Why rejected: the field guide says requests for several read verbs mean a command group. The owner also asked for these as subcommands.
