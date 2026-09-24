# CLAUDE.md

Claude plugin marketplace for real estate agents. Read [docs/status.md](docs/status.md) for current progress and [docs/architecture.md](docs/architecture.md) before building or changing a skill.

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

- **Build skills per [docs/skill-guidelines.md](docs/skill-guidelines.md):** lean SKILL.md, domain detail in `references/`, markdown output from templates in `assets/`, scripts only for deterministic work (math, parsing, validation, PDF/PPTX). Never write a script to produce markdown.
- **Documentation goes in `docs/`.** The root README stays short and links there. No README files inside plugins.
- **`sources/` is reference only.** Rebuild skills from it; never copy a prototype into `plugins/`, and never edit or ship anything from it.
- **Skills run in claude.ai and Cowork only** (desktop app and cloud), not Claude Code. Script paths are relative to the skill directory. Do not use `/mnt/...` paths or paths outside the skill directory. Skill descriptions stay under 1,024 characters.
- **Dependencies:** use only what the sandbox has ([docs/runtime-support.md](docs/runtime-support.md)). Python code must be 3.11-compatible. Never install packages at run time.
- **Local dev:** run `make setup` once; `make test` after changing `shared/`; generate outputs with `make outputs`. Use `.venv/bin/python` and the Node version in `.nvmrc`. See [docs/development.md](docs/development.md).
- **Shared code is edited in `shared/` only.** `scripts/_shared/` inside a skill is a committed copy; never edit it by hand. After changing `shared/`: `make test`, `make sync`, commit the copies with the change. The pre-commit hook blocks commits with stale copies.
- **Every skill has a markdown mode and a file mode** from the same data JSON: markdown via an `assets/` template, files via `scripts/render.py`. The core profile skills are markdown only.
- **Skills never require other skills.** Read profiles and handoffs as files when present; otherwise collect what's needed inline.
- **No hard-coded brand colors.** File outputs get their palette from `shared/design`, starting from the agent profile's colors (buyer blue / seller orange by default). Status colors (good / caution / risk) are fixed.
- **Print-light PDFs:** no filled section bars, table headers, zebra rows, hero panels or callouts. Use colored type, rules and thin accent bars; fill only where the fill is the data (chart marks, timeline bars, meters, small pills). See [docs/architecture.md](docs/architecture.md#brand-colors).
- **Fair housing (HUD):** every skill opens with a **Guardrails** section; skills that write client prose point to `references/fair-housing.md` (edit it in `shared/references/` only). Describe the property, numbers and terms, never people. Levels per skill are in [docs/architecture.md](docs/architecture.md#guardrails).
- **No em dashes in prose** in anything a skill ships or writes (reports, chat replies, templates, examples, references). A lone em dash for an empty value (an empty table cell) is fine, and so are en dashes in number ranges.
- **Labels are Title Case** (headings, column headers, row names, tiles, legends, card and slide titles). Sentences, notes and table values stay sentence case. See [docs/skill-guidelines.md](docs/skill-guidelines.md#skillmd). Check with `make style-check`.
- **English only.** No Spanish or other-language modes, label files or templates, even where a prototype in `sources/` has them.
- **No silent Florida defaults** outside the built-in Florida/Stellar market. Ask, or label the assumption and mark the output Preliminary.
- **Skill names** carry no output format (`-pdf`), and use a `buyer-` / `seller-` prefix when a skill serves one side.

## Workflow

- Follow the phases and per-skill checklist in [docs/migration-plan.md](docs/migration-plan.md) and update its status table as skills move.
- Update [docs/plugins.md](docs/plugins.md) when a skill or plugin is added or renamed.
- Validate after changing any manifest: `claude plugin validate .`
