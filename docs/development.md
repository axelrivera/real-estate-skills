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
  tests/                 # unit tests for shared/ (make test)
  preview_design.py      # palette preview (make preview-design)
  fixtures/<skill>/      # test inputs for make outputs
.venv/  out/  dist/      # git-ignored
```

## Shared code

`shared/` is a Python package. In a skill it's copied to `scripts/_shared/` and imported as `from _shared import design`. Tests and dev scripts import it from the repo root as `from shared import design`. Modules inside `shared/` import each other relatively (`from . import design`) so both work.

## Skill render contract

Every skill with outputs exposes one entry point, so `make outputs` works the same way for all of them:

```
python scripts/render.py DATA.json --format md|pdf|pptx|all --out DIR
```

`--format` accepts only the formats that skill supports. `all` renders every one of them.
