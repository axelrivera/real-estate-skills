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

## References

- One topic per file, named for what it answers (`references/brand-colors.md`, `references/florida-costs.md`).
- SKILL.md says when to read each one ("Read `references/x.md` before step 3").
- Files over ~300 lines start with a table of contents.

## Evals

Each skill has test prompts in `dev/evals/<skill>/evals.json` (never shipped): 2–4 realistic prompts with the expected result, plus input files when needed. They're run with the skill by subagents that simulate the sandbox and report their friction ([development.md](development.md#evals)), following the skill-creator loop, before a skill is marked done. Baseline runs without the skill are optional.
