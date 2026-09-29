# Release Checklist

The gate every release passes before the pull request from `develop` into `main`. Work top to bottom; a release ships only when every box is checked or has a written reason in the release notes. Background on each step is in [development.md](development.md).

## 1. Automated Checks

- [ ] `make package` passes (it runs check-sync, test, lint-skills, py311 and style-check first).
- [ ] `make test` shows no skipped mock-contract tests (needs PyMuPDF and `sources/Contracts/FARBAR/`).
- [ ] `make forms-check` reports no revised, new or removed forms, or each one is handled per [Updating a Contract Form](development.md#updating-a-contract-form).
- [ ] `make mock-contracts ARGS="--answer-key --scanned"` builds every starter.
- [ ] `make outputs` renders every fixture.
- [ ] `claude plugin validate .` passes.

## 2. Golden Results

- [ ] `make test` passes `test_golden`. Every change to `dev/golden/` since the last release is explained in the commit that made it (`git log -p v<last>..develop -- dev/golden/`). An unexplained number, date or flag change is a bug until proven otherwise.

## 3. Samples

- [ ] `make samples`, then check what changed with `git diff --stat samples/`. Samples carry their build time, so every file shows as changed; a change is real only when the page text differs (`dev/samples_diff.py`).
- [ ] Open the regenerated PDFs, PPTX and ICS and look at them: layout, colors, no overflowing text, nothing a client shouldn't see.

## 4. Evals

- [ ] List what changed since the last release: `git diff --stat v<last>..develop -- skills shared`. A change in `shared/` counts for every skill that copies it.
- [ ] Re-run the evals of every changed skill ([development.md](development.md#evals)), including the mock-package evals for contract skills. The pass rate is no lower than the last iteration's.
- [ ] Re-run the fair-housing evals whenever a template, reference or prose script changed.
- [ ] Every failed expectation and real friction item is fixed, or recorded in [status.md](status.md) with a reason.

## 5. Package

- [ ] List `dist/real-estate-<version>.plugin`: only `.claude-plugin/plugin.json`, `skills/` and `LICENSE`; no `__pycache__`, `.DS_Store`, `dev/`, `sources/` or `out/`.
- [ ] `dist/skills/` holds one zip per folder in `skills/` and nothing else.
- [ ] The release zip holds the `.plugin`, the agent guide (`README.md`), the PDF manual and `LICENSE`. The guide (`dev/package/README.md`) describes this version's behavior, and `make manual` rebuilt the manual from it ([The Agent Guide and Manual](development.md#the-agent-guide-and-manual); `make package` stops when the manual is stale).

## 6. Manual Smoke Test

- [ ] Run [manual-testing.md](manual-testing.md) on the packaged build in the desktop app (Cowork) and in claude.ai, with the old plugins uninstalled. Every case passes, or its failure is fixed and the case re-run.

## 7. Version and Notes

- [ ] The version in `.claude-plugin/plugin.json` is bumped per [Versioning](development.md#versioning), once for the release.
- [ ] [status.md](status.md) has release notes written for agents under a heading ending in `Version <version>`: what they'll notice, anything that changed or was removed, and whether several unreleased versions ship together. `make release` publishes every section since the last release tag as the GitHub notes.
- [ ] Open the pull request `develop` → `main`; merge when `check-sync` passes. Then `make release` from an up-to-date `main`.
