# lint/ — agent-facing static analysis for the Vidbyte CLI

This folder turns contracts that review keeps repeating into one blocking, count-ratcheted
command. It exists because a review comment fixes one file, while a rule fixes the next file
too — written by whoever never read that thread.

Diagnostics assume the reader is a coding agent with the output and nothing else, so each
failure states the consequence, the repair, local precedent, the shortcuts that will not
work, and the exact command to re-run.

It is modelled on `vidbyte/lint/` and `vidbyte-sdk/lint/`: the same rule contract, the same
per-rule baseline ratchet, and the same fail-closed behavior. It is deliberately smaller,
because this repository is a transport and presentation layer, and `ruff` plus strict `mypy`
already cover most of what a generic analyzer can see here.

## Responsibilities

- Enforce the CLI-specific contracts a generic linter cannot see, over tracked source only.
- Fail closed when discovery, a parser, the registry, or the baseline fails.
- Freeze existing debt while failing any increase and preserving reductions.

## Non-Goals

- It does not format or rewrite source; that is `ruff format`.
- It does not re-implement `ruff` or `mypy` policy, which `scripts/run_ci.py` already runs.
- It never imports `vidbyte_cli`, so a module that fails to import can still be analyzed.
- It never ships in the wheel: `[tool.setuptools.packages.find]` looks only in `src/`.

## Running the suite

```bash
python lint/run.py
python lint/run.py --rule C001
python lint/run.py --rule C001 --all
python lint/run.py --format json
```

`python scripts/run_ci.py` runs the complete suite as one of its source gates, so local and
remote gates cannot drift.

Exit 0 means every rule is CLEAN, RATCHETED, or IMPROVED. REGRESSED and ERRORED fail, and so
does a `baseline.json` whose keys disagree with the registered catalogue — a registered rule
cannot silently escape enforcement.

## Baseline ratchet

`baseline.json` maps each rule ID to the number of violations that predated its gate. An
allowance may never be raised to make a regression pass. After a real repair, lower the
focused allowance:

```bash
python lint/run.py --rule C001 --update-baseline
```

## Adding a rule

1. Add one module under `lint/rules/` named `<id>_<snake_case_name>.py`, exporting a single
   `RULE` instance. Take the next free ID: `C###`.
2. Register its import path in `_RULE_MODULES` in `lint/core/registry.py`.
3. Add one row to the rule table below.
4. Measure before committing: `python lint/run.py --rule <ID> --format json`, and read the
   findings rather than the count. Hundreds of hits usually means the scope is wrong. Zero
   hits means either genuinely CLEAN — prove it by hand-writing a violation and confirming
   the rule fires — or a broken detector, which is indistinguishable from a passing one.
5. Seed the ratchet with `python lint/run.py --rule <ID> --update-baseline`, then confirm
   `python lint/run.py` still exits 0.
6. Write the diagnostic for an agent with no other context. Cite the review comment the rule
   came from: feedback is the strongest evidence a rule can carry, and it tells the reader
   the rule came from a real failure rather than someone's preference.

Only promote a comment into a rule when it states a rule rather than a fix, is decidable from
source structure alone, generalizes to files written later, has a canonical correct form to
name, and is not already covered. Most comments fail one of those; that is the expected
outcome, because a rule that fires on judgment calls trains every future agent to treat the
whole suite as noise.

## File Index

- `__init__.py` — marks the repository-local lint package.
- `run.py` — the CLI and the application that orchestrates one run.
- `baseline.json` — sorted per-rule debt ceilings.

Nested folders:

- `core/` — source discovery, the rule contract, the ratchet, execution, and reporting.
- `rules/` — one independently selectable module per rule.

## Rule catalogue

| ID | Rule | Protected contract |
|---|---|---|
| C001 | command-help-description-depth | Every `click` command and option carries at least four substantial sentences of `help=`, and every positional argument is named in its command's help — because Click has no `help=` for arguments. Agents read `--help` once and have nothing else. |
| C002 | paid-execute-comment-density | The method that calls an `admit_*` endpoint carries at least ten comment blocks — because it is the one method where a reordering spends a user's money, and the free-then-admit-then-verify-then-run ordering is load-bearing but invisible in the calls themselves. |
