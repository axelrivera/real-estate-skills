# Release Checklist

The gate every release passes before the pull request from `develop` into `main`. Work top to bottom; a release ships only when every box is checked or has a written reason in the release notes. Background on each step is in [development.md](development.md).

## 1. Automated Checks

- [ ] `make check` passes (check-sync, lint-skills, py311, style-check and test; test prints every PDF fixture too).
- [ ] `make release-check` passes: the slow mock-contract tests (no skips: needs PyMuPDF and `sources/Contracts/FARBAR/`) and `make fuzz` (every skill in parallel). The developer runs it before the pull request; the smoke pass never waits on it.
- [ ] `make forms-check` reports no revised, new or removed forms, or each one is handled per [Updating a Contract Form](development.md#updating-a-contract-form).
- [ ] `make mock-contracts ARGS="--answer-key --scanned"` builds every starter.
- [ ] `make outputs` renders every fixture.
- [ ] `make fuzz` (inside `make release-check`): the generated tests on 25 inputs per skill from fresh seeds, with no invariant failure (a failure is fixed in the construction, never with a check for that input; [Tests](development.md#tests)).
- [ ] `claude plugin validate .` passes.

## 2. Golden Results

- [ ] `make test` passes `test_golden`. Every change to `dev/golden/` since the last release is explained in the commit that made it (`git log -p v<last>..develop -- dev/golden/`). An unexplained number, date or flag change is a bug until proven otherwise.

## 3. Samples

- [ ] `make samples`, then check what changed with `git diff --stat samples/`. Samples carry their build time, so every file shows as changed; a change is real only when the page text differs (`dev/samples_diff.py`).
- [ ] Commit the samples whose page text changed. Layout and overflow are covered by `make layout-check` and `make fuzz`, not by eye.

## 4. Evals

- [ ] List what changed since the last release: `git diff --stat v<last>..develop -- skills shared`. A change in `shared/` counts for every skill that copies it.
- [ ] Run the full eval pass once (`dev/evals/setup.py N`, every skill, including the mock-package and smoke-kit mirrors; [development.md](development.md#evals)), graded checks first. The pass rate is no lower than the last full pass. An expectation that passed last time and fails now is re-run three times (`--runs 3 <skill>:<id>`) and compared with `dev/evals/spread.py N` before it's called a regression: the spread shows no script-owned differences.
- [ ] Re-run the fair-housing evals whenever a template, reference or prose script changed.
- [ ] Every failed expectation and real friction item is fixed, or recorded in [status.md](status.md) with a reason.

## 5. Package

- [ ] List `dist/real-estate-<version>.plugin`: only `.claude-plugin/plugin.json`, `skills/` and `LICENSE`; no `__pycache__`, `.DS_Store`, `dev/`, `sources/` or `out/`.
- [ ] `dist/skills/` holds one zip per folder in `skills/` and nothing else.
- [ ] The release zip holds the `.plugin`, the agent guide (`README.md`), the PDF manual and `LICENSE`. The guide (`dev/package/README.md`) describes this version's behavior, and `make manual` rebuilt the manual from it ([The Agent Guide and Manual](development.md#the-agent-guide-and-manual); `make package` stops when the manual is stale).

## 6. Manual Smoke Test

- [ ] Run the smoke pass in [manual-testing.md](manual-testing.md) (`make manual-kit`, about ten yes/no checks, twenty minutes) on the packaged build in the desktop app (Cowork) and in claude.ai, with any older copy uninstalled. Every check is a Yes, or its failure is fixed and the case re-run.

## 7. Version and Notes

- [ ] The version in `.claude-plugin/plugin.json` is bumped per [Versioning](development.md#versioning), once for the release.
- [ ] [status.md](status.md) has release notes written for agents under a heading ending in `Version <version>`: what they'll notice, anything that changed or was removed, and whether several unreleased versions ship together. `make release` publishes every section since the last release tag as the GitHub notes.
- [ ] Open the pull request `develop` → `main`; merge when `check-sync` passes. Then `make release` from an up-to-date `main`.
