# Design Doc: Suggestion Agent Category Taxonomy

**Status:** Draft
**Author:** Codex
**Created:** 2026-09-15
**Last Updated:** 2026-09-15

---

## 1. Overview

Revise the `vidbyte-cli agents suggest` category taxonomy by removing `stop_or_defer`, `risk_prevention`, `verification`, and `cross_domain`, then adding `long_term_suggestions`. The new category will guide the agent toward durable initiatives on two explicit planning horizons: concrete capability building over 3-6 months and larger directions over 2 years or more. The registry, CLI validation, category listing, prompt context, deterministic service path, documentation, and verification checks will all expose the same 14-category vocabulary.

---

## 2. Goals & Non-Goals

### Goals

- Remove the four requested category identifiers from registry validation and category listing.
- Add the exact CLI identifier `long_term_suggestions` using the repository's existing snake_case convention.
- Define long-term guidance that distinguishes 3-6 month capability building from 2 year+ strategic directions and connects them with milestones.
- Keep category selection strict: removed identifiers fail before any model/provider work, while the new identifier is accepted anywhere an existing category is accepted.
- Store every retained category's model-facing definition in a packaged Markdown asset with purpose, intent, timing, checks, and cautions.
- Keep the existing output envelope, category command shape, service workflow, and horizon enum unchanged.
- Update documentation and deterministic verification so source and wheel installations expose the same taxonomy.

### Non-Goals

- Do not add a new backend route, pricing path, database record, migration, scheduler, or proactive suggestion trigger.
- Do not add a new `SuggestionHorizon` enum value or change the meaning of `now`, `next`, `later`, or `any`; the new category supplies its more precise 3-6 month and 2 year+ guidance.
- Do not preserve aliases for removed category identifiers. A caller must discover the current closed set through `agents suggest categories`.
- Do not redesign generator, critic, handoff, context, or result schemas beyond the category registry and prompt asset mapping they already consume.
- Do not carry forward the unrelated category expansions present on other unmerged branches.

---

## 3. Background & Context

- The current `SuggestionCategories` registry contains 17 identifiers in `src/vidbyte_cli/services/suggestions/categories.py`.
- `suggest.py` validates repeated `--category` values through that registry before constructing the request; the service then cycles through the accepted identifiers when it creates deterministic candidates.
- `suggestion_categories.py` renders the same registry as the credential-free `agents suggest categories` command, so changing the registry changes both human and JSON output.
- `SuggestionCategories.prompt_section()` currently renders descriptions and guidance from Python. The Vidbyte field guide requires reusable model-facing vocabularies to live in packaged Markdown assets, with Python loading and validating those assets.
- `pyproject.toml` already packages the top-level suggestion prompt files but does not yet package a category subdirectory. The wheel gate checks selected prompt assets, so the category assets need an explicit package-data and wheel check.
- The current checkout is `feat/suggestion-agent`; `main` does not yet contain the suggestion-agent implementation. The implementation worktree must therefore branch from this feature branch to preserve the requested agent, then target this branch as a stacked change.

---

## 4. Requirements

### Functional Requirements

1. The registry must contain exactly these 14 identifiers, in stable order: `continuation`, `prerequisite`, `completion`, `bottleneck`, `experiment`, `investigation`, `alternative`, `simplification`, `leverage`, `strategy`, `long_term_suggestions`, `adjacent_opportunity`, `preparation`, and `coordination`.
2. `stop_or_defer`, `risk_prevention`, `verification`, and `cross_domain` must not be recognized by `SuggestionCategories.is_known()` or `require_known()`.
3. `--category stop_or_defer`, `--category risk_prevention`, `--category verification`, and `--category cross_domain` must fail with the existing typed category error before service/model work begins.
4. `--category long_term_suggestions` must pass validation, and a run restricted to it must produce ideas whose `primary_category` is `long_term_suggestions`.
5. `agents suggest categories` must list the 14 current identifiers in registry order in human output and in the `suggestions.categories` JSON envelope.
6. The long-term category description and packaged prompt must explicitly cover both a 3-6 month horizon and a 2 year+ horizon, including milestones that connect the two.
7. `prompt_section()` must render exactly the selected retained category assets in the requested order and must not render assets for removed categories.
8. Every retained category must map one-to-one to a packaged Markdown file containing explicit purpose, intent, timing, checks, and cautions. Missing assets must fail the verification suite rather than silently falling back to Python prose.
9. The result schema version, `SuggestionHorizon` values, category command kind, and existing count/selection semantics must remain unchanged.
10. The package wheel must include every category asset, and the canonical CI gate must verify that source and installed-package category listings remain usable.

