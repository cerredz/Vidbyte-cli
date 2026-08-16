# Design Doc: AGENTS.md Repository Map

**Status:** Draft
**Author:** Claude
**Created:** 2026-08-16
**Last Updated:** 2026-08-16

---

## 1. Overview

This change adds a root-level `AGENTS.md` to five Vidbyte repositories — `Vidbyte`, `Vidbyte-SDK`, `Vidbyte-cli`, `Vidbyte-Skills`, and `Vidbyte-Cookbook`. Each file is a **Map**: a lossy compression of something the repository already fully contains. The repository holds the whole truth at hundreds of thousands of tokens; the Map holds the routing information only. It answers one question — *where is everything, and what is it?* — so that an agent (or a human) reading it knows which directory to open next, without having to grep the tree first. Every `AGENTS.md` uses the identical section structure: repository title, a one-to-two paragraph description, and a File Index that walks the folder tree to depth 3 with three to four sentences of context per folder.

Because everything in the file is derivable from the repository itself, the Map is explicitly a *generated, regenerable* artifact. It does not need to be right in every detail; it needs to be right about where to look next, and it is expected to be regenerated whenever it drifts.

---

## 2. Goals & Non-Goals

### Goals
- Create one root-level `AGENTS.md` in each of the five repositories.
- Give every file the same three sections in the same order: repository title, repository description (1–2 paragraphs), and a `## File Index` section.
- Walk the folder tree recursively to depth 3 in the File Index, giving each folder 3–4 sentences describing what it is and what it is used for.
- Exclude skill-library contents from the recursion: `skills/` and `agent-skills/` directories are described as single entries and their interiors are not expanded.
- Ground every description in the repository's own tracked contents (`git ls-tree` against `origin/main`), its `README.md`, and its `llms.txt` where one exists — never in memory.
- Open one pull request per repository, each targeting `main`.

### Non-Goals
- **Not** a contributor guide, coding-standards document, build-command reference, or agent behavior policy. Those are separate classes of document; this file is the Map and nothing else.
- **Not** a replacement for `README.md`, `llms.txt`, `vidbyte-sdk/artifacts/file_index.md`, or `vidbyte-skills/artifacts/architecture.md`. The Map routes to them.
- **Not** a generator script. This PR produces the artifact; automating regeneration is a possible follow-up, not part of this change.
- **No** changes to source code, configuration, CI, packaging, or dependencies in any repository.
- **No** new tests. This is a documentation-only change.

---

## 3. Background & Context

Five repositories now make up the Vidbyte workspace, and work routinely crosses between them: the SDK supplies primitives, the backend executes harnesses on top of them, the CLI and Skills packages are the client surfaces, and the Cookbook demonstrates the whole stack. An agent dropped into any one of these repositories currently has no cheap way to orient. `Vidbyte` — by far the largest, at 3,447 tracked files — has **no root README at all**; its only tracked root files are `.gitignore` and `pr-body.md`. Orientation there today means either a full tree walk or prior knowledge.

Two repositories have already converged on this artifact independently. `vidbyte-sdk/artifacts/file_index.md` is a 504-line "compressed, code-free map of the repository" that explicitly positions itself as the structural companion to the code-heavy `llms.txt`. `vidbyte-skills/artifacts/architecture.md` plays a similar role. Both prove the format is useful; neither is at the root, neither is named the thing that agent harnesses actually look for, and neither exists in the other three repositories. `AGENTS.md` is the emerging cross-harness convention for exactly this file, and `vidbyte-skills` already generates AGENTS.md-compatible rule files for third-party tools — so the name is already understood inside this workspace.

The relevant prior constraint from the project field guide (`field-guide/vidbyte/skill-authoring.md`) is that repo-context documentation must state business intent, carry an important-files-and-folders subsection with per-folder descriptions, and be grounded in the repository's own docs rather than recalled from memory. That entry was established by PR #345/#346 review feedback. This design follows it directly: descriptions come from `git ls-tree`, `README.md`, and `llms.txt`.

