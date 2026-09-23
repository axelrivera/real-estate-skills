# Migration plan: prototypes → final skills

The prototypes in `sources/Prototype Skills/` (local only, git-ignored) are **reference material**. Final skills are rebuilt from them, not copied. See [architecture.md](architecture.md) for the rules every final skill follows.

## Name mapping

| Prototype | Final skill | Plugin |
|---|---|---|
| — | `agent-profile` (markdown only) | core |
| — | `market-profile` (markdown only) | core |
| `contract-timeline` | `contract-timeline` | transactions |
| `buyer-cma-pdf` | `buyer-cma` | transactions |
| `seller-cma-pdf` | `seller-cma` | transactions |
| `offer-analysis-pdf` | `seller-offer-review` | transactions |
| `buyer-offer-builder` | `buyer-offer-strategy` | transactions |

Naming rules: no output format in names (`-pdf`); side prefix (`buyer-` / `seller-`) when a skill serves one side.

## What the prototypes share

| Code | Where | State |
|---|---|---|
| Offer engine (`engine.py`, 574 lines) | `buyer-offer-builder`, `offer-analysis-pdf` | Identical, synced by hand |
| `florida_costs.md`, `scoring_rubric.md` | both offer skills | Identical |
| `market_stats.py` | both CMAs | ~90% identical |
| `report.css` / `summary.css` / `theme.css` | all | Identical or accent-color differences. Brand hex values are hard-coded in CSS, Python renderers and `build_deck.js`. `buyer-offer-builder` uses the seller orange by mistake |
| HTML → PDF via Playwright | 5 of 6 PDF renderers | Same approach |
| PPTX via pptxgenjs | `seller-cma-pdf` | Depends on `/mnt/skills/public/pptx` — must go |

## Phases

| Phase | Work |
|---|---|
| **1. Foundation** | `shared/` modules (offer engine, market stats, costs, design system with palette derived from the agent's brand colors, render helpers, output location); market profile schema with Florida/Stellar defaults; `cma-handoff v1` schema; `tools/` sync, check, package; regression fixtures from prototype examples and sample PDFs |
| **2. Core** | `agent-profile`, `market-profile` |
| **3. Pilot** | `contract-timeline` — smallest, standalone, both sides. Sets the conventions. Includes a non-Florida contract test and a run in all three runtimes |
| **4. CMAs** | `buyer-cma`, then `seller-cma` (deck without `/mnt/skills`) |
| **5. Offers** | `seller-offer-review`, then `buyer-offer-strategy` (it simulates the listing-side view) |

## Per-skill checklist

- [ ] Final name; description rewritten for triggering, under 1,024 characters, no references to prototype names
- [ ] Relative script paths only; no `/mnt/...`, no `${CLAUDE_PLUGIN_ROOT}`
- [ ] Data JSON + `render_md.py` + file renderer(s); files fall back to markdown when dependencies are missing
- [ ] Reads agent and market profiles when present; works without them
- [ ] No hard-coded brand colors; file outputs render correctly with default, single custom and split buyer/seller colors
- [ ] Produces / consumes handoffs per [architecture.md](architecture.md#handoffs-between-skills)
- [ ] Regression tests pass against prototype fixtures
- [ ] Non-Florida test case
- [ ] Trigger tests: should fire / should route to a sibling skill
- [ ] Packaged and run in Claude Code, claude.ai and Cowork
- [ ] `_shared/` in sync; plugin version bumped; [plugins.md](plugins.md) updated

## Status

| Skill | Status |
|---|---|
| `agent-profile` | Not started |
| `market-profile` | Not started |
| `contract-timeline` | Not started |
| `buyer-cma` | Not started |
| `seller-cma` | Not started |
| `seller-offer-review` | Not started |
| `buyer-offer-strategy` | Not started |
