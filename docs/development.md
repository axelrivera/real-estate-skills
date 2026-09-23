# Development

Skills run in the claude.ai / Cowork sandbox. The local environment mirrors it so every output (markdown, PDF, PPTX) can be generated and debugged on a Mac.

## Requirements

- Python 3.12 (`PYTHON=python3.x make setup` to use another; keep code 3.11-compatible)
- [nvm](https://github.com/nvm-sh/nvm); the Node version comes from `.nvmrc`
- Optional: LibreOffice (`brew install --cask libreoffice`) for deck checks and PPTX → PDF previews. The sandbox has it; decks are generated without it.

## Commands

| Command | What it does |
|---|---|
| `make setup` | Creates `.venv` from `dev/requirements.txt`, installs Chromium for Playwright, installs Node from `.nvmrc` and the modules in `dev/package.json` |
| `make runtime-check` | Runs the runtime check against the local environment, to compare with [runtime-support.md](runtime-support.md) |
| `make outputs` | Renders every fixture in `dev/fixtures/<skill>/*.json` into `out/<skill>/<fixture>/` |
| `make package` | Zips every skill into `dist/<plugin>-<skill>.zip` for upload to claude.ai, plus `dist/runtime-check.zip` |
| `make clean` | Removes `out/` and `dist/` |

## Layout

```
Makefile
.nvmrc
dev/                     # dev tooling, never shipped
  requirements.txt       # Python packages, pinned to sandbox versions
  package.json           # Node modules, pinned to sandbox versions
  runtime-check/         # diagnostic skill
  fixtures/<skill>/      # test inputs for make outputs
.venv/  out/  dist/      # git-ignored
```

## Skill render contract

Every skill with outputs exposes one entry point, so `make outputs` works the same way for all of them:

```
python scripts/render.py DATA.json --format md|pdf|pptx|all --out DIR
```

`--format` accepts only the formats that skill supports. `all` renders every one of them.