### Non-Functional Requirements

- Category validation remains local, deterministic, exact-match, and credential-free.
- Category list and dry-run paths must not import or call the provider SDK.
- Prompt assets must be UTF-8 Markdown loaded with `importlib.resources`, so the installed wheel does not depend on the caller's working directory.
- Existing stdout/stderr and JSON envelope contracts must remain intact.
- No new third-party dependency is introduced.
- Verification must use the repository's canonical `python scripts/run_ci.py` gate after focused checks.

---

## 5. High-Level Design

Replace the four removed entries in the registry and insert `long_term_suggestions` after `strategy`, preserving the surrounding stable order. Each retained entry will carry its public title/summary and the name of one category Markdown asset. The category command will continue to expose the short summary, while `prompt_section()` will load the full authored asset for model-facing context.

Extend the existing prompt loader with a category-asset read path and add the category directory to setuptools package data. The deterministic suggestion service already consumes category IDs through the registry, so no separate service branching is needed: restricting a run to the new ID automatically produces new-category ideas, and removed IDs are rejected at the command boundary.

Update the README, suggestion service notes, deterministic test script, and wheel verification. The test script will assert the exact registry, rejection of every removed identifier, acceptance and output of the new identifier, long-term wording, selected-prompt ordering, and category asset availability. The implementation will run in an isolated worktree based on `feat/suggestion-agent` because the requested agent is not present on `main` yet.

```text
[category registry]
       | exact validation + stable order
       v
[CLI list / --category] ----> [deterministic service selection]
       |
       +----> [packaged category Markdown] ----> [model-facing prompt context]
```

---

## 6. Detailed Design

### 6.1 Category Registry

**File(s):** `src/vidbyte_cli/services/suggestions/categories.py`
**Type:** Modified

#### What it does

Owns the closed set of 14 category identifiers, their caller-facing summaries, their stable order, and their one-to-one prompt asset names. It remains the single validation source for the CLI and service.

#### Interface / API

```python
class CategoryDefinition:
    category_id: str
    title: str
    summary: str
    prompt_name: str

class SuggestionCategories:
    def ids(self) -> tuple[str, ...]: ...
    def definitions(self) -> tuple[CategoryDefinition, ...]: ...
    def is_known(self, category_id: str) -> bool: ...
    def require_known(self, category_ids: tuple[str, ...]) -> tuple[str, ...]: ...
    def prompt_section(self, category_ids: tuple[str, ...] | None = None) -> str: ...
```

#### Logic / Algorithm

1. Remove the four requested definitions from the ordered tuple.
2. Add `long_term_suggestions` after `strategy`, with a summary that names both requested horizons.
3. Add a prompt asset name to every retained definition and keep the existing exact-match validation behavior.
4. Preserve the category registry schema version at `1` because the envelope shape is unchanged; the `categories` command remains the discovery mechanism for the revised vocabulary.
5. Resolve selected definitions to category assets through `SuggestionPrompts` and concatenate them in selected order.

#### Edge Cases & Error Handling

- An empty category selection still means the complete revised registry.
- A removed identifier is unknown, not silently remapped to a neighboring category.
- A duplicate selected identifier keeps the existing behavior unless existing validation changes independently; this feature does not add aliases or normalization.
- A missing category asset is a packaging/verification failure and must not fall back to stale Python guidance.

### 6.2 Packaged Category Prompt Assets

**File(s):** `src/vidbyte_cli/services/suggestions/prompts/categories/*.md` (14 new files)
**Type:** New files

#### What it does

Provides the model-facing definition for each retained category. Each file will explain the category's purpose, intent, timing, checks, and cautions, with the `long_term_suggestions.md` asset explicitly separating 3-6 month capability building from 2 year+ strategic direction.

