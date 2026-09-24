# Status and handoff

Where the work stands and what's left. Last updated 2026-09-23 (version 0.2.0). Read this first when resuming, together with [CLAUDE.md](../CLAUDE.md), [architecture.md](architecture.md), [skill-guidelines.md](skill-guidelines.md), [development.md](development.md) and [migration-plan.md](migration-plan.md).

## Done (committed on `main`)

| Area | What |
|---|---|
| Scaffold | Marketplace (`core`, `transactions`) at 0.2.0, docs, CLAUDE.md, Makefile, `.venv` + nvm dev env pinned to sandbox versions, pre-commit sync check |
| `shared/` | `design`, `profiles` + `markets/` (Florida state layer, Stellar MLS layer), `render`, `report.css`, `dates`, `finance`, `handoff` (cma-handoff v1), `mls`, `cma` + `cma.css`, `offer_engine`. See [development.md](development.md#shared-code) |
| `core` | `agent-profile`, `market-profile` (markdown only) |
| `transactions` | `contract-timeline`, `buyer-cma`, `seller-cma` (PDF + deck), `seller-offer-review`, `buyer-offer-strategy` |
| Tests | `make test`: 203 passing. Every fixture renders with `make outputs` (16 PDFs and decks) |
| Evals | Iteration 1 run for all 7 skills (21 prompts), fixes applied. Runner: [dev/evals/RUNNER.md](../dev/evals/RUNNER.md); procedure in [development.md](development.md#evals) |

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
4. **Evals, iteration 1:** results in `out/evals/iteration-1/` (git-ignored; review page `out/evals/iteration-1/review.html`). Main fixes, by skill:
   - agent-profile: write the file once name and brokerage are known; keep the agent's color name; updates in place.
   - market-profile: named values saved first; listing fee = listing side only; title fees merge fee by fee; `from_profile` in the check.
   - contract-timeline: per-deadline `time` / `rollover` (TREC option period), closing date optional for quick questions, `moved` list for amendments, rider words matched whole ("va" in "private" was read as a VA rider).
   - seller-offer-review: state from an address without ZIP; zero transfer tax reads as none; market deposit norm; certainty-priority sellers aren't countered for < 1%; honest counter wording.
   - buyer-offer-strategy: stronger option recommended when it lifts the outlook inside every limit; insurance quote "planned", not claimed; honest reasons; `rate` must be a percent; `tax_rate`; checked boxes print.
   - CMAs: seller nets without brokerage terms refuse to render; `{median_adjusted}` filled on page 1; examples' unsupported facts removed and marked tone-only; subject's own export rows surfaced (a current listing is raised first); `--mls`; Spanish footer and units.
5. **Docs and version:** migration-plan status, development.md (evals), skill-guidelines, manifests at 0.2.0 (validated).

## Open items (judgment calls and smaller gaps from the evals)

- **Eval anchoring:** the CMA example reports and the CMA evals use the same property (517 Hickorywood). Runners noticed and rebuilt from the inputs, but a second example property (or evals on a different home) would test the skills more honestly.
- **Loose judgment rules** that make runs vary: time adjustments (1–2% per quarter), undocumented-systems adjustments, expected sale per pricing option. method.md now anchors the expected sale on the adjusted comps; the rest is still judgment.
- **Page-1 dot plot labels** can overlap the price line; there's no setting to move them (the scatter has `side`).
- **Seller review backup counter:** the plan can show a backup counter at list that would net more than the recommended offer (it's conditional on the first offer failing); consider wording it as "if B falls through".
- **Rent-back / occupancy terms** in an offer aren't scored; record them as custom `flags` for now.
- **Texas title rates** below $100k are a lookup table; the per-$1,000 tier format approximates them.
- **State holidays** (Texas) aren't in the built-in holiday list; add them to a deal's `rules.holidays`.
- **Chat templates** are English only (buyer-cma's PDF is bilingual); Claude translates the chat reply.
- **Rounding:** seller-cma display rounds a few half-dollar amounts differently line to line (cosmetic).

## Remaining work, in order

1. **User testing** in claude.ai and Cowork: `make package` → upload `dist/*.zip` (claude.ai) or add the marketplace (Cowork). The user will give feedback after this pass.
2. **Evals iteration 2** after the user's feedback: re-run the changed skills with [dev/evals/RUNNER.md](../dev/evals/RUNNER.md), compare with iteration 1 (`--previous-workspace`).
3. **Later / optional:** trigger-description optimization (skill-creator `run_loop`, Claude Code only), more states' market layers, more MLS layers, refresh Florida millage when 2026 rates are final (October 2026), port the prototype's offer outcome log.

## Decisions worth remembering (details in the docs)

- Skills must be self-contained; `shared/` is copied into each skill's `scripts/_shared/` by `make sync` and committed.
- Markdown output comes from `assets/` templates filled by Claude; scripts only do math, parsing, validation and PDF/PPTX rendering.
- Every skill has markdown and file modes from the same data JSON; core profile skills are markdown only.
- Brand colors from the agent profile (one primary or buyer/seller split); status colors fixed; subject accents distinct from brand.
- Agent profile: only name and brokerage required; never print placeholders. No logos on reports.
- Market data in layers: state (FL) and MLS (Stellar, FL + PR) are separate; never fill Florida values for other states; each value carries its source. Per-deal costs go in the deal's data file.
- Every `*_pct` is a fraction (0.025 = 2.5%); interest `rate` is a percent.
- Offer skills consume `cma-handoff v1` (JSON file, or fenced markdown block, else extract and confirm).
- A seller-facing net is never shown without the commission: seller-cma refuses to render without brokerage terms.