**Constraints and dependencies:**
- Five separate GitHub remotes, so five branches and five pull requests.
- `Vidbyte` and `Vidbyte-Harnesses` are private; `Vidbyte-SDK`, `Vidbyte-cli`, `Vidbyte-Skills`, and `Vidbyte-Cookbook` are public.
- `Vidbyte-Skills` was not checked out locally and had to be cloned before it could be mapped.
- Three repositories run CI on every pull request with no path filters: `Vidbyte` (`next-app-lint.yml`), `Vidbyte-SDK` (`ci.yml`, `static-policy.yml`), `Vidbyte-cli` (`ci.yml`). `Vidbyte-Cookbook` and `Vidbyte-Skills` have no workflows.

---

## 4. Requirements

### Functional Requirements

1. A file named `AGENTS.md` exists at the repository root of each of the five repositories.
2. Each file opens with an H1 that is the repository's title.
3. Each file follows the H1 with a description of the repository, one to two paragraphs long, stating what the repository is and what it is for.
4. Each file contains a `## File Index` section.
5. The File Index enumerates folders recursively from the repository root to a maximum depth of 3.
6. Each enumerated folder is followed by 3–4 sentences describing what the folder is and what it is used for.
7. Skill-library directories (`skills/`, `agent-skills/`) receive a single entry each and are **not** expanded — the recursion does not descend into them.
8. Generated, vendored, and tool-cache directories are omitted: `.git/`, `node_modules/`, `.next/`, `__pycache__/`, `.venv/`, `dist/`, `build/`, `*.egg-info/`, and any `worktree-*` checkouts.
9. Root-level files that carry routing value are listed for each repository.
10. Every folder listed corresponds to a directory actually tracked on that repository's `origin/main`, and every description reflects that directory's real contents.
11. All five files use the identical section structure and heading hierarchy.
12. Each file states, in its own text, that it is a generated Map that may drift and is expected to be regenerated.
13. One pull request per repository, each targeting `main`, each carrying the design doc as its body.

### Non-Functional Requirements

- **Performance:** N/A — static Markdown, no runtime component.
- **Scalability:** The format must survive folder churn. Descriptions are written at the level of a folder's *responsibility*, not its file list, so adding or renaming a file inside a mapped folder does not invalidate the entry.
- **Security:** No credentials, tokens, internal hostnames, customer data, or private business logic. `Vidbyte-SDK`, `Vidbyte-cli`, `Vidbyte-Skills`, and `Vidbyte-Cookbook` are public repositories, so their Maps must describe only what is already public in that repository. `Vidbyte` is private and its Map stays in that private repository.
- **Observability:** N/A — no logging, metrics, or tracing surface.
- **Reliability:** Documentation-only; no failure modes at runtime. The one real risk is factual drift, addressed by the regeneration note required in FR-12.
- **Verifiability:** Every folder claim is checkable with a single `git ls-tree` invocation against `origin/main`.

---

## 5. High-Level Design

The work is a five-way fan-out of one authored artifact class. There is no shared code and no shared package between these repositories, so "the exact same context in each of them" is satisfied structurally rather than by literal file duplication: every `AGENTS.md` carries the same sections, in the same order, at the same depth, with the same per-folder sentence budget, while the *content* of each is that repository's own tree. A byte-identical file would be worthless — a Map of `vidbyte-sdk` does not route anyone through `vidbyte-cli`.

Content is derived, not recalled. For each repository the tree comes from `git ls-tree -r --name-only origin/main`, aggregated into depth-3 directory nodes with descendant file counts, then collapsed at `skills/` and `agent-skills/` boundaries. Folder descriptions are grounded by sampling the actual file names inside each depth-3 node and cross-reading the repository's `README.md` and `llms.txt`. This is the same discipline the field guide requires for skill repo-context sections, and the same one `vidbyte-sdk/artifacts/file_index.md` already follows.

The key design decision is **what the Map refuses to be**. It carries no build commands, no coding standards, no review checklist, no agent behavior rules. Those belong to different document classes with different lifecycles — a coding standard is an authored assertion that must be argued for, while a file index is a derivable fact that should be regenerated. Mixing them produces a file nobody dares regenerate, which is exactly how these documents rot. Keeping the Map purely derivable is what makes "regenerate it whenever it drifts" a safe operation.

