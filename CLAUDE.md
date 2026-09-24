# CLAUDE.md

One Claude plugin (`real-estate`) of skills for real estate agents; the repo root is the plugin and a one-plugin marketplace (`real-estate-skills`). Read [docs/status.md](docs/status.md) for current progress and [docs/architecture.md](docs/architecture.md) before building or changing a skill. New skills and scope ideas go in [docs/roadmap.md](docs/roadmap.md).

## Layout

```
.claude-plugin/plugin.json          # the plugin manifest (name "real-estate"); the only place the version lives
.claude-plugin/marketplace.json     # one-plugin marketplace, source "./"; lets users add the repo by URL
skills/<skill>/SKILL.md             # one directory per skill
shared/                             # shared code and references, copied into skills by make sync
dev/                                # dev tooling and fixtures, never shipped
Makefile                            # make setup | test | sync | check-sync | style-check | lint-skills | outputs | samples | package | package-skills | clean
docs/                               # all documentation
samples/                            # committed preview files (PDF, PPTX, ICS), one happy path per skill (make samples), never shipped
sources/                            # prototype skills, local only, git-ignored
```

## Rules

- **Build skills per [docs/skill-guidelines.md](docs/skill-guidelines.md):** lean SKILL.md, domain detail in `references/`, markdown output from templates in `assets/`, scripts only for deterministic work (math, parsing, validation, PDF/PPTX). Never write a script to produce markdown.
- **Documentation goes in `docs/`.** The root README stays short and links there. No README files inside skills.
- **`sources/` is reference only.** Rebuild skills from it; never copy a prototype into `skills/`, and never edit or ship anything from it.
- **Skills run in claude.ai and Cowork only** (desktop app and cloud), not Claude Code. Script paths are relative to the skill directory. Do not use `/mnt/...` paths or paths outside the skill directory. Skill descriptions stay under 1,024 characters.
- **Dependencies:** use only what the sandbox has ([docs/runtime-support.md](docs/runtime-support.md)). Python code must be 3.11-compatible. Never install packages at run time.
- **Local dev:** run `make setup` once; `make test` after changing `shared/`; generate outputs with `make outputs`. `samples/` is regenerated with `make samples` from the fully mocked inputs in `dev/samples/`; never put real people, brokerages, addresses or MLS numbers there. Use `.venv/bin/python` and the Node version in `.nvmrc`. See [docs/development.md](docs/development.md).
- **Shared code is edited in `shared/` only.** `scripts/_shared/` inside a skill is a committed copy; never edit it by hand. After changing `shared/`: `make test`, `make sync`, commit the copies with the change. The pre-commit hook blocks commits with stale copies.
- **Every skill has a markdown mode and a file mode** from the same data JSON: markdown via an `assets/` template, files via `scripts/render.py`. The core profile skills are markdown only.
- **One plugin.** Every skill goes in `skills/`; never add a second plugin or a marketplace entry. Packaging and install routes are in [docs/architecture.md](docs/architecture.md#packaging).
- **Skills never require other skills.** Read profiles and handoffs as files when present; otherwise collect what's needed inline.
- **Saved files:** profiles are saved and found per `shared/references/saved-files.md` (`.claude/real-estate/` in the Cowork working folder, else the outputs folder). Skills point to `references/saved-files.md`; scripts take explicit `--agent` / `--market` / `--cma` paths and never search.
- **No hard-coded brand colors.** File outputs get their palette from `shared/design`, starting from the agent profile's colors (buyer blue / seller orange by default). Status colors (good / caution / risk) are fixed.
- **Print-light PDFs:** no filled section bars, table headers, zebra rows, hero panels or callouts. Use colored type, rules and thin accent bars; fill only where the fill is the data (chart marks, timeline bars, meters, small pills). See [docs/architecture.md](docs/architecture.md#brand-colors).
- **Fair housing (HUD):** every skill opens with a **Guardrails** section; skills that write client prose point to `references/fair-housing.md` (edit it in `shared/references/` only). Describe the property, numbers and terms, never people. Levels per skill are in [docs/architecture.md](docs/architecture.md#guardrails).
- **No em dashes in prose** in anything a skill ships or writes (reports, chat replies, templates, examples, references). A lone em dash for an empty value (an empty table cell) is fine, and so are en dashes in number ranges.
- **Labels are Title Case** (headings, column headers, row names, tiles, legends, card and slide titles). Sentences, notes and table values stay sentence case. See [docs/skill-guidelines.md](docs/skill-guidelines.md#skillmd). Check with `make style-check`.
- **English only.** No Spanish or other-language modes, label files or templates, even where a prototype in `sources/` has them.
- **No silent Florida defaults** outside the built-in Florida/Stellar market. Ask, or label the assumption and mark the output Preliminary.
- **Contract forms never mix.** FR/BAR AS IS and Standard rules (inspection walk-away, repair reserve vs. repair limits, deadlines) are routed only through `shared/contract_forms.py`; never branch on the form name elsewhere, never run one form's math on the other, and never default a missing form silently (ask, or record a high-impact assumption).
- **Skill names** carry no output format (`-pdf`), and use a `buyer-` / `seller-` prefix when a skill serves one side.

## Workflow

- **Branches:** work and commit on `develop`; `main` changes only through a pull request from `develop` (the `check-sync` status check must pass). Never push to `main` directly. See [docs/development.md](docs/development.md#branches).
- Follow the phases and per-skill checklist in [docs/migration-plan.md](docs/migration-plan.md) and update its status table as skills move.
- Update [docs/skills.md](docs/skills.md) and the README skill table when a skill is added or renamed.
- Validate after changing any manifest: `claude plugin validate .`
