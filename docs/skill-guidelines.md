# Skill guidelines

How every skill in this marketplace is built. Based on the skill-creator best practices.

## Anatomy

```
<skill>/
├── SKILL.md        # workflow and pointers; lean
├── references/     # domain detail Claude reads only when a step needs it
├── assets/         # templates and files used in outputs (markdown templates, CSS, examples)
└── scripts/        # deterministic work only
    └── _shared/    # synced copy of shared/ (never edit)
```

Only add a folder when the skill needs it.

## SKILL.md

- **Lean.** The workflow, the judgment calls, and a pointer to each reference file with when to read it. Aim for under ~150 lines; 500 is the hard ceiling. Detail that only matters in one step belongs in `references/`.
- **Frontmatter:** `name` (lowercase, hyphens) and `description`: what the skill does and when to use it, including the phrases agents actually say. Slightly pushy, because skills tend to under-trigger. Under 1,024 characters.
- **Explain why.** Say why a rule matters so Claude can apply it sensibly, rather than all-caps MUSTs.
- **Plain language for the agent.** Users are not technical: no JSON, YAML or hex codes in replies unless asked.
- **Guardrails first.** Right after the intro, a `## Guardrails` section: fair housing, no em dashes in prose, Title Case labels, and (for skills with `render.py`) that the render check stops on either. A skill that writes prose a client reads points to `references/fair-housing.md` and names its own risky spots (findings, value drivers, offer reasons). Copy the wording from an existing skill at the same level ([architecture](architecture.md#guardrails)).
- **No em dashes in prose** in reports, chat replies, templates, examples or references: use a comma, colon, parentheses or a new sentence. A lone em dash standing for an empty value (a table cell with nothing in it) is fine. Claude copies the style of what it reads, so references follow the rule too.
- **Labels in Title Case:** document and section titles, column headers, row names, tiles, legend entries, card and slide titles, pills, and template headings and bold field labels. Sentences, notes, table values, fragments spliced into a sentence, and sentence-style finding headings stay sentence case. ALL-CAPS labels stay as they are. The SKILL.md **Guardrails** section states both, so chat replies follow them too. Markdown headings in SKILL.md, references and templates are Title Case too, even though they're instructions to Claude, so one rule covers every heading; file names (`report.json`), field keys (`## listing`) and `code` keep their own spelling. `make style-check` checks them, along with `--` or a spaced en dash used as a dash in shipped markdown. In labels.json, list real sentences and table values that share a label prefix under `_prose` so the check skips them.
- **Paths** are relative to the skill folder (`scripts/extract_colors.py`, `assets/template.md`). References are one level deep: SKILL.md points to them; they don't chain.

## Scripts vs templates

| Work | Where |
|---|---|
| Math, scoring, dates, net sheets | `scripts/` (deterministic, testable; Claude never hand-calculates) |
| Parsing files (MLS CSV, images, websites) | `scripts/` |
| Validation (does this profile parse? what's missing?) | `scripts/` |
| PDF and PPTX rendering | `scripts/render.py DATA.json --format pdf\|pptx` |
| Markdown output (chat replies, profile files) | `assets/*-template.md`, filled in by Claude |

Markdown mode takes its numbers from the same data JSON the scripts produce, so chat and files always agree. Only the layout comes from the template.

## PDF Layout

- **Top fact row.** Context under the header (home facts, contract terms, the inputs a report rests on) goes in one divider row (`divrow factrow` in `shared/report.css`), not a grid of boxed cells. It wraps onto a second line as it grows and needs no layout change when an item is added.
- **Every item carries its word** ("payoff $214,000", "built 1962", "deadline Sun Nov 15"), since a bare value means nothing in a row of mixed facts. Order: the property first, then the money and dates.
- **Missing items drop out**, no dashes. A missing input that makes the report Preliminary stays and shows in the risk color ("CMA not provided").
- **The row is context only.** A number the reader decides on (a net, a target, a score) belongs in page 1's tiles or tables, not the fact row. A boxed strip (`.snap`) is only for a few comparable numbers read side by side, as in buyer-offer-strategy's market strip.

## References

- One topic per file, named for what it answers (`references/brand-colors.md`, `references/florida-costs.md`).
- SKILL.md says when to read each one ("Read `references/x.md` before step 3").
- Reference files over about 100 lines start with a short table of contents (Anthropic's skill guidance), so Claude can jump to the part it needs.

## Evals

Each skill has test prompts in `dev/evals/<skill>/evals.json` (never shipped): 2–4 realistic prompts with the expected result, plus input files when needed. They're run with the skill by subagents that simulate the sandbox and report their friction ([development.md](development.md#evals)), following the skill-creator loop, before a skill is marked done. Baseline runs without the skill are optional.