#### Interface / API

```text
# <Category title>

## Purpose
<category boundary>

## Intent
<what a useful suggestion should accomplish>

## Timing
<when the category is appropriate>

## Checks
- <observable quality check>

## Cautions
- <misuse or neighboring-category boundary>
```

#### Logic / Algorithm

1. Create one file for each retained registry identifier, using the identifier as the filename.
2. Keep the asset title and summary aligned with the registry entry.
3. Make timing and cautions specific enough to distinguish adjacent categories.
4. In `long_term_suggestions.md`, require a 3-6 month milestone path, a 2 year+ direction, and an explicit connection between them.

#### Edge Cases & Error Handling

- Removed category assets are not created, so they cannot be loaded through the revised registry.
- All files must be packaged; source-only success is insufficient.
- Asset text is guidance, not executable instruction or authority, and must not grant permission to perform work.

### 6.3 Prompt Loader and Package Data

**File(s):** `src/vidbyte_cli/services/suggestions/prompts/library.py`, `pyproject.toml`
**Type:** Modified

#### What it does

Loads category Markdown through the same wheel-safe resource mechanism already used for generator and critic prompts, and declares the nested category directory as package data.

#### Interface / API

```python
class SuggestionPrompts:
    def category_prompt(self, name: str) -> str: ...
```

#### Logic / Algorithm

1. Add a category-aware read path that resolves `prompts/categories/<name>.md` with `importlib.resources`.
2. Cache loaded text using the existing per-run cache.
3. Add `services/suggestions/prompts/categories/*.md` to the `vidbyte_cli` package-data list.
4. Leave generator and critic prompt names and literal placeholder rendering unchanged.

#### Edge Cases & Error Handling

- The loader must work when the current working directory is outside the checkout.
- Unknown or removed category names are never passed to the loader because registry validation happens first.
- A missing asset raises the normal resource error; the verification suite reports it instead of accepting a fallback.

### 6.4 CLI and Documentation Surface

**File(s):** `README.md`, `src/vidbyte_cli/services/suggestions/README.md`
**Type:** Modified

#### What it does

Keeps caller-facing documentation synchronized with the revised category count and explains that the category command is the authoritative discovery path.

#### Interface / API

```text
vidbyte-cli agents suggest categories
vidbyte-cli agents suggest run --goal "..." --category long_term_suggestions
```

#### Logic / Algorithm

1. Change the README's category count from 17 to 14.
2. Document the new identifier and its two planning horizons in the suggestion-service notes.
3. Do not change Click option names, output kinds, or command registration.

#### Edge Cases & Error Handling

- Documentation must not advertise any removed identifier.
- Help and category listing must remain usable without credentials.
- The README describes the public contract; detailed category guidance remains in packaged assets.

### 6.5 Verification and Wheel Checks

**File(s):** `scripts/test_suggestions.py`, `scripts/run_ci.py`
**Type:** Modified

#### What it does

Proves that taxonomy changes are enforced at the registry, command, service, prompt, and installed-wheel boundaries.

#### Interface / API

```text
python scripts/test_suggestions.py
python scripts/run_ci.py
```

#### Logic / Algorithm

1. Assert the exact 14-ID tuple and the four removed IDs' rejection.
2. Run the service and CLI with `long_term_suggestions` and assert the resulting primary category.
3. Assert the long-term summary and packaged asset mention both requested horizons.
4. Assert selected prompt rendering includes only selected categories and preserves order.
5. Assert JSON category listing has 14 entries and no removed IDs.
6. Extend the wheel check to require all 14 category Markdown paths in the built archive.

#### Edge Cases & Error Handling

- A removed category must fail with a non-zero CLI status before any provider work.
- A missing asset or incomplete wheel must fail the verification gate.
- A category list with no credentials must still return a valid envelope.
- The test script must print labeled `PASS`/`FAIL` results and exit non-zero on any failure.

---

## 7. Data Model Changes

N/A - No database, persistence, migration, or Pydantic field-shape change is required. The `primary_category` field is already a bounded string, and the result/category envelope shapes remain version 1. The vocabulary is intentionally discovered through the category registry rather than encoded as a persisted enum.