The second decision is **depth 3, uniformly**. Depth 3 is where routing value peaks in these repositories: `backend/services/harnesses/` and `vidbyte/tools/builtins/` are the granularity at which someone actually decides where to look, while depth 4 collapses into file-level detail the repository already holds. Applying it uniformly makes the five files comparable. The consequence is that `Vidbyte`'s Map is substantially larger than the others — roughly 230 folder entries against 20–50 for the rest — because the repository is roughly 3.5× the size of the other four combined. This is called out in Section 12 as an open question rather than silently resolved by shrinking that one file below the specified format.

```
git ls-tree -r origin/main          (ground truth, per repo)
        |
        v
  depth-3 directory aggregation  --->  collapse skills/, agent-skills/
        |                               omit .git, node_modules, __pycache__, ...
        v
  per-folder file sampling  +  README.md  +  llms.txt
        |
        v
                 AGENTS.md  (title | description | file index)
        |
        +--> Vidbyte            branch feat/agents-md-repository-map --> PR
        +--> Vidbyte-SDK        branch feat/agents-md-repository-map --> PR
        +--> Vidbyte-cli        branch feat/agents-md-repository-map --> PR
        +--> Vidbyte-Skills     branch feat/agents-md-repository-map --> PR
        +--> Vidbyte-Cookbook   branch feat/agents-md-repository-map --> PR
```

---

## 6. Detailed Design

### 6.1 Shared AGENTS.md template

**File(s):** `AGENTS.md` (root) in all five repositories
**Type:** New file

#### What it does
Defines the single structure every one of the five files obeys. This is the "exact same context in each of them" requirement, made concrete.

#### Interface / API
```markdown
# <Repository Title>

<Paragraph 1: what this repository is, who it serves, what it produces.>
<Paragraph 2: how it relates to the other Vidbyte repositories, and its status.>

> This file is a Map: a compressed index of what this repository already
> contains in full. It is generated from the tree and is expected to drift.
> Regenerate it rather than patching it.

## File Index

Root files worth knowing: `<file>` — <what it is>. ...

### `<top-level-dir>/`
<3-4 sentences.>

#### `<top-level-dir>/<second-level>/`
<3-4 sentences.>

##### `<top-level-dir>/<second-level>/<third-level>/`
<3-4 sentences.>
```

#### Logic / Algorithm
1. H1 is the repository title.
2. One to two paragraphs of description follow immediately, before any other heading.
3. A short blockquote states the regeneration contract (FR-12).
4. `## File Index` opens the index; a root-files line precedes the folder walk.
5. Folders are emitted depth-first in path order, `###` for depth 1, `####` for depth 2, `#####` for depth 3.
6. Each folder heading is followed by 3–4 sentences and nothing else — no file listings, no code.
7. `skills/` and `agent-skills/` terminate the recursion at their own level.

#### Edge Cases & Error Handling
- **Folder with no obvious purpose from its name:** sample its files before writing; never guess.
- **Folder holding a large homogeneous family** (`next-app/constants/blog/`, 142 files): describe the family and its shape, not the members.
- **Folder that is mostly design notes rather than code** (`backend/services/narrative/`, `backend/services/pacer/`): say so plainly — that *is* the routing information.
- **Empty or near-empty folder:** still listed, with its emptiness stated, so a reader does not go looking for substance that is not there.
- **Repository with no root README** (`Vidbyte`): description is synthesized from `next-app/public/llms.txt`, which carries the product background, plus the tracked tree.

---

### 6.2 Vidbyte — `AGENTS.md`

**File(s):** `AGENTS.md`
**Type:** New file

#### What it does
Maps the private full-stack product repository: a FastAPI backend and a Next.js frontend, plus a large local skill library.

