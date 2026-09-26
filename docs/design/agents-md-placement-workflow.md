# Design Doc: AGENTS.md Placement Workflow

**Status:** Implemented
**Author:** Claude Code (design-doc-lite workflow)
**Created:** 2026-09-25

## What and why

Pull requests regularly put code in the wrong folder or layer, and `AGENTS.md` already says where each kind of code belongs. This change adds a GitHub Actions workflow that runs Codex (`gpt-6-luna`, `high` reasoning effort) on every opened or updated pull request. Codex reads `AGENTS.md`, finds code in the PR's diff that sits somewhere the Map assigns elsewhere, and moves it, updating imports and references. The workflow then commits the relocation and pushes it back to the PR branch. The same workflow and prompt ship in the Vidbyte, Vidbyte-cli, and Vidbyte-SDK repositories.

## How it works

- Trigger: `pull_request` with `types: [opened, synchronize]`, skipped for fork PRs (no secrets, no push access). A per-PR `concurrency` group cancels a stale run when a new push arrives.
- Checkout: the PR head branch with full history and `persist-credentials: false`, so the agent has no git credentials.
- Prompt: `.github/prompts/agents-md-placement.md` (Goal and Instructions sections), plus a runtime footer naming the base branch and the `git diff <base-sha>...HEAD` scope. The assembled prompt and the agent's report are written to `$RUNNER_TEMP`, outside the repository.
- Agent: `openai/codex-action` pinned to v1.12, `permission-profile: ":workspace"` (workspace writes, no network), `safety-strategy: drop-sudo`. The action proxies the OpenAI key, so the agent never sees it.
- Commit: a final step appends the report to the job summary, and if the working tree changed, commits as `github-actions[bot]` with the report as the message body and pushes to the head branch.
- Push token: `secrets.PLACEMENT_PUSH_TOKEN` if set, otherwise `GITHUB_TOKEN`. A `GITHUB_TOKEN` push triggers no workflows, so it cannot loop but leaves CI unrun on the relocation commit. A PAT push runs CI and re-runs this workflow once, which finds nothing to move.

## Files

- `.github/workflows/agents-md-placement.yml` (new)
- `.github/prompts/agents-md-placement.md` (new)
- `AGENTS.md`: the `.github/workflows/` entry no longer says the folder holds a single `ci.yml`, and names the new workflow as a non-gate automation.

`ci.yml` and `scripts/run_ci.py` are unchanged: the new workflow runs no lint, build, or publish step, so the local/remote gate parity rule is untouched.

## Risks and open questions

- Setup: the repository needs an `OPENAI_API_KEY` Actions secret.
- The agent can misjudge a placement. The prompt limits it to the PR's own diff, requires `AGENTS.md` to clearly name a different home, forbids behavior changes, and makes "no change" the default. Every relocation is a visible, revertible commit.
- If the author pushes while a run is in progress, the run is cancelled; the next run covers the new head.
- Authors must `git pull` before their next push after a relocation commit lands.

## Verification

- `actionlint` 1.7.12 passes on the new workflow.
- `python scripts/run_ci.py` passes (no package code changed).
- After merge, the first real PR confirms end to end: the job summary shows the agent's report, and a relocation commit appears when code is misplaced.
