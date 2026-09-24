# Status and handoff

Where the work stands and what's left. Last updated 2026-09-24 (version 0.3.0: audit Phase 1 done). Read this first when resuming, together with [CLAUDE.md](../CLAUDE.md), [architecture.md](architecture.md), [skill-guidelines.md](skill-guidelines.md), [development.md](development.md) and [migration-plan.md](migration-plan.md).

## Done (committed on `main`)

| Area | What |
|---|---|
| Scaffold | Marketplace (`core`, `transactions`) at 0.3.0, docs, CLAUDE.md, Makefile, `.venv` + nvm dev env pinned to sandbox versions, pre-commit sync check |
| `shared/` | `design`, `profiles` + `markets/` (Florida state layer, Stellar MLS layer), `render`, `report.css`, `dates`, `finance`, `handoff` (cma-handoff v1), `mls`, `cma` + `cma.css`, `offer_engine`, `contract_forms` (FR/BAR AS IS vs. Standard routing), `prose` (em dash and fair-housing check), `references/` (`fair-housing.md`, `condo.md`). See [development.md](development.md#shared-code) |
| `core` | `agent-profile`, `market-profile` (markdown only) |
| `transactions` | `contract-timeline`, `buyer-cma`, `seller-cma` (PDF + deck), `seller-offer-review`, `buyer-offer-strategy` |
| Tests | `make test`: 294 passing. Every fixture in `dev/fixtures/` renders with `make outputs` |
| Evals | Iteration 1 run for all 7 skills (21 prompts): 108/117 expectations passed (92%) before fixes; fixes applied. Iteration 2 re-ran the three most-changed evals (seller-cma Texas, buyer-offer-strategy minimal, TREC option period): fixes held, small follow-ups applied. Runner: [dev/evals/RUNNER.md](../dev/evals/RUNNER.md); procedure in [development.md](development.md#evals) |

## This pass (2026-09-23)

1. **Worktrees merged:** offer skills + `shared/offer_engine.py`, then `seller-cma`, copied from the agent worktrees, reviewed (PDFs and deck checked), committed per skill; worktrees removed.
2. **Shared changes decided:**

   | Proposal | Decision |
   |---|---|
   | `render.main` extra args + partial formats | Done: `extra_args`, `errors`, `ctx["formats"]`; other formats still saved when one fails |
   | Concession cap at exactly 25% down | **Kept 9%**: Fannie Mae goes by LTV (≤75% → 9%); the prototype's 6% was wrong |
   | Buyer insurance estimate | Done: `buyer_costs.insurance_rate` (Florida 0.9%); seller holding stays 0.7% |
   | Design party tints | Done (`party_tints`); a light neutral wasn't needed |
   | Scatter label `above` | Done: left, right, above, below |
   | `seller_net` structured assumptions + title-fee override | Done |
   | Percent vs. fraction | Done: every `*_pct` is a fraction, checked everywhere; interest `rate` stays a percent |

3. **Earlier eval findings** for agent-profile, contract-timeline and market-profile: all fixed.
4. **Evals, iteration 1:** results in `out/evals/iteration-1/` (git-ignored; review pages `out/evals/iteration-1/review.html` and `out/evals/iteration-2/review.html`, each run with `grading.json`, `response.md` and `friction.md`). Main fixes, by skill:
   - agent-profile: write the file once name and brokerage are known; keep the agent's color name; updates in place.
   - market-profile: named values saved first; listing fee = listing side only; title fees merge fee by fee; `from_profile` in the check.
   - contract-timeline: per-deadline `time` / `rollover` (TREC option period), closing date optional for quick questions, `moved` list for amendments, rider words matched whole ("va" in "private" was read as a VA rider).
   - seller-offer-review: state from an address without ZIP; zero transfer tax reads as none; market deposit norm; certainty-priority sellers aren't countered for < 1%; honest counter wording.
   - buyer-offer-strategy: stronger option recommended when it lifts the outlook inside every limit; insurance quote "planned", not claimed; honest reasons; `rate` must be a percent; `tax_rate`; checked boxes print.
   - CMAs: seller nets without brokerage terms refuse to render; `{median_adjusted}` filled on page 1; examples' unsupported facts removed and marked tone-only; subject's own export rows surfaced (a current listing is raised first); `--mls`.
5. **Docs and version:** migration-plan status, development.md (evals), skill-guidelines, manifests at 0.2.0 (validated).

6. **Style and compliance pass:** Spanish support removed (English only); no em dashes in prose (lone em dashes for empty values are fine) and Title Case labels across every output (`make style-check`); a Guardrails section at the top of every SKILL.md; fair housing rules in `shared/references/fair-housing.md`, synced into the five skills that write client prose; `shared/prose.py` stops a render on an em dash in a sentence or a clear fair-housing phrase; `fair_housing.extra_protected_classes` in market profiles; one fair-housing eval each for buyer-cma, seller-cma, seller-offer-review, buyer-offer-strategy and agent-profile (not run yet).

## Open items (judgment calls and smaller gaps from the evals)

- **Broker review of `shared/references/fair-housing.md`** before release: it applies HUD's rules as the skills understand them and is not legal advice.
- **Fair-housing evals** (the new id in each of the five skills above) haven't been run; include them in iteration 2.

- **Eval anchoring:** the CMA example reports and the CMA evals use the same property (517 Hickorywood). Runners noticed and rebuilt from the inputs, but a second example property (or evals on a different home) would test the skills more honestly.
- **Loose judgment rules** that make runs vary: time adjustments (1–2% per quarter), undocumented-systems adjustments, expected sale per pricing option. method.md now anchors the expected sale on the adjusted comps; the rest is still judgment.
- **Page-1 dot plot labels** can overlap the price line; there's no setting to move them (the scatter has `side`).
- **Seller review backup counter:** the plan can show a backup counter at list that would net more than the recommended offer (it's conditional on the first offer failing); consider wording it as "if B falls through".
- **Rent-back / occupancy terms** in an offer aren't scored; record them as custom `flags` for now.
- **Texas title rates** below $100k are a lookup table; the per-$1,000 tier format approximates them.
- **State holidays** (Texas) aren't in the built-in holiday list; add them to a deal's `rules.holidays`.
- **Files blocked without commission:** outside Florida, seller-cma won't build the PDF or deck until the agent gives brokerage terms (by design; the chat summary says "pending brokerage terms"). Confirm this is the behavior you want.
- **Escalation cap vs. the CMA's walk-away:** buyer-offer-strategy can set a cap above a buyer CMA's walk-away price without comment; it should say so.
- **Unknown seller credit** on a comp is recorded as 0 in the handoff.
- **Deck slide 6** (market stats): long values can overlap their period label; keep values short.
- **Eval set:** the grader's expectations could be copied into `evals.json` as assertions for iteration 2.
- **Rounding:** seller-cma display rounds a few half-dollar amounts differently line to line (cosmetic).

## Audit 2026-09-23

[The audit](audits/2026-09-23.md) found 24 High, 62 Medium and 57 Low items. Its product gaps are in [roadmap.md](roadmap.md). Rules marked Verify are checked in [the verification note](audits/2026-09-23-verification.md) before they're fixed. Fixes land one theme per commit, with the IDs in the message, and a minor version bump closes each phase. When a theme lands, list its fixed IDs here; any ID left out on purpose goes under Won't Fix with the reason.

| Phase | Version | Themes | IDs | Status |
|---|---|---|---|---|
| 0. Baseline | | Commit the in-progress work, roadmap, verification note | | Done |
| 1. High and contract rules (done 2026-09-24, validated) | 0.3.0 | Crashes | OFR-1, CMA-1, CMA-13, CMA-19, CMA-21, OFR-22 | Done |
| | | Profile merge, no silent Florida | CORE-1, CORE-2, CORE-8, TL-4, CORE-10, CORE-24 | Done |
| | | FR/BAR dates | TL-1, TL-2, TL-3, TL-5 to TL-13, TL-18, TL-23 | Done |
| | | Escalation and appraisal | OFR-2 to OFR-5, OFR-17, OFR-27 | Done |
| | | Contract form routing (AS IS vs. Standard never mix) | OFR-33 (new) | Done |
| | | Offer plan wording | OFR-6, OFR-21 | Done |
| | | Money lines | CORE-5, CORE-6, CORE-18, CMA-3, CMA-4, CMA-18, OFR-13, OFR-14 | Done |
| | | Computed comp adjustments | CMA-2 | Done |
| | | Disclaimers, brokerage, EHO | CORE-3, CORE-4, CMA-16, FH-6 | Done |
| | | Fair-housing check | FH-1, FH-2, FH-3 | Done |
| | | Condo and flood | CMA-5, CMA-6, OFR-26 | Done |
| 2. Medium | 0.4.0 | Market data and checks | CORE-7, CORE-9, CORE-11 to CORE-17, CORE-19 (warning), CORE-20, CORE-21 | Open |
| | | CMA method and charts | CMA-7 to CMA-12, CMA-14, CMA-15, CMA-17, CMA-20, CMA-22 | Done |
| | | Offer pricing and programs | OFR-7 to OFR-12, OFR-18, OFR-25, OFR-30 | Done |
| | | Offer benchmarks and review UX | OFR-15, OFR-16, OFR-20, OFR-24, OFR-28 | Done |
| | | TREC and other forms (TREC 20-19, current since July 1, 2026) | OFR-19, TL-15, TL-24 | Open |
| | | Timeline wording and outputs | TL-14, TL-16, TL-17, TL-19, TL-21, TL-22, TL-25 | Open |
| | | Fair housing and design | FH-4, FH-5, DS-1 to DS-4 | Open |
| 3. Low, docs, tooling | 0.5.0 | Skills | CORE-22 to CORE-29, CMA-23 to CMA-32, OFR-23, OFR-29, OFR-31, OFR-32, TL-20 | Open |
| | | Docs and tooling | DOC-1 to DOC-14 (DOC-13 needs a license and remote) | Open |
| 4. Evals | | Iteration 2 on the new fixtures, plus the fair-housing evals | | Open |

Fixed: OFR-1, CMA-1, CMA-13, CMA-19, CMA-21, OFR-22, CORE-1, CORE-2, CORE-8, CORE-10, CORE-24, TL-1 to TL-13 (TL-4 with the profile theme), TL-18, TL-23, OFR-33, OFR-2 to OFR-5, OFR-17, OFR-27, OFR-6, OFR-21, CORE-5, CORE-6, CORE-18, CMA-3, CMA-4, CMA-18, OFR-13, OFR-14 (and Collier from CORE-7), CMA-2, CORE-3, CORE-4, CMA-16, FH-6, FH-1, FH-2, FH-3, CMA-5, CMA-6, OFR-26, CORE-7, CORE-9, CORE-11 to CORE-17, CORE-19 (warning only; the tiered model is on the roadmap), CORE-20, CORE-21, CMA-7 to CMA-12, CMA-14, CMA-15, CMA-17, CMA-20, CMA-22, OFR-7 to OFR-12, OFR-18, OFR-25, OFR-30, OFR-15, OFR-16, OFR-20, OFR-24, OFR-28.

CORE-5 note: who pays the buyer's broker is expressed by the percentages rather than a separate `buyer_broker_paid_by` field: the seller side models what the seller pays (0 when the buyer pays), and the buyer side counts the rest of the buyer's agreement as a "Buyer's Broker Fee (Not Paid by Seller)" line.

Removed with OFR-4: the seller review's "fallback counter" for cash-short buyers. With appraisal risk measured from the CMA high, the main counter already prices at the top of the range with no gap request, so the fallback could no longer trigger.

Found while verifying (not in the audit): the FR/BAR forms set no time of day, so a rolled deadline runs to the end of the next business day, not 5:00 PM (fixed with TL-1); Brevard is Space Coast MLS, not Stellar; Lee and Charlotte are seller-pay counties; Texas legal holidays exclude Columbus Day (Phase 2); the FR/BAR Standard form has no inspection cancel right and seller repair limits, so the timeline now models its repair windows and OFR-33 tracks the offer engine's missing repair reserve.

Won't fix: (none yet).

## Remaining work, in order

1. **Audit fixes**, phases 1 to 4 above.
2. **User testing** in claude.ai and Cowork: `make package` → upload `dist/*.zip` (claude.ai) or add the marketplace (Cowork). The user will give feedback after this pass.
3. **Evals iteration 2** after the user's feedback (the audit's phase 4 covers the changed skills): re-run the changed skills with [dev/evals/RUNNER.md](../dev/evals/RUNNER.md), compare with iteration 1 (`--previous-workspace`).
4. **Yearly refreshes:** Florida millage when the year's rates are final (October); loan limits in `shared/markets/loan-limits.md` when FHFA and HUD publish the next year's (late November); the indexed homestead exemption in `fl.md` (January).
5. **Later / optional:** New skills and scope extensions (more state and MLS layers, the offer outcome log, trigger-description optimization) are in [roadmap.md](roadmap.md).

## Decisions worth remembering (details in the docs)

- Skills must be self-contained; `shared/` is copied into each skill's `scripts/_shared/` by `make sync` and committed.
- Markdown output comes from `assets/` templates filled by Claude; scripts only do math, parsing, validation and PDF/PPTX rendering.
- Every skill has markdown and file modes from the same data JSON; core profile skills are markdown only.
- Brand colors from the agent profile (one primary or buyer/seller split); status colors fixed; subject accents distinct from brand.
- Agent profile: only name and brokerage required; never print placeholders. No logos on reports.
- Market data in layers: state (FL) and MLS (Stellar, FL + PR) are separate; never fill Florida values for other states; each value carries its source. Per-deal costs go in the deal's data file.
- Every `*_pct` is a fraction (0.025 = 2.5%); interest `rate` is a percent.
- Offer skills consume `cma-handoff v1` (JSON file, or fenced markdown block, else extract and confirm).
- No commissions are built in (negotiable, not set by law): they come from the deal or the agent's market profile (marked "Standard Terms"). A seller-facing net is never shown without them: seller-cma refuses to render without brokerage terms.