#### Logic / Algorithm
1. Description drawn from `next-app/public/llms.txt` (mission, learning-velocity framing) and `next-app/README.md` (stack: Next.js, NextAuth, MongoDB Atlas, Stripe).
2. Depth-1 walk: `.github/`, `backend/`, `docs/`, `next-app/`, `scripts/`, `skills/`.
3. `backend/` expands to `database/`, `docs/`, `lib/`, `middleware/`, `orchestrators/`, `prompts/`, `provider/`, `routes/`, `scripts/`, `services/`, `tests/`, `types/`, `utils/`, then their depth-3 children.
4. `next-app/` expands to `app/`, `components/`, `config/`, `constants/`, `content/`, `database/`, `hooks/`, `lib/`, `public/`, `scripts/`, `security/`, `seo/`, `server/`, `store/`, `tests/`, `utils/`, `widgets/`, then their depth-3 children.
5. `skills/` (774 files) gets one entry and is not expanded, per FR-7.

#### Edge Cases & Error Handling
- Root has no README; the description must be synthesized rather than quoted.
- `pr-body.md` is a tracked root file that is scratch, not structure — listed as such so nobody mistakes it for a contract.
- `backend/services/sandbox/` (174 files) and `next-app/utils/integrations/` (162 files) are the two largest leaf nodes; both get a family-level description.

---

### 6.3 Vidbyte-SDK — `AGENTS.md`

**File(s):** `AGENTS.md`
**Type:** New file

#### What it does
Maps the public Python SDK package — the primitives layer the rest of the workspace builds on.

#### Logic / Algorithm
1. Description drawn from `README.md` ("agent engineering platform… the Python package surface") and `llms.txt`.
2. Depth-1 walk: `.github/`, `.semgrep/`, `artifacts/`, `docs/`, `scripts/`, `skills/`, `tests/`, `vidbyte/`.
3. `vidbyte/` expands to its 20 subpackages; the README's Layer Guide is the authority for each one's role.
4. Depth-3 children of `vidbyte/` (for example `lib/dataclasses/`, `tools/builtins/`, `agents/runtimes/`) are described from sampled contents.
5. The `artifacts/` entry points explicitly at `artifacts/file_index.md` as the deeper structural index.

#### Edge Cases & Error Handling
- `vidbyte/shared/` is a reserved namespace with no stable public symbols — stated, not padded.
- `vidbyte/skills/` is package-internal and small (3 files); distinct from the repo-root `skills/` (45 files). Both are listed, and the difference is called out, because the name collision is a live source of confusion.

---

### 6.4 Vidbyte-cli — `AGENTS.md`

**File(s):** `AGENTS.md`
**Type:** New file

#### What it does
Maps the public research CLI — the thinnest of the five repositories, at 94 tracked files.

#### Logic / Algorithm
1. Description drawn from `README.md`: authenticate, run Vidbyte research threads, manage configuration; research executes on the backend and the CLI admits runs and reads durable status.
2. Depth-1 walk: `.github/`, `docs/`, `scripts/`, `src/`.
3. `src/` expands to `vidbyte_cli/`, which expands to `commands/`, `lib/`, `types/` — the depth-3 boundary.
4. The `scripts/` entry names `run_ci.py` as the single verification entry point, matching the comment at the head of `.github/workflows/ci.yml`.

#### Edge Cases & Error Handling
- Depth 3 stops at `src/vidbyte_cli/commands/`; the per-command packages beneath it are depth 4 and out of scope by FR-5.

---

### 6.5 Vidbyte-Skills — `AGENTS.md`

**File(s):** `AGENTS.md`
**Type:** New file

#### What it does
Maps the public skills repository and npm installer — a hybrid Node installer plus Python CLI, with an 894-file skill library.

#### Logic / Algorithm
1. Description drawn from `README.md` and `llms.txt`: source of truth for installable skills, plus the `vidbyte` command skills use to submit authenticated artifacts.
2. Depth-1 walk: `agent-skills/`, `artifacts/`, `bin/`, `cli/`, `docs/`, `lib/`, `packages/`, `scripts/`, `skills/`.
3. `skills/` (894 files) and `agent-skills/` get one entry each and are not expanded, per FR-7.
4. `cli/` expands to `auth/`, `commands/`, `constants/`, `dataclasses/`, `helpers/`; `packages/` expands to `learning/` and `reasoning/` and their `bin/` children.