---

## 8. API Changes

N/A - No HTTP endpoint or backend API changes are introduced. The local `agents suggest categories` command changes its data values from the old 17-item vocabulary to the revised 14-item vocabulary, while retaining its existing `suggestions.categories` kind and envelope shape.

---

## 9. File Change Manifest

Complete list of every file that will be created, modified, or deleted:

| Action | File Path | Reason |
|--------|-----------|--------|
| CREATE | `docs/design/suggestion-agent-category-taxonomy.md` | Record the taxonomy revision and implementation contract. |
| CREATE | `src/vidbyte_cli/services/suggestions/prompts/categories/continuation.md` | Model-facing guidance for continuation suggestions. |
| CREATE | `src/vidbyte_cli/services/suggestions/prompts/categories/prerequisite.md` | Model-facing guidance for prerequisite suggestions. |
| CREATE | `src/vidbyte_cli/services/suggestions/prompts/categories/completion.md` | Model-facing guidance for completion suggestions. |
| CREATE | `src/vidbyte_cli/services/suggestions/prompts/categories/bottleneck.md` | Model-facing guidance for bottleneck suggestions. |
| CREATE | `src/vidbyte_cli/services/suggestions/prompts/categories/experiment.md` | Model-facing guidance for experiment suggestions. |
| CREATE | `src/vidbyte_cli/services/suggestions/prompts/categories/investigation.md` | Model-facing guidance for investigation suggestions. |
| CREATE | `src/vidbyte_cli/services/suggestions/prompts/categories/alternative.md` | Model-facing guidance for alternative-route suggestions. |
| CREATE | `src/vidbyte_cli/services/suggestions/prompts/categories/simplification.md` | Model-facing guidance for simplification suggestions. |
| CREATE | `src/vidbyte_cli/services/suggestions/prompts/categories/leverage.md` | Model-facing guidance for leverage suggestions. |
| CREATE | `src/vidbyte_cli/services/suggestions/prompts/categories/strategy.md` | Model-facing guidance for strategy suggestions. |
| CREATE | `src/vidbyte_cli/services/suggestions/prompts/categories/long_term_suggestions.md` | Define 3-6 month and 2 year+ long-term suggestion guidance. |
| CREATE | `src/vidbyte_cli/services/suggestions/prompts/categories/adjacent_opportunity.md` | Model-facing guidance for adjacent-opportunity suggestions. |
| CREATE | `src/vidbyte_cli/services/suggestions/prompts/categories/preparation.md` | Model-facing guidance for preparation suggestions. |
| CREATE | `src/vidbyte_cli/services/suggestions/prompts/categories/coordination.md` | Model-facing guidance for coordination suggestions. |
| MODIFY | `src/vidbyte_cli/services/suggestions/categories.py` | Remove four IDs, add the new ID, and map retained categories to assets. |
| MODIFY | `src/vidbyte_cli/services/suggestions/prompts/library.py` | Load nested category prompt assets through package resources. |
| MODIFY | `src/vidbyte_cli/services/suggestions/README.md` | Document the revised category registry and prompt asset boundary. |
| MODIFY | `pyproject.toml` | Package category Markdown files in built distributions. |
| MODIFY | `README.md` | Update the public category count and new category usage. |
| MODIFY | `scripts/test_suggestions.py` | Add exact taxonomy, rejection, acceptance, prompt, and list-output checks. |
| MODIFY | `scripts/run_ci.py` | Verify every category asset is present in the built wheel. |
| DELETE | N/A | No existing files are deleted; the removed categories are registry entries, not files. |

---

## 10. Testing Plan

### Unit Tests

- [Edge Case] Registry order contains exactly the 14 specified IDs after removing four and inserting one.
- [Hidden Failure] Each removed ID fails `require_known()` and cannot leak into the allowed-category tuple.
- [Silent Failure] `long_term_suggestions` appears in `ids()`, resolves through `describe()`, and its title/summary are not empty or copied from `strategy`.
- [Hidden Assumption] Every retained registry entry resolves to one readable category asset, including when loaded through package resources rather than a current-directory path.
- [Edge Case] `prompt_section(None)` renders all 14 assets, while a selected tuple renders only the selected assets.
- [Silent Failure] Selected prompt assets preserve caller-specified order and do not silently append removed or unselected categories.
- [Hidden Assumption] The long-term asset explicitly contains both `3-6 month` and `2 year+` planning language and a milestone connection.

