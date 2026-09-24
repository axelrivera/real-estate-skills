# Migration plan: prototypes → final skills

The prototypes in `sources/Prototype Skills/` (local only, git-ignored) are **reference material**. Final skills are rebuilt from them, not copied. See [architecture.md](architecture.md) for the rules every final skill follows.

## Name mapping

| Prototype | Final skill |
|---|---|
| `michael-cruz/ai-brain-builder`, `brand-direction-builder` (interview style only) | `agent-profile` (markdown only; replaced `market-profile` on 2026-09-24) |
| `contract-timeline` | `contract-timeline` |
| `buyer-cma-pdf` | `buyer-cma` |
| `seller-cma-pdf` | `seller-cma` |
| `offer-analysis-pdf` | `seller-offer-review` |
| `buyer-offer-builder` | `buyer-offer-strategy` |

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
| **2. Core** | `agent-profile` (one file, `profile.md`: who the agent is) |
| **3. Pilot** | `contract-timeline` — smallest, standalone, both sides. Sets the conventions. Includes a non-Florida contract test and a run in claude.ai and Cowork |
| **4. CMAs** | `buyer-cma`, then `seller-cma` (deck without `/mnt/skills`) |
| **5. Offers** | `seller-offer-review`, then `buyer-offer-strategy` (it simulates the listing-side view) |

## Per-skill checklist (template)

Copy this list into a skill's notes when building or rebuilding it; the status table above tracks which skills are done.

- [ ] Final name; description rewritten for triggering, under 1,024 characters, no references to prototype names
- [ ] Relative script paths only; no `/mnt/...`
- [ ] Data JSON + `scripts/render.py` (render contract) for markdown and file formats; fixtures in `dev/fixtures/<skill>/` render with `make outputs`
- [ ] Reads the profile (`--profile profile.md`) when present; works without it
- [ ] No hard-coded brand colors; file outputs render correctly with default, single custom and split buyer/seller colors
- [ ] Produces / consumes handoffs per [architecture.md](architecture.md#handoffs-between-skills)
- [ ] Regression tests pass against prototype fixtures
- [ ] Non-Florida test case
- [ ] Trigger tests: should fire / should route to a sibling skill
- [ ] Packaged and run in claude.ai and Cowork
- [ ] `_shared/` in sync; plugin version bumped; [skills.md](skills.md) updated

## Status

All phases are built (version 0.2.0; 0.3.0 to 0.5.0 add the audit's Phase 1 to 3 fixes, see [status.md](status.md#audit-2026-09-23)). Every skill has run through the eval loop once (iteration 1, 2026-09-23: 21 prompts, with-skill runs by sandbox-simulating subagents) and the fixes from those runs are in. What's left for every skill is a run in claude.ai and Cowork by the user.

| Shared module | Status |
|---|---|
| `shared/design` | Done: palette, legibility, status separation, party colors and tints; tests and preview |
| `shared/profiles` + `markets/` | Done (Florida seller title fees and 2.5% + 2.5% brokerage defaults researched 2026-09): the agent's profile file, Florida state layer, national estimates layer (`national.md`) (incl. buyer insurance, typical deposit), Stellar MLS layer (Florida and Puerto Rico), county overrides, value sources, 2025 millage for 7 Central Florida counties (57 districts) |
| `shared/render` | Done: output location, file names, HTML → PDF, render command line with skill options and partial formats |
| `shared/finance`, `dates`, `handoff`, `mls`, `cma` | Done: payments, program caps, property tax (incl. school-only and percent exemptions), title (table, quote, estimate), seller net with keyed lines and structured assumptions; business days; cma-handoff v1; MLS export reader and stats; CMA report pieces |
| `shared/offer_engine` | Done: one port of the prototype engine for both offer skills |
| Sync and drift check | Done: `make sync`, `make check-sync`, pre-commit hook |

| Skill | Status |
|---|---|
| `agent-profile` | Rebuilt 2026-09-24 as the one onboarding skill: two-round interview after the Cruz prototypes, one `profile.md` with who the agent is; `market-profile` removed (local costs are conventions: national estimates, per-deal overrides). Evals rewritten (6 prompts, incl. a cold start); needs an eval run and a run in claude.ai and Cowork |
| `contract-timeline` | Built: engine matches the prototype sample; FR/BAR and other contracts (per-deadline time and rollover for TREC); client flags vs. agent notes; evals run and fixed; needs a run in claude.ai and Cowork |
| `buyer-cma` | Built: numbers match the prototype sample; cma-handoff v1; evals run and fixed; needs a run in claude.ai and Cowork |
| `seller-cma` | Built: report PDF and 15-slide deck from one report.json; nets from the market layers with labeled estimates and an assumed 5% commission; cma-handoff v1; evals run and fixed; needs a run in claude.ai and Cowork |
| `seller-offer-review` | Built on `shared/offer_engine.py`: prototype numbers reproduced with the prototype's costs; market costs, labeled national estimates outside built-in markets; single and multi-offer PDF; evals run and fixed (certainty-priority sellers aren't countered for a small gain); needs a run in claude.ai and Cowork |
| `buyer-offer-strategy` | Built on `shared/offer_engine.py` and `shared/finance`: Offer Options + Offer Package Worksheet; evals run and fixed (stronger option recommended when it lifts the outlook inside every limit, honest reasons); outcome log not ported; needs a run in claude.ai and Cowork |
