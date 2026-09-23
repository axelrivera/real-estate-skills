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
| **1. Foundation** | `shared/` modules every skill needs: design system, profile reader with the Florida/Stellar market profile, render helpers; sync and drift-check tools in `dev/`. Modules only some skills use (offer engine, market stats, lending rules, holidays, `cma-handoff v1`) and each skill's regression fixtures move into `shared/` and `dev/fixtures/` when the first skill that needs them is rebuilt |
| **2. Core** | `agent-profile`, `market-profile` |
| **3. Pilot** | `contract-timeline` — smallest, standalone, both sides. Sets the conventions. Includes a non-Florida contract test and a run in claude.ai and Cowork |
| **4. CMAs** | `buyer-cma`, then `seller-cma` (deck without `/mnt/skills`) |
| **5. Offers** | `seller-offer-review`, then `buyer-offer-strategy` (it simulates the listing-side view) |

## Per-skill checklist

- [ ] Final name; description rewritten for triggering, under 1,024 characters, no references to prototype names
- [ ] Relative script paths only; no `/mnt/...`
- [ ] Data JSON + `scripts/render.py` (render contract) for markdown and file formats; fixtures in `dev/fixtures/<skill>/` render with `make outputs`
- [ ] Reads agent and market profiles when present; works without them
- [ ] No hard-coded brand colors; file outputs render correctly with default, single custom and split buyer/seller colors
- [ ] Produces / consumes handoffs per [architecture.md](architecture.md#handoffs-between-skills)
- [ ] Regression tests pass against prototype fixtures
- [ ] Non-Florida test case
- [ ] Trigger tests: should fire / should route to a sibling skill
- [ ] Packaged and run in claude.ai and Cowork
- [ ] `_shared/` in sync; plugin version bumped; [plugins.md](plugins.md) updated

## Status

| Shared module | Status |
|---|---|
| `shared/design` | Done: palette, legibility, status separation, party colors; tests and preview |
| `shared/profiles` + `markets/` | Done (Florida seller title fees and 2.5% + 2.5% brokerage defaults researched 2026-09): agent and market profiles, Florida state layer, Stellar MLS layer (Florida and Puerto Rico), county overrides, value sources, 2025 millage for 7 Central Florida counties (57 districts) |
| `shared/render` | Done: output location, file names, HTML → PDF, render command line |
| Sync and drift check | Done: `make sync`, `make check-sync`, pre-commit hook |

| Skill | Status |
|---|---|
| `agent-profile` | Built per skill guidelines (template, reference, check script), tests and evals; needs a run in claude.ai and Cowork |
| `market-profile` | Built per skill guidelines (template, fields reference, check script), tests and evals; needs a run in claude.ai and Cowork |
| `contract-timeline` | Built per skill guidelines: engine matches the prototype sample exactly; FR/BAR and other contracts; branded PDF; 3 fixtures, tests, evals; needs a run in claude.ai and Cowork |
| `buyer-cma` | Built per skill guidelines: numbers match the prototype sample exactly; branded PDF, English/Spanish labels, markdown template, cma-handoff v1; fixture, tests, evals; needs a run in claude.ai and Cowork |
| `seller-cma` | Not started |
| `seller-offer-review` | Built per skill guidelines on the new `shared/offer_engine.py`: numbers match the prototype samples exactly when given the prototype's costs; costs now from the market profile (Florida 2.5% + 2.5% brokerage, itemized $1,145 title fees; other states left out and marked Preliminary); consumes `cma-handoff v1`; single and multi-offer PDF in seller colors; 4 fixtures (incl. Texas), tests, evals; needs a run in claude.ai and Cowork |
| `buyer-offer-strategy` | Built per skill guidelines on `shared/offer_engine.py` and `shared/finance`: options, scores, cash and payments match the prototype sample; buyer blue (prototype used orange); consumes `cma-handoff v1` (range, median adjusted, market stats); Offer Options + Offer Package Worksheet PDFs (FR/BAR, or entries by name elsewhere); 3 fixtures (incl. Texas), tests, evals; outcome log not ported; needs a run in claude.ai and Cowork |