### Integration Tests

- [Edge Case] A service request restricted to `long_term_suggestions` returns no other primary category.
- [Hidden Failure] CLI requests for each removed category exit non-zero before the service can run; a valid new-category request exits zero without credentials.
- [Silent Failure] Human and JSON `agents suggest categories` output both contain exactly 14 IDs, including the new ID and excluding all four removed IDs.
- [Hidden Assumption] The category command still works with the SDK unavailable and no provider credentials configured.
- [Hidden Failure] A built wheel contains all category assets and an installed invocation can render the category command from outside the source checkout.

### Manual / QA Test Cases

1. Given a clean environment with no provider credentials, run `python -m vidbyte_cli agents suggest categories`; confirm the 14 IDs are shown and the four removed IDs are absent.
2. Given a goal and `--category long_term_suggestions`, run `python -m vidbyte_cli agents suggest run --goal "Build a durable learning product" --category long_term_suggestions --count 1`; confirm the result identifies the new category.
3. Given each removed ID, run the same command with that ID; confirm the CLI returns a typed usage failure without attempting a model call.
4. Build the wheel, run the installed CLI from a directory outside the repository, and confirm category listing still succeeds.

---

## 11. Dependencies & External Services

| Dependency | Version / Endpoint | Purpose | Risk |
|------------|--------------------|---------|------|
| Python standard library `importlib.resources` | Python >= 3.11 | Load category Markdown from source and wheel packages. | A missing package-data declaration could pass source tests and fail only after installation. |
| Setuptools package data | Existing `pyproject.toml` configuration | Include nested category prompt files in wheels. | The glob must remain aligned with the registry's 14 assets. |
| Existing Click and Pydantic contracts | Existing project ranges | Validate category flags and render structured outputs. | No new dependency risk; accidental type/shape changes would affect callers. |

---

## 12. Rollout & Deployment

- No feature flag or backend deployment order is required.
- This is a CLI contract change: callers using one of the four removed identifiers must discover and select a retained category or `long_term_suggestions`.
- The implementation will be committed in an isolated worktree branched from `feat/suggestion-agent`, because `main` does not contain the agent being changed.
- Run the focused suggestion test, Ruff/mypy checks as needed, and the full `python scripts/run_ci.py` gate before handoff.
- Rollback is a Git revert of the taxonomy and asset changes, followed by the same focused and full verification commands.

---

## 13. Open Questions

N/A - The requested category identifier is normalized to `long_term_suggestions` because all existing CLI category IDs use lowercase snake_case. The requested 3-6 month and 2 year+ horizons are treated as category guidance, while the existing generic `IdeaHorizon` filter remains unchanged.

---

## 14. Alternatives Considered

### Alternative 1: Keep category guidance in `categories.py`

- What: Change only the Python tuple and leave descriptions/guidance inline.
- Why rejected: The Vidbyte field guide requires reusable model-facing vocabularies to be authored as packaged Markdown so agents and reviewers can inspect the full category contract.

### Alternative 2: Reuse `strategy` for long-term suggestions

- What: Keep the existing 17-category shape minus four entries and tell callers to use `strategy` for long-range ideas.
- Why rejected: The user requested a distinct category, and `strategy` does not explicitly distinguish 3-6 month capability building from 2 year+ direction.

### Alternative 3: Add new `IdeaHorizon` enum values for `three_to_six_months` and `two_year_plus`

- What: Encode the two timeframes as new structured result horizon values.
- Why rejected: The request adds a category, not a result-schema redesign. Keeping the generic horizon filter stable avoids breaking schema consumers while the category prompt carries the requested planning distinction.

### Alternative 4: Branch the implementation worktree from `main`

- What: Follow the generic workflow literally and create the change from `main`.
- Why rejected: The current `main` revision does not contain `agents suggest`; that branch would omit the very feature this change must modify. The worktree will be isolated but based on the current suggestion-agent feature branch.

