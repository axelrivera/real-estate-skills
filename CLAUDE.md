# CLAUDE.md

Claude plugin marketplace for real estate agents. Read [docs/architecture.md](docs/architecture.md) before building or changing a skill.

## Layout

```
.claude-plugin/marketplace.json     # marketplace catalog; add every new plugin here
plugins/<plugin>/
  .claude-plugin/plugin.json        # plugin manifest
  skills/<skill>/SKILL.md           # one directory per skill
shared/                             # shared code, copied into skills (planned)
dev/                                # dev tooling and fixtures, never shipped
Makefile                            # make setup | runtime-check | outputs | package | clean
docs/                               # all documentation
sources/                            # prototype skills, local only, git-ignored
```

## Rules

- **Documentation goes in `docs/`.** The root README stays short and links there. No README files inside plugins.
- **`sources/` is reference only.** Rebuild skills from it; never copy a prototype into `plugins/`, and never edit or ship anything from it.
- **Skills run in claude.ai and Cowork only** (desktop app and cloud), not Claude Code. Script paths are relative to the skill directory. Do not use `/mnt/...` paths or paths outside the skill directory. Skill descriptions stay under 1,024 characters.
- **Dependencies:** use only what the sandbox has ([docs/runtime-support.md](docs/runtime-support.md)). Python code must be 3.11-compatible. Never install packages at run time.
- **Local dev:** run `make setup` once; `make test` after changing `shared/`; generate outputs with `make outputs`. Use `.venv/bin/python` and the Node version in `.nvmrc`. See [docs/development.md](docs/development.md).
- **Shared code is edited in `shared/` only.** `scripts/_shared/` inside a skill is a committed copy; never edit it by hand. After changing `shared/`: `make test`, `make sync`, commit the copies with the change. The pre-commit hook blocks commits with stale copies.
- **Every skill has a markdown mode and a file mode**, both rendered by scripts from the same data JSON. The core profile skills are markdown only.
- **Skills never require other skills.** Read profiles and handoffs as files when present; otherwise collect what's needed inline.
- **No hard-coded brand colors.** File outputs get their palette from `shared/design`, starting from the agent profile's colors (buyer blue / seller orange by default). Status colors (good / caution / risk) are fixed.
- **No silent Florida defaults** outside the built-in Florida/Stellar market. Ask, or label the assumption and mark the output Preliminary.
- **Skill names** carry no output format (`-pdf`), and use a `buyer-` / `seller-` prefix when a skill serves one side.

## Workflow

- Follow the phases and per-skill checklist in [docs/migration-plan.md](docs/migration-plan.md) and update its status table as skills move.
- Update [docs/plugins.md](docs/plugins.md) when a skill or plugin is added or renamed.
- Validate after changing any manifest: `claude plugin validate .`