#### Edge Cases & Error Handling
- This repository has both a Node surface (`lib/`, `bin/`) and a Python surface (`cli/`). The Map must make that split obvious at depth 1, since it is the single most confusing thing about the repository.
- FR-7's exclusion is load-bearing here: `skills/` is 87% of the tracked files.

---

### 6.6 Vidbyte-Cookbook — `AGENTS.md`

**File(s):** `AGENTS.md`
**Type:** New file

#### What it does
Maps the public examples repository — 22 tracked files, one notebook per rebuilt system.

#### Logic / Algorithm
1. Description drawn from `README.md`: runnable examples for both the Vidbyte API and the Vidbyte SDK, with the SDK examples following a single premise — rebuild a well-known production agentic system, minimal, in one walkthrough notebook.
2. Depth-1 walk: `.claude/`, `api/`, `docs/`, `scripts/`, `sdk/`.
3. `sdk/` expands to its eight example folders, each of which is a depth-2 leaf holding one notebook.
4. The three harness examples (`rlm/`, `rl-env-generator/`, `graph-engineering/`) are identified as such, since they pin a git commit of the SDK rather than the PyPI release.

#### Edge Cases & Error Handling
- Each `sdk/<name>/` folder holds exactly one notebook, so its description is about the *system being rebuilt*, not the folder mechanics.
- `.claude/skills` is tracked; it gets one entry and is not expanded, consistent with FR-7.

---

## 7. Data Model Changes

N/A — no schema, collection, table, or persisted type is created, modified, or deleted. This change adds Markdown files only.

---

## 8. API Changes

N/A — no HTTP route, CLI command, MCP tool, or exported Python/JavaScript symbol is added, modified, or deprecated.

---

## 9. File Change Manifest

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `Vidbyte:AGENTS.md` | Root Map for the full-stack product repository |
| CREATE | `Vidbyte:docs/design/agents-md-repository-map.md` | This design doc |
| CREATE | `Vidbyte-SDK:AGENTS.md` | Root Map for the Python SDK |
| CREATE | `Vidbyte-SDK:docs/design/agents-md-repository-map.md` | This design doc |
| CREATE | `Vidbyte-cli:AGENTS.md` | Root Map for the research CLI |
| CREATE | `Vidbyte-cli:docs/design/agents-md-repository-map.md` | This design doc |
| CREATE | `Vidbyte-Skills:AGENTS.md` | Root Map for the skills repository and installer |
| CREATE | `Vidbyte-Skills:docs/design/agents-md-repository-map.md` | This design doc |
| CREATE | `Vidbyte-Cookbook:AGENTS.md` | Root Map for the examples repository |
| CREATE | `Vidbyte-Cookbook:docs/design/agents-md-repository-map.md` | This design doc |

No file is modified. No file is deleted. Ten created files across five repositories.

---

## 10. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| `git` | local | `ls-tree` against `origin/main` is the ground truth for every folder claim | None |
| `gh` | local, authenticated | Opens one pull request per repository | Auth or permission failure on the private `Vidbyte` repo |
| GitHub Actions | `Vidbyte`, `Vidbyte-SDK`, `Vidbyte-cli` | CI runs on every PR with no path filters | Pre-existing red CI on `main` would surface here despite a docs-only diff |

No new runtime dependency, package, or external service is introduced in any repository.

---

## 11. Rollout & Deployment

- **Feature flags:** None. Adding a Markdown file has no runtime effect.
- **Breaking changes:** None. No repository has an existing root `AGENTS.md` or `CLAUDE.md`, verified by `git ls-tree` against `origin/main` in all five — so there is nothing to overwrite and no migration path required.
- **Deployment order:** None required; the five pull requests are fully independent and can merge in any order or not at all.
- **Per-repository CI:** `Vidbyte` runs `next-app-lint.yml` (ESLint over `next-app/`); `Vidbyte-SDK` runs `ci.yml` (source + package stages over a Python matrix) and `static-policy.yml` (Semgrep); `Vidbyte-cli` runs `ci.yml` (`scripts/run_ci.py` across an OS/Python matrix). None of the three has path filters, so all run on a docs-only diff and all are expected to pass unchanged. `Vidbyte-Cookbook` and `Vidbyte-Skills` have no workflows.
- **Canonical local gate:** `Vidbyte-SDK` — `python -m pip install -e ".[dev]"` then `python scripts/run_ci.py`. `Vidbyte-cli` — `python scripts/run_ci.py`. `Vidbyte` — `npm run lint` and `npm run build` from `next-app/`; note that PR checks never build, so the local build is the only real gate.
- **Rollback:** Revert the merge commit, or close the pull request. There is no state to unwind.

