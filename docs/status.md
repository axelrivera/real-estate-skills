# Status and handoff

Where the work stands, what's in flight, and what's left. Last updated 2026-09-23 at commit `7f4d903`. Read this first when resuming, together with [CLAUDE.md](../CLAUDE.md), [architecture.md](architecture.md), [skill-guidelines.md](skill-guidelines.md), [development.md](development.md) and [migration-plan.md](migration-plan.md).

## Done (committed on `main`)

| Area | What |
|---|---|
| Scaffold | Marketplace (`core`, `transactions`), docs, CLAUDE.md, Makefile, `.venv` + nvm dev env pinned to sandbox versions, pre-commit sync check |
| Runtimes | claude.ai and Cowork only (desktop app + cloud). Claude Code is not a target. See [runtime-support.md](runtime-support.md) |
| `shared/` | `design` (brand palette, named colors), `profiles` (agent/market profiles, state + MLS layers, value sources), `markets/states/fl.md` (Florida: costs, 2025 millage for 7 Central FL counties, contract rules), `markets/mls/stellar.md` (formats, coverage FL + PR), `render` (output location, HTML→PDF, `render.py` CLI with `--agent/--market/--sample`), `report.css`, `dates`, `finance` (payments, programs, tax, title, `seller_net` with keyed `lines`), `handoff` (cma-handoff v1), `mls` (export reader via market column map, stats, trend), `cma` + `cma.css` (CMA report pieces) |
| `core` plugin | `agent-profile` (template + `references/brand-colors.md` + `extract_colors.py` + `check_profile.py`), `market-profile` (template + `references/fields.md` + `check_market.py`) |
| `transactions` | `contract-timeline` (FR/BAR + other contracts, matches prototype dates exactly), `buyer-cma` (numbers match prototype sample exactly; English/Spanish; writes `.cma.json` handoff) |
| Tests | `make test`: 124 passing. `dev/tests/skill_import.py` loads each skill's scripts without module-name clashes; every skill test must use it |
| Evals | `dev/evals/<skill>/evals.json` for agent-profile, market-profile, contract-timeline, buyer-cma (not yet run through the skill-creator loop) |

## Step 1 done: worktrees merged (2026-09-23)

Offer skills (`seller-offer-review`, `buyer-offer-strategy`, `shared/offer_engine.py`) and `seller-cma` copied from the worktrees into `main`, reviewed (PDFs and deck rendered and checked), committed per skill; worktrees removed. Changes on the way in: the offer engine reads `finance.seller_net` `lines` only (label matching removed); a missing transfer tax asks for "the local transfer tax (or confirm there is none)"; seller-cma fixture prose matches the synthetic export (33 sales, 95.2%).

## Step 2 done: shared changes decided (2026-09-23)

| Proposal | Decision |
|---|---|
| `render.main` extra args + partial formats | Done: `extra_args` (values in `ctx`), `errors` (plain messages), `ctx["formats"]`, other formats still saved when one fails. Offer skills and seller-cma use it; buyer-cma and contract-timeline pass `errors` |
| Concession cap at exactly 25% down | **Kept 9%**: Fannie Mae goes by LTV (≤75% LTV → 9%), so 25% down is 9%; the prototype's 6% was wrong. Comment in `finance`, wording fixed in buyer-cma's offer-plan.md |
| Buyer insurance estimate | Done: `buyer_costs.insurance_rate` (Florida 0.9%) for buyer payments; `holding_costs.insurance_rate` 0.7% stays for the seller's holding cost. In fields.md, template, check_market |
| Design party tints / light neutral | Party tints done (`party_tints` → `--party-both-bg`, `party_both_soft`); seller-cma render and deck use them. Light neutral not needed (hollow markers are white on the chart) |
| Scatter label `above` | Done: subject label and callouts take `left`/`right`/`above`/`below` |
| `seller_net` structured assumptions + title-fee override | Done: `assumed` is `[{key, value, text}]` incl. built-in title fees; `title_fees=` override (seller-cma `costs.title_fees`); deal-level costs count as the agent's |
| Percent vs. fraction | Done: every `*_pct` is a fraction everywhere (CMAs converted: `down_pct`, brokerage); `finance.fraction` refuses 1+ with a plain message; offer files checked too. Interest `rate` stays a percent. Rule in architecture.md |
| Docs | `offer_engine.py` in development.md; per-deal costs and the fraction rule in architecture.md |

