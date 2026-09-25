# Development

Skills run in the claude.ai / Cowork sandbox. The local environment mirrors it so every output (markdown, PDF, PPTX) can be generated and debugged on a Mac.

## Requirements

- Python 3.12 (`PYTHON=python3.x make setup` to use another; keep code 3.11-compatible)
- [nvm](https://github.com/nvm-sh/nvm); the Node version comes from `.nvmrc` (pinned to the sandbox's 22.22.2)
- Optional: LibreOffice (`brew install --cask libreoffice`) for deck checks and PPTX → PDF previews. The sandbox has it; decks are generated without it. The Makefile adds `/Applications/LibreOffice.app/Contents/MacOS` to `PATH`; override with `LO_BIN=...` if it's installed elsewhere. Shell aliases don't work here.

## Commands

| Command | What it does |
|---|---|
| `make setup` | Creates `.venv` from `dev/requirements.txt`, installs Chromium for Playwright, installs Node from `.nvmrc` and the modules in `dev/package.json` |
| `make hooks` | Installs the pre-commit hook that blocks commits when `scripts/_shared/` copies are out of date (`make setup` does this too). GitHub Actions ([.github/workflows/check.yml](../.github/workflows/check.yml)) runs check-sync on every push to `main` or `develop` and every pull request |
| `make sync` | Copies `shared/` into `scripts/_shared/` of every skill that has a `scripts/` folder |
| `make sync` copies only what each skill imports | Each skill's `scripts/_shared/` holds the shared modules its scripts import, what those import, and the data they read (markets for `profiles`, CSS for `render` and `cma`) |
| `make check-sync` | Fails if any copy differs from `shared/`. Runs before `make package`; the pre-commit hook also compares what's staged |
| `make test` | Runs the unit tests in `dev/tests/` |
| `make preview-design` | Renders the brand palette for sample scenarios (defaults, one color, split, pale, black, status clash) into `out/design/palettes.pdf` |
| `make runtime-check` | Runs the runtime check against the local environment, to compare with [runtime-support.md](runtime-support.md) |
| `make outputs` | Renders every fixture in `dev/fixtures/<skill>/*.json` into `out/<skill>/<fixture>/` |
| `make samples` | Regenerates `samples/<skill>/`, the committed preview files (PDF, PPTX and ICS; renders never write JSON): one happy path per file-mode skill, rendered from `dev/samples/<skill>.json` with the mock agent in `dev/samples/profile.md`. Every name, brokerage, address and MLS number in `dev/samples/` is fictional (the county and public data sources are real because the tax rules need them). It then writes `samples/README.md` from `dev/samples/readme-template.md` (`dev/samples_readme.py`): each `{{pattern}}` there becomes a link to the matching file with its page, slide or event count; edit the text in the template. Run it by hand when you want fresh previews, and commit the result |
| `make style-check` | Renders every fixture and flags em dashes used in prose (in outputs, shipped files and `shared/**/*.md`; a lone em dash for an empty value is fine), `--` or a spaced en dash used as a dash in shipped markdown, labels not in Title Case, and markdown headings not in Title Case. `dev/style_check.py <skill>` checks one skill. Remaining label findings should be sentence-style headings or fragments |
| `make lint-skills` | Checks every SKILL.md: valid frontmatter, name matches the folder, description ≤ 1,024 characters, Guardrails first, every named path exists |
| `make py311` | Checks shipped Python for 3.11 (the Cowork runtime): `python3.11 -m compileall` when it's installed, otherwise the grammar plus 3.12-only f-string forms |
| `make package` | Runs check-sync, test, lint-skills, py311 and style-check, then builds `dist/real-estate-<version>.plugin` (the desktop app's **Upload local plugin** format: `.claude-plugin/plugin.json` at the archive root). It holds only `plugin.json`, `skills/` and `LICENSE`; docs, `dev/` and `shared/` stay out. Also builds the release zip `dist/real-estate-skills-<version>.zip`: the `.plugin`, `dev/package/README.md` (the agent guide: install, profile, MLS setup using Stellar as the example, each skill with inputs and examples; version filled in) and every PDF in `dev/package/` (the manual; the build stops if there is none) for sharing |
| `make package-skills` | Runs the same checks, then zips every skill into `dist/skills/<skill>.zip` for upload to claude.ai as single skills; the runtime check goes to `dist/dev/` (don't upload it) |
| `make clean` | Removes `out/` and `dist/` |

## Branches

- **`develop`:** active development. Commit and push here.
- **`main`:** releases. It changes only through a pull request from `develop`, and a ruleset requires the `check-sync` status check to pass before merging.

To release: bump the version (below), push `develop`, open a pull request into `main` (`gh pr create --base main --head develop`), and merge it once `check-sync` passes. Then run `make package` on `main` and publish the GitHub release: `gh release create v<version> dist/real-estate-skills-<version>.zip dist/real-estate-<version>.plugin --target main --title <version> --generate-notes`.

## Versioning

The version lives only in `.claude-plugin/plugin.json`. It names the `.plugin` and the release zip, and installed copies update when it changes, so a release that ships without a bump can leave agents on the old version.

Bump once per release (before the pull request into `main`, or before sharing a zip), not per commit. Pick the highest level that applies to everything since the last release:

| Bump | When the release... | Examples |
|---|---|---|
| Minor (0.8.0 to 0.9.0) | Changes what an agent does, uploads or gets: a skill added, removed or renamed; a new or changed input, output file or default; a change to `profile.md` or a handoff format | 0.7.0 removed market-profile; 0.8.0 took the 360 report as input; 0.9.0 added project instructions and the agent guide |
| Patch (0.9.0 to 0.9.1) | Ships fixes an agent notices only as things working better: wrong numbers, parsing, wording, references, guide text, an accepted column name | A new MLS column alias; a template typo |
| None | Changes nothing shipped: `docs/`, `dev/` tooling, evals, tests, samples | This file |

While the version is below 1.0, a minor bump may also break things (a removed skill, a new profile schema); say so in the status notes. Go to 1.0.0 once every skill has passed its evals and been checked by hand in claude.ai and Cowork; after that, a breaking change is a major bump.

Record each release in [status.md](status.md) (what changed for agents), and run `claude plugin validate .` after the bump.

## Evals

Each skill's test prompts live in `dev/evals/<skill>/evals.json` with their input files. To run them (Claude Code, from the repo root):

1. For each eval, make `out/evals/iteration-N/<skill>/eval-<id>/` with `task.md` (the prompt only), `inputs/` (its files) and `with_skill/outputs/`. Keep `expected_output` out of the runner's view.
2. Start one subagent per eval with [dev/evals/RUNNER.md](../dev/evals/RUNNER.md) (replace `<repo>` with the repo path): it simulates the sandbox (skill folder only, `OUTPUT_DIR`, the pinned Python and Node) and saves the reply (`response.md`), every file, and `friction.md`, an honest list of where the skill made it stumble.
3. Grade each run against `expected_output` into `with_skill/grading.json`, and review with the skill-creator's `eval-viewer/generate_review.py out/evals/iteration-N --static out/evals/iteration-N/review.html`.
4. Fix what `friction.md` and the grades reveal (skill text, references, scripts), add a test for each script fix, and re-run the evals that changed.

Baselines (the same prompts without the skill) are optional here: the skills are rebuilds with known-good outputs, so the with-skill runs and their friction notes carry most of the signal.

## Troubleshooting

- **`sharp` fails to install and tries to build from source:** a Homebrew `vips` is on the machine. `make setup` already sets `SHARP_IGNORE_GLOBAL_LIBVIPS=1`; use the same flag if you run `npm install` by hand.
- **`npm audit` warns about `sharp` and `image-size`:** the versions are pinned to match the sandbox, which is what the skills actually run on. Don't upgrade them locally.

## Layout

```
.claude-plugin/          # plugin.json (the real-estate plugin) + marketplace.json (one entry, source "./")
skills/<skill>/          # every skill; the only folder the plugin loads
shared/                  # shared code and references, copied into skills by make sync
Makefile
.nvmrc
dev/                     # dev tooling, never shipped
  requirements.txt       # Python packages, pinned to sandbox versions
  package.json           # Node modules, pinned to sandbox versions
  runtime-check/         # diagnostic skill
  hooks/pre-commit       # runs check-sync
  sync_shared.py         # make sync / make check-sync
  tests/                 # unit tests (make test); skill_import.py loads each skill's scripts without name clashes
  preview_design.py      # palette preview (make preview-design)
  package.py             # make package (one .plugin + release zip) / make package-skills
  package/README.md      # install instructions shipped in the release zip
  package/*.pdf          # the manual, shipped in the release zip
  fixtures/<skill>/      # data files for make outputs (file-mode skills); the CMAs' long-summary.json pushes every page-1 field to its limit, so page 1 must still fit
  evals/<skill>/         # test prompts per skill (see skill-guidelines.md)
  samples/               # fully mocked inputs for make samples: <skill>.json, mls-export.csv, seller-cma-deck.json, profile.md, readme-template.md
  samples_readme.py      # make samples: writes samples/README.md from the template
samples/<skill>/         # committed preview files from make samples
.venv/  out/  dist/      # git-ignored
```

## Shared code

| Module | What it does |
|---|---|
| `shared/design.py` | Brand palette from the agent's colors ([architecture](architecture.md#brand-colors)) |
| `shared/profiles.py` | Reads the agent's profile (`profile.md`); merges a property's market values from the built-in layers (state, MLS, county, national estimates) with the source of each; `Market.with_deal` puts a deal's own costs on top |
| `shared/markets/states/fl.md` | Built-in Florida state layer (costs, taxes, contract rules) |
| `shared/markets/mls/stellar.md` | Built-in Stellar MLS layer (formats, coverage), for Florida and Puerto Rico |
| `shared/render.py` | Output location, file names, HTML → PDF with footer, and the `render.py` command line (`--profile`, `--mls`, `--sample`, plus each skill's own options through `extra_args`) |
| `shared/report.css` | Base PDF styles on the theme variables, print-light: header rule, tables with rules, outlined hero, notes |
| `shared/dates.py` | US federal holidays (with observed dates) and business-day math |
| `shared/finance.py` | Loan programs and seller-contribution caps, payments, 2-1 buydown, property tax, title premium, seller net |
| `shared/handoff.py` | cma-handoff v1: build, validate, read from `.cma.json` (or a fenced markdown block from older chat summaries; no longer written) |
| `shared/contract_forms.py` | Which contract rules apply to which form: FR/BAR AS IS (inspection walk-away, post-inspection credit) vs. Standard (repair notices, repair limits) vs. any other contract. The offer engine, buyer-offer-strategy and contract-timeline route through it, so the forms' math never mixes |
| `shared/offer_engine.py` | Offer analysis for both offer skills: listing and offer defaults with ranked assumptions, seller net sheet (via `finance.seller_net`), appraisal downside, certainty score, risk flags, counters, multi-offer ranking |
| `shared/mls.py` | MLS export reader (columns from the MLS layer or `--columns`) and market statistics, trend line |
| `shared/prose.py` | The render check: em dashes in prose and clear fair-housing phrases in the data file stop the render, naming each field |
| `shared/references/fair-housing.md` | Fair housing rules; copied to `references/` of each skill whose SKILL.md points to it |
| `shared/cma.py`, `shared/cma.css` | CMA report pieces: labels, tables, scatterplot, dot plot, keep-together groups, pagination |

After editing `shared/`, run `make test` and `make sync`, and commit the updated copies with the change.

`shared/` is a Python package. In a skill it's copied to `scripts/_shared/` and imported as `from _shared import design`. Tests and dev scripts import it from the repo root as `from shared import design`. Modules inside `shared/` import each other relatively (`from . import design`) so both work.

## Skill render contract

Every skill with file outputs exposes one entry point, so `make outputs` works the same way for all of them:

```
python scripts/render.py DATA.json --format pdf|pptx|all --out DIR
```

Markdown output comes from templates in the skill's `assets/`, filled in by Claude, so it's checked through the evals in `dev/evals/<skill>/`, not `make outputs`.

`--format` accepts only the formats that skill supports. `all` renders every one of them; if one fails (for example the deck without Node), the others are still saved and listed, and the run ends with a message naming what wasn't built. Skill options (`--cma`, `--mode`, `--option`) are added with `render.main(..., extra_args=...)` and arrive in `ctx`; input errors listed in `errors=` end the run with their plain message.