---

## 12. Open Questions

- [ ] **Vidbyte's Map is much larger than 3k tokens.** The stated form is a ~3k-token routing artifact, but depth 3 with 3–4 sentences per folder yields roughly 230 entries for `Vidbyte` — an order of magnitude over that budget — because the repository is roughly 3.5× the size of the other four combined. This design follows the explicit format (depth 3, 3–4 sentences) rather than the token budget, on the grounds that the format is the more specific instruction. If the budget matters more, the fix is to drop `Vidbyte`'s depth-3 entries to one line each, which lands it near the other four. **Flagged for the reviewer; not resolved unilaterally.**
- [ ] Should regeneration be automated — a script plus a CI check that fails when the tree drifts from the Map? Deliberately out of scope here, but it is the natural second PR, and it is what makes "regenerate whenever it drifts" real rather than aspirational.
- [ ] Should `vidbyte-sdk/artifacts/file_index.md` and `vidbyte-skills/artifacts/architecture.md` be folded into their `AGENTS.md` files, or stay as the deeper tier the Map points to? This design keeps them separate and links to them, since `file_index.md` is 504 lines and serves a different reading depth.
- [ ] Should `Vidbyte-Harnesses` and `Vidbyte-Evals` get the same treatment? Both are in the workspace but neither was named in the request, so both are out of scope here.

---

## 13. Alternatives Considered

### Alternative 1: One byte-identical AGENTS.md in all five repositories
- **What:** Take "fill them with the exact same context in each of them" literally — write one file describing the whole workspace and commit that same file everywhere.
- **Why rejected:** It contradicts the form. A Map is defined as a compression of *the repository it lives in*; a file that maps all five routes nobody through any one of them, and every entry would be wrong four times out of five. The reading that survives contact with the stated purpose is that the *structure* is identical and the *content* is per-repository, which is what Section 5 implements.

### Alternative 2: `CLAUDE.md` instead of `AGENTS.md`
- **What:** Use the Claude Code-specific filename.
- **Why rejected:** The request said `agents.md`, and `AGENTS.md` is the cross-harness convention that all agent tooling reads. `vidbyte-skills` already generates AGENTS.md-compatible rule files for third-party tools, so the name is established in this workspace. `CLAUDE.md` would also imply behavior instructions, which Section 2 explicitly excludes.

### Alternative 3: Generate the files with a committed script in this PR
- **What:** Write a `scripts/generate_agents_md.py` per repository and commit the generated output alongside it.
- **Why rejected:** Description quality is the whole value of the artifact, and 3–4 sentences of *why a folder exists* is not mechanically derivable from a file listing. A generator would emit accurate structure with useless prose. Structure is derived mechanically here (`git ls-tree`) and prose is authored against sampled contents. Automating the drift check is recorded in Section 12 as a follow-up.

### Alternative 4: Depth 2 instead of depth 3
- **What:** Stop the recursion one level earlier, keeping every file near the 3k-token target.
- **Why rejected:** Depth 3 is where routing value actually sits in these repositories — `backend/services/harnesses/`, `vidbyte/tools/builtins/`, `next-app/server/research/`. Stopping at depth 2 would leave `backend/services/` as a single entry covering 411 files, which routes nobody anywhere. The request also specified depth 3 explicitly.

### Alternative 5: Put the Map in `docs/` rather than at the root
- **What:** Follow the existing precedent of `vidbyte-sdk/artifacts/file_index.md`.
- **Why rejected:** The request specified root level, and root is where agent harnesses auto-discover `AGENTS.md`. A Map that has to be found before it can route is a Map that does not get read.

---

END OF DESIGN DOC
