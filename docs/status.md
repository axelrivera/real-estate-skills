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

## In flight when the session ended (background agents, uncommitted)

Agents worked in git worktrees under `.claude/worktrees/` (git-ignored). Their files survive on disk even if the agents stopped. **Check each worktree before redoing anything.**

1. **Offer skills** — worktree `.claude/worktrees/agent-a8a315f56fe9bace2` (based on `eff6683`). Building `shared/offer_engine.py`, `plugins/transactions/skills/seller-offer-review/`, `plugins/transactions/skills/buyer-offer-strategy/`, fixtures, tests, evals. At handoff it had `shared/offer_engine.py`, most of `seller-offer-review`, and its fixtures; `buyer-offer-strategy` may be missing or partial.
2. **Seller CMA** — worktree `.claude/worktrees/agent-a5b7d456f9c94adf2` (based on `7f4d903`). Building `plugins/transactions/skills/seller-cma/` (PDF + PPTX deck from `build_deck.js`), fixture `dev/fixtures/seller-cma/`, tests, evals. It had just started at handoff.
3. **Eval smoke runs** (read-only, results were going to the session scratchpad, likely lost): contract-timeline eval 1, agent-profile eval 2, market-profile eval 2. Re-run them if needed.

### How to recover the worktrees

```
git worktree list
git -C .claude/worktrees/<name> status --short
```

- Review the files (read the SKILL.md, scripts, tests; render the fixtures and look at the PDFs/PPTX).
- Bring the new files into `main` by copying them over (the worktree branches are based on older commits, so copy rather than merge): new skill folders, `shared/offer_engine.py`, `dev/fixtures/<skill>/`, `dev/tests/test_*.py`, `dev/evals/<skill>/`. **Don't** copy the worktrees' `scripts/_shared/` folders or their `shared/*.py` other than new modules; run `make sync` on `main` instead.
- The offers worktree predates `finance.seller_net` returning `lines` and the Florida transfer-tax label change ("Documentary stamp tax on the deed (0.70%)"); fix any test that asserts on the old "Deed transfer tax" label, prefer `lines` keys.
- Then: `make sync && make test && make check-sync && make outputs`, review outputs, commit, and `git worktree remove` the worktrees.
- If a worktree is empty or unusable, rebuild that skill yourself following the `buyer-cma` pattern.

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
