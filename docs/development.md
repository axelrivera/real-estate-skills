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
| `make hooks` | Installs the pre-commit hook that blocks commits when `scripts/_shared/` copies are out of date (`make setup` does this too) |
| `make sync` | Copies `shared/` into `scripts/_shared/` of every skill that has a `scripts/` folder |
| `make check-sync` | Fails if any copy differs from `shared/`. Runs before `make package` and on every commit |
| `make test` | Runs the unit tests in `dev/tests/` |
| `make preview-design` | Renders the brand palette for sample scenarios (defaults, one color, split, pale, black, status clash) into `out/design/palettes.pdf` |
| `make runtime-check` | Runs the runtime check against the local environment, to compare with [runtime-support.md](runtime-support.md) |
| `make outputs` | Renders every fixture in `dev/fixtures/<skill>/*.json` into `out/<skill>/<fixture>/` |
| `make package` | Zips every skill into `dist/<plugin>-<skill>.zip` for upload to claude.ai, plus `dist/runtime-check.zip` |
| `make clean` | Removes `out/` and `dist/` |

## Troubleshooting

- **`sharp` fails to install and tries to build from source:** a Homebrew `vips` is on the machine. `make setup` already sets `SHARP_IGNORE_GLOBAL_LIBVIPS=1`; use the same flag if you run `npm install` by hand.
- **`npm audit` warns about `sharp` and `image-size`:** the versions are pinned to match the sandbox, which is what the skills actually run on. Don't upgrade them locally.

## Layout

```
Makefile
.nvmrc
dev/                     # dev tooling, never shipped
  requirements.txt       # Python packages, pinned to sandbox versions
  package.json           # Node modules, pinned to sandbox versions
  runtime-check/         # diagnostic skill
  hooks/pre-commit       # runs check-sync
  sync_shared.py         # make sync / make check-sync
  tests/                 # unit tests for shared/ and dev tools (make test)
  preview_design.py      # palette preview (make preview-design)
  fixtures/<skill>/      # data files for make outputs (file-mode skills)
  evals/<skill>/         # test prompts per skill (see skill-guidelines.md)
.venv/  out/  dist/      # git-ignored
```

## Shared code

| Module | What it does |
|---|---|
| `shared/design.py` | Brand palette from the agent's colors ([architecture](architecture.md#brand-colors)) |
| `shared/profiles.py` | Reads agent and market profiles; merges market values with the source of each |
| `shared/markets/states/fl.md` | Built-in Florida state layer (costs, taxes, contract rules) |
| `shared/markets/mls/stellar.md` | Built-in Stellar MLS layer (formats, coverage), for Florida and Puerto Rico |
| `shared/render.py` | Output location, file names, HTML → PDF with footer, and the `render.py` command line (`--agent`, `--market`, `--sample`) |
| `shared/report.css` | Base PDF styles (header, section bars, tables, hero, notes) on the theme variables |
| `shared/dates.py` | US federal holidays (with observed dates) and business-day math |

After editing `shared/`, run `make test` and `make sync`, and commit the updated copies with the change.

`shared/` is a Python package. In a skill it's copied to `scripts/_shared/` and imported as `from _shared import design`. Tests and dev scripts import it from the repo root as `from shared import design`. Modules inside `shared/` import each other relatively (`from . import design`) so both work.

## Skill render contract

Every skill with file outputs exposes one entry point, so `make outputs` works the same way for all of them:

```
python scripts/render.py DATA.json --format pdf|pptx|all --out DIR
```

Markdown output comes from templates in the skill's `assets/`, filled in by Claude, so it's checked through the evals in `dev/evals/<skill>/`, not `make outputs`.

`--format` accepts only the formats that skill supports. `all` renders every one of them.