## Step 3 done: earlier eval findings fixed (2026-09-23)

All findings from the agent-profile, contract-timeline and market-profile smoke runs are fixed (commits "agent-profile / contract-timeline / market-profile: fix eval findings"). Also found and fixed: contract-timeline rider matching treated "va" inside words like "private" as a VA rider.

## Remaining work, in order

1. **Recover/finish the offer skills** (`seller-offer-review`, `buyer-offer-strategy`) and `shared/offer_engine.py`. Requirements: prototype engine ported once (shared), Florida hard-coding replaced by market profile + `shared/finance`, never-block-on-missing-data with Preliminary labels, CMA handoff consumed via `shared/handoff`, buyer side themed "buyer" (prototype wrongly used orange), analysis script prints formatted JSON, markdown via `assets/*-template.md`, PDFs via `render.py`, Offer Package Worksheet for buyer side. Prototypes: `sources/Prototype Skills/offer-analysis-pdf/`, `buyer-offer-builder/`, sample PDFs `Test1_*.pdf`, `Test2_*.pdf`, `Test3_*.pdf`, `Offer_Package_Worksheet_Sample.pdf`.
2. **Recover/finish `seller-cma`** (PDF + deck). Requirements in the seller agent brief: net sheet via `finance.seller_net` (brokerage from agent terms or market defaults 2.5%+2.5%, labeled), buyer payments per list price, seller handoff with `recommended_list_price`, subject accent = theme `party.both` (never brand), deck colors from `design.pptx_colors`, no hard-coded Florida text in the deck, node run with `NODE_PATH` incl. `npm root -g`, deck QA via `soffice` instead of `/mnt/skills`. Prototype: `sources/Prototype Skills/seller-cma-pdf/`, samples `517-Hickorywood-Seller-CMA.pdf`, `517-Hickorywood-Listing-Presentation.pptx`.
3. **Evals (skill-creator loop)** for every skill: run each `dev/evals/<skill>/evals.json` prompt with the skill (subagents, local venv, `OUTPUT_DIR` to a scratch folder), fix SKILL.md/references where runs stumble. Baselines optional. Load the `anthropic-skills:skill-creator` skill for the procedure.
4. **Docs pass**: `docs/migration-plan.md` status table, `docs/plugins.md`, README, marketplace/plugin versions (bump to 0.2.0 when all skills land), remove "needs a run" notes after testing.
5. **User testing** in claude.ai and Cowork: `make package` → upload `dist/*.zip` (claude.ai) or add the marketplace (Cowork). The user said they'll give feedback at the end of the full pass.
6. **Later / optional**: trigger-description optimization (skill-creator `run_loop`, Claude Code only), more states' market layers, more MLS layers, refresh Florida millage when 2026 rates are final (October 2026).

## Decisions worth remembering (details in the docs)

- Skills must be self-contained; `shared/` is copied into each skill's `scripts/_shared/` by `make sync` and committed.
- Markdown output comes from `assets/` templates filled by Claude; scripts only do math, parsing, validation and PDF/PPTX rendering.
- Every skill has markdown and file modes from the same data JSON; core profile skills are markdown only.
- Brand colors from the agent profile (one primary or buyer/seller split); status colors fixed; subject accents distinct from brand.
- Agent profile: only name and brokerage required; team optional; never print placeholders. Brand colors from hex codes, a website or an image; confirm by name. No logos on reports. Don't ask about brokerage rules.
- Market data in layers: state (FL) and MLS (Stellar, FL + PR) are separate; never fill Florida values for other states; county overrides; each value carries its source.
- Florida defaults researched 2026-09: seller title fees itemized ($1,145), brokerage 2.5% + 2.5%, 2025 millage for Orange, Seminole, Osceola, Lake, Volusia, Polk, Sumter.
- Offer skills consume `cma-handoff v1` (JSON file, or fenced markdown block, else extract and confirm).
