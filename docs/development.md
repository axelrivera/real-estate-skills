# Development

Skills run in the claude.ai / Cowork sandbox. The local environment mirrors it so every output (markdown, PDF, PPTX) can be generated and debugged on a Mac.

## Requirements

- Python 3.12 (`PYTHON=python3.x make setup` to use another; keep code 3.11-compatible)
- Python 3.11 for `make py311` (the Cowork runtime): `make setup` installs [uv](https://docs.astral.sh/uv/) with Homebrew when it's missing (`brew install uv`) and runs `uv python install 3.11`. `make py311` uses `python3.11` on the `PATH`, else `uv python find 3.11`
- [nvm](https://github.com/nvm-sh/nvm); the Node version comes from `.nvmrc` (pinned to the sandbox's 22.22.2)
- Optional: LibreOffice (`brew install --cask libreoffice`) for deck checks and PPTX → PDF previews. The sandbox has it; decks are generated without it. The Makefile adds `/Applications/LibreOffice.app/Contents/MacOS` to `PATH`; override with `LO_BIN=...` if it's installed elsewhere. Shell aliases don't work here.

## Commands

| Command | What it does |
|---|---|
| `make setup` | Creates `.venv` from `dev/requirements.txt`, adds the local-only tools in `dev/requirements-tools.txt` (PyMuPDF, which the sandbox doesn't have), installs Chromium for Playwright, installs Node from `.nvmrc` and the modules in `dev/package.json`, and installs Python 3.11 with uv (uv itself with Homebrew if missing) |
| `make hooks` | Installs the pre-commit hook that blocks commits when `scripts/_shared/` copies are out of date (`make setup` does this too). GitHub Actions ([.github/workflows/check.yml](../.github/workflows/check.yml)) runs check-sync on every push to `main` or `develop` and every pull request |
| `make sync` | Copies `shared/` into `scripts/_shared/` of every skill that has a `scripts/` folder |
| `make sync` copies only what each skill imports | Each skill's `scripts/_shared/` holds the shared modules its scripts import, what those import, and the data they read (markets for `profiles`, CSS for `render` and `cma`) |
| `make check-sync` | Fails if any copy differs from `shared/`. Runs before `make package`; the pre-commit hook also compares what's staged |
| `make forms-check` | Local only (the PDFs live in the git-ignored `sources/`): compares every FAR/BAR form PDF in `sources/Contracts/FARBAR/` with `dev/forms/farbar-forms.json` and reports new, removed and changed forms with a text diff and what depends on each, plus revision citations in `shared/references/farbar-*.md` or `contract_forms.VERIFIED` that don't match. `make forms-check ARGS="--accept CR-7_L"` records a reviewed form. See [Updating a Contract Form](#updating-a-contract-form) |
| `make mock-contracts` | Local only (fills the FAR/BAR PDFs in the git-ignored `sources/`): builds every starter scenario in `dev/mock_contracts/scenarios/` into `out/mock-contracts/<name>/`, as one contract package PDF each, named after the property. `ARGS="--answer-key --scanned"` adds the answer key and a scanned copy. Any other scenario: ask the `mock-contract` skill in Claude Code. See [mock-contracts.md](mock-contracts.md) |
| `make test` | Runs the unit tests in `dev/tests/` ([Tests](#tests)), the generated tests on 8 inputs per skill. With LibreOffice installed (`LO_BIN`, added at the end of `PATH`) it also checks the listing presentation's PDF copy, with a 60-second conversion limit; without it that check is skipped. The mock-contract build checks (about 17 seconds) run only with `RUN_SLOW=1 make test`; `make package` and `make package-skills` set it |
| `make fuzz` | The generated tests on 200 inputs per skill (`N=50` for another count, `FUZZ_SEED=1000` to shift the seeds, `SKILL=seller-cma` for one skill): before every release and after a change to `shared/` or a skill's compute or render. See [Tests](#tests) |
| Coverage | `.venv/bin/python -m coverage run --include='shared/*,skills/*' -m unittest discover -s dev/tests`, then `.venv/bin/python -m coverage report`. Skill tests run `shared/` through each skill's `scripts/_shared/` copy, so count a `shared/` module as covered by its copies too (the copies are identical). Measure before and after removing tests; line coverage must not drop more than a point or two |
| `make golden` | Rewrites `dev/golden/` (`dev/golden.py --update`): what each skill computes for its fixtures (numbers, dates, flags), with the clock frozen. `make test` fails until the snapshots match, so an engine change that moves a number is either approved here, with the `git diff dev/golden/` explained in the commit, or fixed |
| `make manual-kit` | Local only: builds the release smoke-test kit into `out/manual-test/` (files to upload, prompts, the yes/no checks with the facts to answer them). See [manual-testing.md](manual-testing.md) |
| `make preview-design` | Renders the brand palette for sample scenarios (defaults, one color, split, pale, black, status clash) into `out/design/palettes.pdf` |
| `make runtime-check` | Runs the runtime check against the local environment, to compare with [runtime-support.md](runtime-support.md) |
| `make outputs` | Renders every fixture in `dev/fixtures/<skill>/*.json` into `out/<skill>/<fixture>/`; `SKILL=<skill>` renders one skill's (seller-net-sheet: `florida-one-price`, `florida-two-prices` and `florida-three-prices` are the same home at one, two and three prices, to compare the tile row). `stress-*.json` render with the long-name profile `dev/fixtures/_profiles/stress.md` |
| `make samples` | Regenerates `samples/<skill>/`, the committed preview files (PDF, PPTX and ICS; renders never write JSON): one happy path per file-mode skill, rendered from `dev/samples/<skill>.json` with the mock agent in `dev/samples/profile.md`. Real cities and counties are fine in `dev/samples/` (the tax rules need them, and so do the public data sources); every street, name, brokerage and MLS number is made up. It then writes `samples/README.md` from `dev/samples/readme-template.md` (`dev/samples_readme.py`): each `{{pattern}}` there becomes a link to the matching file with its page, slide or event count; edit the text in the template. Run it by hand when you want fresh previews, and commit the result |
| `make style-check` | Renders every fixture and flags em dashes used in prose (in outputs, shipped files and `shared/**/*.md`; a lone em dash for an empty value is fine), `--` or a spaced en dash used as a dash in shipped markdown, labels not in Title Case, markdown headings not in Title Case, and client wording in report HTML and calendar text (tool words, unfilled `{placeholders}`, data keys, ISO dates in a sentence, jargon: the scripts' own text, which the run-time check never sees; an error). `dev/style_check.py <skill>` checks one skill. Remaining label findings should be sentence-style headings or fragments |
| `make layout-check` | Prints every fixture of every PDF skill into `out/layout/<skill>/<fixture>/` (`dev/layout_check.py`; `SKILL=<skill>` for one) and fails on a page-1 overflow warning, clipped text (`Check: ... clipped`, from `shared/render.py`: a box that hides its overflow, an ellipsis, or text past the page's right edge) or a near-empty page read back from the PDF (`cma.page_fill`): a page between the first and the last under half full, or a last page after page 1 under 15% full. `stress-*.json` fixtures (long names, brokerage, address, labels, many deadlines) render with `dev/fixtures/_profiles/stress.md`. A page a fixture leaves near-empty on purpose goes in `ALLOW` in `dev/layout_check.py` with its reason. `make test` runs the same check (`dev/tests/test_layout.py`) when Chromium and pdftotext are installed |
| `make lint-skills` | Checks every SKILL.md: valid frontmatter, name matches the folder, description ≤ 1,024 characters, Guardrails first, every named path exists. Also fails if shipped Python (`skills/`, `shared/`) imports a dev-only library from `dev/requirements-tools.txt` |
| `make py311` | Compiles every shipped Python file with a real Python 3.11 (the Cowork runtime): `python3.11 -m compileall`, using uv's 3.11 when none is on the `PATH`. With no 3.11 at all it falls back to the grammar plus the 3.12-only f-string forms, and says so |
| `make manual` | Rebuilds the PDF manual, `dev/package/Real-Estate-Skills-Manual.pdf`, from the agent guide (`dev/package/README.md`), its screenshots (`dev/package/images/`) and `dev/package/manual.css`, printed with the dev Chromium (`dev/manual.py`). Commit the PDF and `dev/package/manual.sha256` with the guide change. See [The Agent Guide and Manual](#the-agent-guide-and-manual) |
| `make package` | Runs check-sync, test, lint-skills, py311, style-check and layout-check, then builds `dist/real-estate-<version>.plugin` (the desktop app's **Upload local plugin** format: `.claude-plugin/plugin.json` at the archive root). It holds only the git-tracked `plugin.json`, `skills/` and `LICENSE`, so an untracked file never ships; docs, `dev/` and `shared/` stay out. Also builds the release zip `dist/real-estate-skills-<version>.zip`: the `.plugin`, the agent guide as `README.md` (version filled in, screenshot lines left out), the PDF manual and `LICENSE`, for sharing. It stops before building when the manual is older than the guide (`make manual`) |
| `make release` | From an up-to-date `main` with nothing uncommitted and no untracked file under `skills/`: checks that release `v<version>` (from `plugin.json`) doesn't exist yet and that [status.md](status.md) has a section for it, runs `make package`, then publishes the GitHub release with only the release zip. The release notes are the status.md sections for every version since the last release tag (`dev/package.py notes`, into `dist/release-notes-<version>.md`), so an unreleased version's notes ship with the next one. See [Branches](#branches) |
| `make package-skills` | Runs the same checks, clears `dist/skills/` and `dist/dev/`, then zips every skill's tracked files into `dist/skills/<skill>.zip` for upload to claude.ai as single skills; the runtime check goes to `dist/dev/` (don't upload it) |
| `make clean` | Removes `out/` and `dist/` |

## Tests

The reports are correct by construction (one document model per run, `fmt` for every figure, `Ledger` columns, one notes registry, the layout kit; [architecture](architecture.md#shared-report-kit)), so the tests check properties and rules, never a sentence. `make test` runs `dev/tests/`, by layer:

| Layer | What It Checks | Where |
|---|---|---|
| **Math** | Finance, dates and business days, deadlines, nets, prorations, payments, scores. Table-driven (`subTest`) where cases share a shape; properties where they hold for any input (totals are the sum of their lines, a later price nets more, a rolled date is a business day) | `test_finance.py`, `test_ledger.py`, `test_fmt.py`, `test_timeline_dates.py`, `test_offer_engine.py`… |
| **Rules** | Contract forms and riders, flags, which question is asked, counter and backup rules, input validation, refused fields (a figure in a judgment field, a field the script writes). Assert keys, flags, numbers and structure | `test_contract_forms.py`, `test_offer_review_counter.py`, each skill's `test_<skill>.py`… |
| **Golden** | Every fixture's computed facts against `dev/golden/` (`make golden` above). A unit test that runs an unmodified fixture and checks numbers the snapshot already pins adds nothing: change an input, or test the function on hand-built data | `test_golden.py` |
| **Generated** | Seeded random valid inputs per skill (`dev/generators/<skill>.py`: realistic ranges, long names, edge dates, missing optional fields, the rare branches) through compute and the printed files, asserting universal properties only: columns add up, each note once, no label carries a note, legends name what's drawn, the input unchanged, the expected page count, nothing clipped, every printed figure from the document model, no sentence (the model's strings, the page's text, the Check lines) with a placeholder left empty or unfilled (`placeholders.py`: a doubled space, a space before punctuation, empty parentheses, "for in", a brace, a mid-sentence None). Each skill adds its own invariants (below). `test_layout.py` prints every fixture once the same way | `test_generated_<skill>.py`, `test_layout.py` |
| **Static** | Sync, Title Case labels and em dashes (`make style-check`), the forms manifest, Python 3.11, SKILL.md lint, the prose check's phrase tables | `test_sync.py`, `test_style_check.py`, `test_prose.py`, `test_lint_skills.py`, `test_py311_check.py` |
| **Tooling** | Evals setup and spread, the smoke kit, mock contracts, packaging | `test_eval_tooling.py`, `test_manual_kit.py`, `test_mock_contracts.py`, `test_package.py` |

**Generated inputs.** `make test` runs 8 inputs per skill. `make fuzz` runs 200 (`N=…` for another count, `FUZZ_SEED=…` to shift the seeds, `SKILL=<skill>` for one skill); it sets `FUZZ_N` for `dev/tests/test_generated_*.py`, which can also run on their own (`FUZZ_N=200 .venv/bin/python -m unittest dev.tests.test_generated_seller_cma`). Run it before every release and after any change to `shared/` or a skill's compute or render. What each skill's test adds:

- **buyer-cma:** a synthetic MLS export per input (Stellar columns: sales across a market split, listings, the home's own rows), built as the skill builds it (comps adjusted, the time rate by the method's rule, the range by the shared range rule); every comp card adds up to its adjusted value, time adjustments follow the rule, the range passes the range checks within the cap, and no middle page is under half full.
- **seller-cma:** a synthetic export too, varying the pricing options (standard, a reprice, a relist with two or three options), the payoff (stated, a balance, none, no mortgage), closings across the year end and an HOA; each option's one closing sets its proration and holding costs, the deck's net sheet, comps table and nets are the report's, every figure on a slide is the model's, and (with Node, `DECK_N` inputs) no slide text reaches a footer.
- **contract-timeline:** every date moved off a weekend or holiday is a business day per the deal's rules, and the calendar's events are the report's open rows on the same dates.
- **seller-offer-review:** each input renders twice (as given and a step later: a counter back, a new offer, a lapse), with one target closing per report and every Respond By time the model's.
- **buyer-offer-strategy:** the recommended offer is inside every buyer limit unless the model says which one it breaks, each cash column adds to cash to close and the worst case, the worksheet doesn't change with the buyer's max, cash, reserve and payment limit, and a generated buyer CMA's own handoff is read as the offer's range.
- **seller-net-sheet:** one page, columns add up, each note once.

### Adding a Test

- **Pick the layer by what can break.** A formula: math. A branch on a form, rider or input: rules. A figure that moved: golden (approve the diff with `make golden` and explain it in the commit). Anything about how a page reads for any input: a generator's range or an invariant in its generated test.
- **Fix the construction, then test the property.** A report bug found by hand or by an eval is fixed where the class of error comes from (the model, the ledger, the registry, the kit), and the test asserts the property for every input. Never a check for the one input that showed it.
- **Never a wording test.** Client sentences live in `assets/labels.json` and templates and are reviewed there; a test may name a label key or a note key, never the sentence. The prose and style checks cover banned words, Title Case and em dashes.
- **Never a round-named test.** Files and classes are named by topic (`test_offer_review_counter.py`, `class Escalation`), never by the round, audit, iteration or manual case that found the bug. A new test goes into the topic it covers, and only when no existing test asserts the same behavior.
- **Fuzz before release.** `make fuzz` (200 inputs per skill) passes with no failure; a failure is fixed in the construction and its seed range re-run.

## Branches

- **`develop`:** active development. Commit and push here.
- **`main`:** releases. It changes only through a pull request from `develop`, and a ruleset requires the `check-sync` status check to pass before merging.

Before every release, work through [release-checklist.md](release-checklist.md), including `make fuzz` and the smoke test in [manual-testing.md](manual-testing.md) (`make manual-kit`).

To release: bump the version (below), push `develop`, open a pull request into `main` (`gh pr create --base main --head develop`), and merge it once `check-sync` passes. Then, on an up-to-date `main`, run `make release`: it reads the version from `plugin.json`, stops unless you're on `main` with nothing uncommitted, level with `origin/main` and the tag is new, runs `make package`, and publishes GitHub release `v<version>` with only the release zip (the `.plugin` is inside it). Never pass the version by hand; bump `plugin.json` instead.

## Versioning

The version lives only in `.claude-plugin/plugin.json`. It names the `.plugin` and the release zip, and installed copies update when it changes, so a release that ships without a bump can leave agents on the old version.

Bump once per release (before the pull request into `main`, or before sharing a zip), not per commit. Pick the highest level that applies to everything since the last release:

| Bump | When the release... | Examples |
|---|---|---|
| Minor (0.8.0 to 0.9.0) | Changes what an agent does, uploads or gets: a skill added, removed or renamed; a new or changed input, output file or default; a change to `profile.md` or a handoff format | 0.7.0 removed market-profile; 0.8.0 took the 360 report as input; 0.9.0 added project instructions and the agent guide |
| Patch (0.9.0 to 0.9.1) | Ships fixes an agent notices only as things working better: wrong numbers, parsing, wording, references, guide text, an accepted column name | A new MLS column alias; a template typo |
| None | Changes nothing shipped: `docs/`, `dev/` tooling, evals, tests, samples | This file |

While the version is below 1.0, a minor bump may also break things (a removed skill, a new profile schema); say so in the status notes. Go to 1.0.0 once every skill has passed its evals and been checked by hand in claude.ai and Cowork; after that, a breaking change is a major bump.

Record each release in [status.md](status.md) (what changed for agents) under a heading that ends in the version, `## This pass (YYYY-MM-DD): What Changed and Version x.y.z`: `make release` publishes those sections as the release notes and stops when the version has none. Run `claude plugin validate .` after the bump.

## The Agent Guide and Manual

The release zip carries two agent-facing documents built from one source, `dev/package/README.md` (the agent guide):

- **The guide** ships as the zip's `README.md`. It uses the on-screen labels verbatim (**Customize**, **Upload plugin**, **Add Export**) and never mentions JSON, script names or other implementation details.
- **The manual** (`Real-Estate-Skills-Manual.pdf`) is the same text with a cover, contents and screenshots. A screenshot goes in the guide as an HTML comment on its own line, `<!-- figure: images/<name>.png | Caption. -->`, indented to sit inside a numbered step; two in a row sit side by side. Markdown viewers hide these lines and `make package` strips them from the zip's copy. Styles are neutral (black and grays, print-light) in `dev/package/manual.css`.

Update the guide when a release changes what an agent does, uploads or gets, then run `make manual` and commit the guide, the PDF and `dev/package/manual.sha256` together. `make package` and `make test` fail while the manual is older than its sources. The manual carries no version number, so a version bump alone doesn't rebuild it. Replace a screenshot by saving the new PNG under the same name in `dev/package/images/`.

## Evals

Evals test the model, never the scripts: what it reads from the files and enters in the data file, the questions it asks, what it declines, which files it makes, its judgment fields (words only) and whether its chat reply uses the script's lines, including a CMA carried into the offer in the same chat. The math, the script's wording and the layout are covered by the tests above. Each skill's prompts live in `dev/evals/<skill>/evals.json` with their input files; an `expected_output` states behaviors and the facts the inputs settle, never a sentence the script writes. To run them (Claude Code, from the repo root):

1. Run `.venv/bin/python dev/evals/setup.py N [--runs K] [skill[:ids] ...]`: it makes `out/evals/iteration-N/<skill>/eval-<id>/run-<k>/` for k = 1 to K (default 1) with `task.md` (the prompt, led by a "Today is" line so every run counts from the same day), `inputs/` (its files) and `with_skill/outputs/`, keeps `expected_output`, answer keys and the smoke kit's `expected.md` out of the runner's view, and lists every run folder with its skill folder(s) in `out/evals/iteration-N/runs.json`. Calling it again with a higher `--runs` adds runs and keeps the ones done.
2. Start one subagent per run (each entry in `runs.json`) with [dev/evals/RUNNER.md](../dev/evals/RUNNER.md) (replace `<repo>` with the repo path): it simulates the sandbox (skill folder only, `OUTPUT_DIR`, the pinned Python and Node) and saves the reply (`response.md`), every file, the data file each report was rendered from (in `_work/`), and `friction.md`, an honest list of where the skill made it stumble.
3. Grade every run against `expected_output` into its own `run-<k>/with_skill/grading.json` with one subagent per skill and [dev/evals/GRADER.md](../dev/evals/GRADER.md): checks first (the figures the model entered and the reply's figures are the script's, judgment fields are words only, each note said once), then behavior and judgment (the same expectation list for every run of an eval; it also checks the answer keys, the legacy form name, em dashes and fair housing). Review with the skill-creator's `eval-viewer/generate_review.py out/evals/iteration-N --static out/evals/iteration-N/review.html`.
4. Fix what `friction.md` and the grades reveal (skill text, references, scripts), add a test in the right layer for each script fix ([Adding a Test](#adding-a-test)), and re-run the evals that changed.

**One run per eval.** A release runs the full pass once (every skill, the mock-package and smoke-kit mirrors included). Repeat runs are for measuring variance only: when a behavior passes in one iteration and fails in the next, or after rewording a skill's instructions, run that eval three times (`--runs 3 seller-offer-review:5,8`) in a new iteration and compare them with `.venv/bin/python dev/evals/spread.py N [skill[:ids] ...]` (`spread.md` and `spread.json` in the iteration folder).

**The spread report.** `spread.py` reruns each run's data file (`deal.json`, `listing.json`, `buyer.json`, `report.json` or `net-sheet.json`, the newest one under the run's outputs) through the skill's compute step with the clock on the eval's day, keeps the same facts `dev/golden.py` snapshots (`facts()`: numbers, dates, keys, sentence counts), and lists, eval by eval:

- **Script-owned differences** first, as bugs: fields the eval's inputs settle (a date, a count, a tax bill, a fee, a rate), which never differ between runs given the same inputs. One usually traces to a value the model typed differently into the data file, which the report's "Data the Model Wrote" section shows side by side.
- **Expectations that pass in only some runs**, from each run's `grading.json`, and the ones failed in every run.
- **Judgment differences**: the comps, the value range, the list or offer price, and what follows from them (nets, payments, taxes at the chosen price), which may vary within the bounds the evals set. The per-skill list is `SPEC` in `spread.py`; a field that follows judgment counts as judgment only when a judgment field moved in the same eval.

It exits 1 when there is a script-owned difference.

**Chats and chains.** A prompt given as a list is one conversation, message by message (`## Message 1`, `## Message 2` in `task.md`; the runner answers each in turn). An eval that runs two skills in one chat names them in `"skills"` (buyer-offer-strategy eval 5: the buyer CMA, then the offer from its handoff), and the runner gets both skill folders.

**Smoke-kit mirrors.** Each smoke case 2 to 8 ([manual-testing.md](manual-testing.md)) has an eval with the same inputs, marked `"manual_case": "<case folder>"`, so what the smoke pass can't check (the facts read from the files, the questions, the judgment, the reply) is graded here. Their inputs come straight from the kit's own folders (`out/manual-test/<case>/`, never committed copies; `test_eval_tooling.py` checks the kit builds each one), so run `make manual-kit` before setting them up; the kit builds the same files every time. The kit's `expected.md` holds only the smoke checks: grade by `expected_output`.

**Contract packages.** Evals for the contract-reading skills (contract-timeline, seller-offer-review, buyer-offer-strategy) use mock FAR/BAR packages ([mock-contracts.md](mock-contracts.md)), which are never committed: they contain Florida Realtors' form text. The eval entry names the starter instead, `"mock_package": "<starter>"` (add `"mock_scanned": true` for the scanned copy), and lists the package's files by name in `files`. A package dated after the runner's default day (2026-09-26) sets `"today"` to a day after its last document, and the task passes it on.

1. Build the starters with `make mock-contracts ARGS="--answer-key"` (add `--scanned` when an eval wants the scan).
2. `setup.py` copies only the package PDFs the eval lists in `files` from `out/mock-contracts/<starter>/` into each run's `inputs/`, and stops on anything under `key/`: it holds the answers.
3. Grade against `out/mock-contracts/<starter>/key/<Street>-Answer-Key.json`: contract-timeline against an executed package's deal file, seller-offer-review against an offer's listing file. contract-timeline on an offer package should say the contract isn't executed yet.

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
.claude/skills/          # Claude Code skills for developing this repo (mock-contract); never shipped
dev/                     # dev tooling, never shipped
  requirements.txt       # Python packages, pinned to sandbox versions
  requirements-tools.txt # local-only dev tools the sandbox doesn't have (PyMuPDF); never imported by skills/ or shared/
  package.json           # Node modules, pinned to sandbox versions
  runtime-check/         # diagnostic skill
  hooks/pre-commit       # runs check-sync
  sync_shared.py         # make sync / make check-sync
  font_metrics.py        # shared/fonts/metrics.json from the bundled font, measured in Chromium (--check: is it current)
  forms_check.py         # make forms-check: FAR/BAR form PDFs vs. the manifest
  forms/farbar-forms.json # the fully supported forms: revision, text hash, what depends on each (no form text)
  mock_contracts/        # mock FAR/BAR contract packages (make mock-contracts, the mock-contract skill): build.py, scenario.py,
                         #   locate.py (finds blanks), fields.py + fields/ (field maps), stamp.py, fonts/, scenarios/
  tests/                 # unit tests (make test); skill_import.py loads each skill's scripts without name clashes
  preview_design.py      # palette preview (make preview-design)
  package.py             # make package (one .plugin + release zip) / make package-skills / release notes
  manual.py              # make manual: the PDF manual from the agent guide
  package/README.md      # the agent guide, shipped in the release zip as README.md
  package/Real-Estate-Skills-Manual.pdf  # the manual, shipped in the release zip (built by make manual)
  package/manual.css     # the manual's styles; package/manual.sha256: the sources the committed PDF was built from
  package/images/        # the manual's screenshots (Claude desktop app, Stellar Matrix)
  golden.py, golden/     # make golden: snapshots of what each skill computes (checked by make test)
  manual_kit/            # make manual-kit: the release smoke-test kit (docs/manual-testing.md)
  generators/<skill>.py  # seeded valid inputs for the generated tests (make test, make fuzz)
  fixtures/<skill>/      # data files for make outputs (file-mode skills); the CMAs' long-summary.json pushes every page-1 field to its limit, so page 1 must still fit; stress-*.json push names, labels and row counts (make layout-check)
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
| `shared/report.css` | Base PDF styles on the theme variables, print-light: header rule, tables with rules, outlined hero, notes, the layout kit's `kit-*` pieces, and the bundled font (`"Report Sans"`, opted into with body class `font-bundled`) |
| `shared/fmt.py` | Every figure as text: money, short prices, percents, months of supply, dates, deadlines, ranges; half-up rounding ([architecture](architecture.md#shared-report-kit)) |
| `shared/notes.py` | One notes registry per document: each note added once by key, printed once, never in a label |
| `shared/layout.py` | The layout kit (table, tiles, fact row, notes block, header, chart frame and legend from drawn series), text measurement with the bundled font's metrics, and the one page-fit pipeline (`Fit`, `print_pdf`; keep-together groups, pagination and page read-back moved here from `cma.py`) |
| `shared/fonts/` | Inter (OFL), regular and bold, Latin WOFF2 subsets; `metrics.json` from `dev/font_metrics.py`. Copied into every skill that renders a PDF |
| `shared/dates.py` | US federal holidays (with observed dates) and business-day math |
| `shared/finance.py` | Loan programs and seller-contribution caps, payments, 2-1 buydown, property tax, title premium, seller net, `Ledger` (lines rounded once to the dollar, totals from the rounded lines) |
| `shared/handoff.py` | cma-handoff v1: build, validate, read from `.cma.json` (or a fenced markdown block from older chat summaries; no longer written) |
| `shared/contract_forms.py` | Which contract rules apply to which form and rider set: FAR/BAR AS IS (inspection walk-away, post-inspection credit) vs. Standard (repair notices, repair limits), Riders K and L on the Standard form, RESERVED riders on AS IS, rider letters from names, the verified revisions and the chat-only support notes; any other contract gets no FAR/BAR default. The offer engine, buyer-offer-strategy and contract-timeline route through it, so the forms' math never mixes |
| `shared/offer_engine.py` | Offer analysis for both offer skills: listing and offer defaults with ranked assumptions, seller net sheet (via `finance.seller_net`), appraisal downside, certainty score, risk flags, counters, multi-offer ranking |
| `shared/mls.py` | MLS export reader (columns from the MLS layer or `--columns`) and market statistics, trend line |
| `shared/prose.py` | The render check: em dashes in prose, clear fair-housing phrases and client wording (tool words, data keys, ISO dates, jargon) in the data file and the files it reads stop the render, listing every field at once; label fields are put in Title Case |
| `shared/references/fair-housing.md` | Fair housing rules; copied to `references/` of each skill whose SKILL.md points to it |
| `shared/cma.py`, `shared/cma.css` | CMA report pieces: the page-1 heading, scatterplot and dot plot, comps math (adjusted values, time adjustments, the range rules), closing notices; the page fit is `layout.py`'s |

After editing `shared/`, run `make test` and `make sync`, and commit the updated copies with the change.

`shared/` is a Python package. In a skill it's copied to `scripts/_shared/` and imported as `from _shared import design`. Tests and dev scripts import it from the repo root as `from shared import design`. Modules inside `shared/` import each other relatively (`from . import design`) so both work.

## Updating a Contract Form

Florida Realtors revises forms one at a time, a few times a year. Only the forms in `dev/forms/farbar-forms.json` are fully supported, and every rule the skills use for them was read from those exact PDFs, so a revision is handled like the original build, scoped to one form:

1. Download the new PDF from Form Simplicity into `sources/Contracts/FARBAR/` (same folder and naming: the form code in parentheses), replacing the old file.
2. Run `make forms-check`. It shows the form as CHANGED with a line diff against the last snapshot and lists what depends on it (`used_by`).
3. Update the affected blocks in `shared/references/farbar-*.md`, including the "Verified Against" row. If a default, day count or paragraph changed, update `shared/contract_forms.py` (`VERIFIED` for the contracts), `skills/contract-timeline/scripts/timeline.py`, the offer engine and their tests.
4. `make forms-check ARGS="--accept <FAMILY>"` records the new text and revision, then `make test`, `make sync`, `make outputs`.
   If the form has a mock-contract field map (`dev/mock_contracts/fields/<FAMILY>.json`), re-anchor it and update its `revision` ([mock-contracts.md](mock-contracts.md#when-a-form-is-revised)); builds that use the form stop until you do.
5. Version: patch for wording or citations, minor when a default or deadline changes what agents get.

A new form works the same way (it shows as NEW). An agent's upload of a newer revision is caught at run time too: the data file's `form_revision` is compared with `VERIFIED`, and the skill tells the agent in chat to confirm the paragraphs.

## Skill render contract

Every skill with file outputs exposes one entry point, so `make outputs` works the same way for all of them:

```
python scripts/render.py DATA.json --format pdf|pptx|all --out DIR
```

Markdown output comes from templates in the skill's `assets/`, filled in by Claude, so it's checked through the evals in `dev/evals/<skill>/`, not `make outputs`.

A skill on the document model passes `compute=`: `render.main(build, formats, compute=compute)` runs `compute(data, ctx)` once and hands the same result to every format's `build(result, fmt, out_dir, ctx)`, so no format recomputes or re-derives a figure.

`--format` accepts only the formats that skill supports. `all` renders every one of them; if one fails (for example the deck without Node), the others are still saved and listed, and the run ends with a message naming what wasn't built. Skill options (`--cma`, `--mode`, `--option`) are added with `render.main(..., extra_args=...)` and arrive in `ctx`; input errors listed in `errors=` end the run with their plain message.
