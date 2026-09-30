# Status and handoff

Where the work stands and what's left. Last updated 2026-09-29 (version 0.12.0: contract fixes from the mock-package evals and the pre-release audit; 0.11.0 was never released on its own and ships inside the 0.12.0 release; 0.11.0: full FR/BAR contract support, riders and addenda, best effort for every other contract; 0.10.2: outlier-proof trend line; 0.10.1: quieter scatterplot background; 0.10.0: the listing presentation with a PDF copy, measured layout and copy that follows the listing, one-hue brand palette; 0.9.0: project instructions and the agent guide; 0.8.0: the MLS 360 property report as the subject input, no JSON handed to agents, seller CMA builds the PDF unless the presentation is asked for; 0.7.0: one onboarding skill and one profile file; one plugin, `real-estate`, in repo `real-estate-skills`; audit Phases 1 to 3 done). Read this first when resuming, together with [CLAUDE.md](../CLAUDE.md), [architecture.md](architecture.md), [skill-guidelines.md](skill-guidelines.md), [development.md](development.md) and [migration-plan.md](migration-plan.md).

## Done

| Area | What |
|---|---|
| Scaffold | One plugin (`real-estate`, repo root) in the one-plugin marketplace `real-estate-skills` at 0.12.0, docs, CLAUDE.md, Makefile, `.venv` + nvm dev env pinned to sandbox versions, pre-commit sync check |
| `shared/` | `design`, `profiles` + `markets/` (Florida state layer, Stellar MLS layer, national estimates), `render`, `report.css`, `dates`, `finance`, `handoff` (cma-handoff v1), `mls`, `cma` + `cma.css`, `offer_engine`, `contract_forms` (FR/BAR AS IS vs. Standard and rider routing, verified revisions, chat-only support notes), `prose` (em dash and fair-housing check), `references/` (`fair-housing.md`, `condo.md`, `saved-files.md`, the FR/BAR library `frbar-contract.md`, `frbar-riders.md`, `frbar-addenda.md`, `frbar-package-check.md`, and `other-contracts.md`). See [development.md](development.md#shared-code) |
| Profile | `agent-profile` (markdown only): a two-round interview that saves one file, `profile.md` (who the agent is), in `.claude/real-estate/` in the Cowork working folder (`shared/references/saved-files.md`). `market-profile` was removed on 2026-09-24 |
| Deal work | `contract-timeline`, `buyer-cma`, `seller-cma` (PDF + deck), `seller-offer-review`, `buyer-offer-strategy` |
| Tests | `make test` (799 on 2026-09-30, 3 slow mock-contract checks skipped unless `RUN_SLOW=1`; the deck-PDF check runs when LibreOffice is installed); golden snapshots of every fixture (`make golden`); `make package` runs every check first. Every fixture in `dev/fixtures/` renders with `make outputs` |
| Evals | 37 prompts across the 6 skills (agent-profile 7, buyer-cma 3, buyer-offer-strategy 4, contract-timeline 10, seller-cma 6, seller-offer-review 7), including 8 on mock FR/BAR packages and 5 fair-housing prompts. Iteration 1: 92% of expectations. Iteration 2 (audit 2026-09-29, all 36 then): 227/257 (88.3%), 27 of the 30 failures from eval definitions, since fixed. Iteration 3 (after the first fixes): 240/254 (94.5%); its findings are fixed in the second pass ([audit](audits/2026-09-29.md#second-pass-eval-iteration-3-2026-09-29)). Iterations 4 and 5: 252/261 (96.6%) and 254/261 (97.3%), with fixes after each ([audit](audits/2026-09-29.md#third-pass-eval-iterations-4-and-5-2026-09-29-to-09-30)). Runner: [dev/evals/RUNNER.md](../dev/evals/RUNNER.md); procedure in [development.md](development.md#evals) |

## This pass (2026-09-30): Fourth Audit Pass From the Targeted Iterations 6 and 7, Still Version 0.12.0

Details in [the audit](audits/2026-09-29.md#fourth-pass-targeted-iterations-6-and-7-2026-09-30). Iteration 7 re-ran the four evals iteration 6 missed: 31/31. What agents will notice:

- **buyer-offer-strategy:** the reply always carries the lines that matter (why listing agents want one flat number, and that option fees come from your contract outside Florida); the mortgage rate is the latest Freddie Mac weekly rate unless you give one; a deadline you give as a weekday is turned into a date and confirmed.
- **seller-offer-review:** with Rider GG and no amount, you're asked for the signed compensation agreement; weekend dates roll per the contract; the "Respond By" box names an offer the plan acts on; outside Florida you can give the tax rate.
- **contract-timeline:** lender estimates are never starred; notes say "not given" unless a blank was seen on the signed copy.
- **Both CMAs:** comp addresses print in normal capitalization; the seller's reprice shows the listing's price history; the buyer's cash warning names the credit option that fits.
- **From iteration 7:**
  - **seller-offer-review:** a counter never promises inspection reports the buyer is ordering; an appraisal gap window that runs to closing is flagged; a November or December closing says the tax bill is assumed unpaid and names the early-payment discount.
  - **buyer-offer-strategy:** outside Florida, the chat note fits an offer still being written, the 10-day inspection or option period is marked as a default to check locally, and the deposit-at-risk date asks you to confirm it against your contract; page 1 no longer overflows when only one option shows.
  - **buyer-cma:** page 1 points to the credit option that fits when cash runs short; one outlying comp no longer sets an end of the range; "about", never "~".
  - **seller-cma:** a listing that ended unsold more than 12 months ago is history, not a price cap; page 1 and the pricing table show nets after holding costs, the same basis as the reply and the deck; a reprice's Stay price is filled by the rule on the first run.
  - **Both CMAs:** a chart callout for a home the chart doesn't plot is named instead of dropped silently.


Fixes for what two more full eval runs found; details in [the audit](audits/2026-09-29.md#third-pass-eval-iterations-4-and-5-2026-09-29-to-09-30). What agents will notice:

- **Profile:** questions come in one fixed order (confirmations first), the licensed brokerage name is checked before colors, and the "try it" line waits until that name is settled.
- **buyer-offer-strategy:** a likely-pushback answer never goes past your buyer's limits; closing dates skip holidays; a "Stronger" option that gains nothing is left out; page 1 says when a payment limit rests on an assumed rate; an insurance premium you give counts as a quote; outside Florida the report uses generic contract wording.
- **seller-offer-review:** the quick answer names every estimated cost; a counter never changes a term nobody gave; deal risks come before the flood-disclosure reminder; counters restate the loan and balance and answer a changed closing date; a rent-back shows on the closing term; a "Terms Reason" field records why offers rank as they do; the plan always says only one counter or acceptance goes out at a time.
- **contract-timeline:** an Additional Deposit given only as a number now gets its deadline (it was dropped before); "before closing" dates that roll closer to closing get a safe date; Rider H by box, unknown flood zones, Rider U and T agreements marked critical; the calendar leaves out lender targets unless asked; amendments are named by their form.
- **buyer-cma:** cash to close shows for every payment scenario, with a warning when the buyer's cash is short or tight; price cuts, days on market and the last contract price come from the script; long replies cut in a fixed order.
- **seller-cma:** relisting a home whose listing expired never prices above the failed price without a reason; staying at the current price on a reprice follows a rule; the presentation's net slide adds up; page layout problems are caught from the printed PDF.
- **Dev only:** mock answer keys carry named amendments, pre-approval caps, verified proof of funds and more; evals that graded things a prompt never asked for were reworded.


Fixes for everything eval iteration 3 found; details in [the audit](audits/2026-09-29.md#second-pass-eval-iteration-3-2026-09-29). What agents will notice:

- **Profile:** never more than three questions in a message; a question about costs gets one line (5% total commission by default, your numbers per report); a franchise name is saved as typed and the licensed brokerage name confirmed; a rewritten Voice is shown for your okay before it's saved.
- **buyer-offer-strategy:** the seller's tax proration uses the same rate as the buyer's payment; the county is found from the city; the offer deadline reads like a date; when an option is missing the report says why; the worksheet has the Rider E repair cap; "Deposit at Risk After" no longer counts the FHA appraisal protection, which gets its own row; the fair-housing reference explains buyer letters and a terms-only cover note.
- **seller-offer-review:** declined offers say why in terms of certainty or downside; costs follow the contract form when the address has no state; commission shows one way when the listing broker pays; the headline reads "Counter the $382K FHA Offer"; a buyer's counter that changes the closing date or leaves deposit, loan and balance out of step with the price is flagged; the walk-away date covers every open window, AGA-1 included; a "quick net sheet" reply.
- **contract-timeline:** the next deadline is the earliest critical contract deadline (never a lender target); deposits, loan and balance are checked against the price and the pre-approval; amendment changes read in plain labels; the header lists riders on AS IS contracts too; a quick date question with no day count gets both counts.
- **buyer-cma:** price cuts, increases and days on market are counted from the history, not by hand; a gut check gives a rough range with an opening, target and walk-away; the payment is shown at the target price, with a warning when the buyer's cash falls short.
- **seller-cma:** a reprice says "New List Price" and offers staying put or cutting, never raising; a November or December closing assumes the tax bill unpaid unless you say it's paid; the holding cost states its loan rate; outside Florida the HOA line reads "HOA Documents"; LibreOffice is found in the Applications folder.
- **Both CMAs:** chart labels step off markers and each other, and a chart that nearly fits shrinks instead of leaving half a page empty.
- **Dev only:** mock answer keys carry `balance_to_close` and the original offer before a buyer counter; tests assert keys, not prose; a slow test tier; coverage measured.

## This pass (2026-09-29): Pre-Release Audit Fixes, Still Version 0.12.0

The full audit before shipping ([audits/2026-09-29.md](audits/2026-09-29.md)) found 6 High, about 40 Medium and about 60 Low items; all are fixed in this pass unless listed under Won't Fix there. 0.11.0 was never released on its own: the 0.12.0 release carries both. **Breaking for agents who relied on it:** the Texas contract rules (TREC rows, option fee, Texas holiday calendar) were removed in 0.11.0; every contract outside FR/BAR is now best effort. What agents will notice:

- **Fair housing:** the check before any file is written now also stops pregnancy and children ("expecting their first baby"), marital status and religion tied to people ("attend the church", "church community"), while "near a church" or "Church Street" still pass. The profile's Voice and Disclaimers are checked too.
- **Offer pricing:**
  - An escalation cap below the offer's own price no longer lowers the price.
  - A seller's last counter is the ceiling even above list, and a buyer counter between list and it meets partway.
  - Without a CMA, an offer above list is never countered down: the price stands and the counter asks for appraisal-gap coverage.
  - Every counter has a Time for Acceptance row, including the one that revives an expired offer.
- **buyer-offer-strategy:** options are scored alone (not against each other); dates count from the expected Effective Date (new optional `expected_effective_date`); the built-in city millage is used; AGA-1 is never written for USDA; an escalation above value comes with AGA-1 rather than a promise; the Stronger option names only what it changed.
- **seller-offer-review:** title fees follow the Para. 9(c) box (including (iii), Miami-Dade and Broward); a missing box, tax rate or contract form is flagged at the right impact; a free rent-back counts; Rider K's walk-away date is its inspection end; the HOA line uses each state's name; lapsed offers are described as facts, not legal conclusions.
- **Both offer skills:** the default inspection period is the form's 15 days; FR/BAR form names written differently are still recognized; AGA-1 windows stop at closing; a CMA for another home is flagged; the CMA handoff now carries the home's tax, flood zone, HOA and roof facts, so the offer's payments match the CMA's.
- **contract-timeline:**
  - The next deadline is the first one not done and not past; passed ones show "Past, Confirm" and stay out of the calendar.
  - Rider names written with hyphens map correctly, and "Condominium Association" is Rider A; an unknown rider name gets a note.
  - Short sale approvals received late are flagged; dates that roll onto closing day are due by closing time.
  - New rows: the Rider E election to proceed, the seller's existing title evidence (9(c)), separate homeowner's and flood insurance under Rider H, the seller's copy of a short sale approval.
  - A future Effective Date or amendment gets a note, and a confirmed hypothetical is labeled What-If.
  - Calendar events carry a time zone, a daytime reminder and a sequence number, so re-imports update them.
  - No tool instructions on the PDF, and the best-effort note never reaches the markdown report.
  - Another state's contract needs only its day count; rules it doesn't state are marked to confirm, never invented.
- **CMAs:** a flood zone written "To confirm" is treated as unknown (it used to print a false insurance note); a home listed right now is confirmed first, and the agent's own listing is built as a reprice with a "Stay at Current Price" option; outside Florida the net sheet uses neutral terms; gut checks get the median before a range; an outlier rule; the examples moved to their own made-up home without agent-only remarks.
- **Profile:** an unquoted color code is caught instead of silently falling back to the default blue.
- **Guide and manual:** the agent guide covers 0.10 to 0.12, and the PDF manual is now built from it (`make manual`).
- **Dev only:** golden output tests (`make golden`), `make samples` keeps only real changes, the release checklist and the manual test kit (`make manual-kit`), packaging from tracked files only, release notes from this file, a real Python 3.11 check through uv, a fixed eval set and mock answer keys.

## This pass (2026-09-29): Fixes From the Mock-Package Evals and Version 0.12.0

- **contract-timeline:**
  - Short sales (Rider G) get a two-phase timeline: dated rows from the Effective Date, and every other period "N days after short sale approval" until `short_sale_approval_received` is set. Closing follows Para. 6, and the PDF builds without a closing date.
  - Deadlines already met (`completed`, such as a deposit shown by the escrow receipt) show as done and drop out of the calendar.
  - Holidays are named in rollover notes, the timeline strip labels no longer overlap, and the walk-through shows no 11:59 PM.
  - The inspection wording fits a condo unit, custom rows can be due "by Closing", and the report date can be set (`--date`).
  - Duplicate default notes are dropped.
  - New guidance: unexecuted offers, missing delivery evidence, a counter on the contract, and documents that disagree.
- **seller-offer-review:**
  - Expired offers are caught (Blocking, or High when delivery is unknown), and the next step never names a past date.
  - Counters never go above the seller's last counter (`prior_counters`), and a buyer counter that drops earlier terms is flagged.
  - FR/BAR Para. 9(c) sets who pays the owner's title policy.
  - The pre-approval price cap is checked, and Rider GG paid from the listing fee isn't double counted.
  - With no appraisal rider, the appraisal is part of loan approval.
  - The Standard repair reserve is exactly the limit.
  - Engine flags and hand-written issues no longer duplicate.
- **Also:** proof of funds (`proof_of_funds`) is checked against the cash the offer needs; agent-written issues replace an engine flag only when they're about the same topic; the timeline's first deadline includes rows both sides owe; a blank association approval box on Rider A or B is treated as required and flagged; a pre-approval that expires before closing is noted (timeline) or flagged Med (offer review).
- **Also in 0.12.0:** check-one boxes left blank get no default; Rider U with Para. 6(b) checked only for the rent-back; the counter shown for reference that would revive an expired offer; offer review flags a pre-approval that expires before closing; evals can set `today`.
- **Verified:** six evals re-run on mock packages (`out/evals/iteration-mock-2/`): every contract-timeline deal file matched its key on every computed deadline, including the scanned short sale before approval.
- **Both:** working files (deal and listing files) are never handed to the agent; a later conversation rebuilds them from the documents (`saved-files.md`). Shared FR/BAR references cover the EA-4 "additional days" count, counters on the contract, CO-3 acceptance, and disclosures that contradict a rider.

## This pass (2026-09-29): Mock Contract Packages (Dev Only, No Version Bump)

- **`mock-contract` skill (Claude Code, `.claude/skills/`) and `dev/mock_contracts/`:** builds a realistic FR/BAR contract package as one PDF from a scenario in chat or a file. It fills the real forms in `sources/` Dotloop-style: typed values, checkmarks, handwriting signatures and initials with "dotloop verified" stamps. The package covers a buyer-signed offer, a counter chain, an executed contract or an amended one. Rules come from `contract_forms`. Optional answer key (contract-timeline's deal file, which renders as is), scanned copy and defects. Outputs go to `out/mock-contracts/` only. Reference: [mock-contracts.md](mock-contracts.md).
- Blanks are found automatically (Dotloop field outlines, rules, checkboxes, printed line numbers), so any of the 71 forms works for parties, property, signatures and initials. Field maps name the rest, for the two contracts, Riders A, B, E, F, FF, GG, H, K, L and P, and AGA, EAC, CO, EA and ACSP. Every package carries buyer's broker compensation (Rider GG, broker to broker, by default) unless the scenario says none; with GG, the CASSB-1 compensation agreement (broker to broker or seller to broker) is written as a separate file, executed after the Effective Date inside GG's window. Packages hold what the buyer's and seller's sides exchange at each stage: the seller's disclosures (SPDR or SPDC, FD; MISIRS and RCD for condos; others by property facts) with yes/no answers filled by default, a generated pre-approval or proof of funds, and generated escrow deposit receipts. Generated letters use made-up institutions and carry a mock-document footer.
- PyMuPDF is a local-only tool (`dev/requirements-tools.txt`); `make lint-skills` fails if shipped code imports it.
- **Key matches PDF.** Every value in an answer key is printed on the package: a spec value with no blank to print it stops the build (the value guard), and a round-trip test types a sample of every mapped key and finds it on its form. New maps for Riders C, D, G, S, T, U, V, W, X and Z, CDDA-2, NMOB-1 (both now signed) and the rest of EA-4. Rider values reach the deal-file key under `frbar.md`'s names and the offer key under the listing file's. Rider V's buyer names no longer land in its sale-date blank.
- **Counter on the contract** (`counter.method: "contract"`): the seller strikes and retypes the changed terms on the contract (and the loan and balance lines a new price moves) and initials them; the buyer's last initial is the Effective Date.
- **End-to-end check:** the skill built a VA counter-on-contract package from chat and mapped an unmapped rider (Rider N, plus CCCLA-3) by itself. Eight evals ran against mock packages (contract-timeline on five executed packages including a scan, and on an unsigned offer; seller-offer-review on two offers); every deal file the runs built matched its key on every computed deadline. Fixes from the runs: Rider A's and B's approval boxes, Rider A's right of first refusal and nondeveloper disclosure boxes (image checkboxes `locate.py` missed), disclosures that follow the property's facts (HOA, sinkhole claim, CCCL), CCCLA-3 left out when Rider N waives it, and the condo starter's document date.
- **Twelve starters** (`make mock-contracts`), adding Rider FF, a seller-paid compensation agreement, a late agreement with missing initials, multiple offers with escalation, a pending buyer counter, a counter on the contract, and a short sale with a rent-back. Evals use them by name (`mock_package`, [development.md](development.md#evals)).
- `dev/samples/` moved from the made-up Harrow Springs to Casselberry (real city, made-up streets), with Casselberry's real 2025 millage; `samples/` regenerated.

## This pass (2026-09-29): Full FR/BAR Contract Support and Version 0.11.0

- **Forms on file and tracked.** The FR/BAR AS IS and Standard contracts (Rev. 2/26), all 33 CR-7 riders (A to GG) and 35 Florida Realtors addenda and disclosures are in `sources/Contracts/FARBAR/` (local only). `dev/forms/frbar-forms.json` records each form's revision, a text hash and what depends on it; `make forms-check` reports a revised, new or removed form with a diff (procedure in [development.md](development.md#updating-a-contract-form)).
- **Shared FR/BAR library** read from the PDFs: `frbar-contract.md` (both forms paragraph by paragraph), `frbar-riders.md` (every rider), `frbar-addenda.md` (every addendum and disclosure), `frbar-package-check.md` (what a package needs). The three contract skills read them; their own references now only map fields.
- **Rules fixed from the forms:** Rider K on the Standard form runs AS IS math; Rider L keeps the repair limits and adds a walk-away; riders I, K, L on an AS IS contract stop the run (RESERVED); the CRSP is no longer read as the Standard form; Rider F's appraisal date is 10 days before closing plus 3 days for notice (was 21 days); Rider H's date is the earlier of 30 days after the Effective Date or 10 before closing (was the inspection period); Rider V's sale date has no default (was 30 days); an FR/BAR gap offer uses the Appraisal Gap Addendum (AGA-1), never with Rider F.
- **New rider handling:** timeline rows for riders G, I, M, R, S, T, U, W, X, Y, Z, DD, GG, N, the condo ROFR, tenant estoppels, the title cure period and the FinCEN report; seller net lines for rent-backs (U), seller financing (C) and assessment payoffs (EE, CDD); seller flags for short sales, attorney approval, a sale contingency without a kick-out, assumptions, EE and GG; worksheet riders named by letter.
- **Every other contract is best effort:** the Texas contract rules (TREC rows, option fee, Texas holiday calendar) are gone; one shared guide, `other-contracts.md`, reads any other contract by function with no borrowed defaults. The scripts return `support` and `chat_notes`; the disclaimer goes in chat only, never in a PDF, calendar file or worksheet (tested). An FR/BAR contract on another revision gets the same chat-only note.
- **Timeline PDF:** when page 1 overflows, the details now follow on page 2 and the details table splits across pages (a five-rider deal went from 5 pages with two near-empty ones to 3).
- **Appraisal form scored, not just printed:** each FR/BAR offer's appraisal window comes from its form (`contract_forms.appraisal_form` / `appraisal_window`): Rider F runs to 10 days before closing plus 3; AGA-1 to its valuation, delivery and renegotiation periods (36 days if blank), and a cash offer with AGA-1 carries appraisal risk. In a multiple-offer review the same price and gap on AGA-1 now ranks above Rider F on a long closing; the buyer strategy scores gap options on AGA-1. AGA-1 with Rider F, on an FHA/VA offer, or without a Gap Amount is flagged.
- **Riders in the certainty score:** each rider's cancel window counts toward days until firm (`contract_forms.rider_windows`: H, I, M, S, T, U, DD, GG, Z and R; a missing Z or R date is flagged). A sale contingency with a kick-out (Rider X) scores 2, not 1. A Rider FF broker credit counts toward the loan program's concession cap in both skills; the buyer strategy pays the buyer's broker under Rider GG by default and prints it on the worksheet. A buyer who must sell is now scored with the sale contingency and kick-out the worksheet recommends. The back-up option says the back-up buyer can cancel until the seller's notice (Rider W).
- Minor: new inputs (rider fields, `form_revision`, `appraisal_form`, `buyer_broker_form`), changed defaults and new outputs.

## This pass (2026-09-26): Outlier-Proof Trend Line and Version 0.10.2

- Outliers can't skew the chart: the size-only line is fit to sales from subject size ÷ 1.6 to × 1.6 (no lower bound before), and sales priced far off a robust line (Theil-Sen, modified z-score over 3.5) are left out of the fit and off the chart. Before, one $1.1M waterfront sale moved "what size predicts" by $21K, cut the "size explains" share from 83% to 20% and stretched the price axis. Listings are dropped only when wildly off (z over 7), so a cheap competing listing stays; comp cards always stay. The note under the chart counts homes left off for size and for price. Needs 6+ sales to judge; the sample reports are unchanged.
- Patch: number fixes, no new inputs, outputs or defaults.

## This pass (2026-09-26): Scatterplot Background and Version 0.10.1

- Price vs. size chart (buyer and seller CMA PDFs, listing presentation): other sales are small, light background dots instead of squares, so stacked sales read as a denser patch rather than solid bars and outliers no longer pull the eye. Comps and the subject home draw on top. The trend line is still fit to all sales.
- PDF: other sales are 30% see-through gray circles. Deck: small pale gray dots (LibreOffice, which makes the PDF copy, ignores marker transparency), and For Sale Now is the darker gray so current competition stands out more than past sales.
- Patch: readability only, no new inputs, outputs or defaults.

## This pass (2026-09-25): Listing Presentation and Version 0.10.0

- The seller-cma deck ships with a PDF copy of the slides (LibreOffice), as a backup and a way to check the layout.
- Every slide text is measured and fitted; text that can't fit prints a `Check:` line naming the `deck` field to shorten. How We Priced It is four numbered steps plus the answer card; the scatter is bigger; appendix notes carry only the required notices, the rest in speaker notes.
- Deck copy follows the listing (tax proration and payoff exclusions, strategy count, expected sale vs. list, comps basis, no mortgage, loan program); item counts are ranges, and items name their icon.
- One hue: outputs use only the brand's shades and tints plus black and grays; other hues only for status and party coding. The subject home is black. Deck color roles are contrast-checked for light and near-black brands.
- Report fixes: no double border at the top of the multiple-offer review and Offer Options.
- Not breaking: deck content written before this still builds (neutral icons, wider counts).

## This pass (2026-09-25): Agent Guide and Version 0.9.0

- The release zip's README is the full agent guide (`dev/package/README.md`): install, profile and Project setup, the Stellar Matrix custom export with its on-screen labels and fields, the comps search, the 360 Property View, each skill with inputs and examples, best practices (a Project per transaction) and other MLS systems.
- The Stellar layer accepts the Matrix label "List Price".
- Version 0.9.0 (agent-profile's project instructions and the guide change what agents get). Versioning rules added to [development.md](development.md#versioning).

## This pass (2026-09-24): Project Instructions

- agent-profile also writes `project-instructions.md` when the interview is done (`assets/project-instructions-template.md`): a first-person prompt for a claude.ai Project's instructions or a Cowork project's Instructions. It names only the agent and points to `profile.md`, the skills, the voice and the guardrails, so profile updates never make it stale.
- The hand-over recommends a Project and gives the steps for where the agent is (claude.ai or Cowork, in a Project or not), from `references/project-setup.md`; button names checked against the Claude Help Center on 2026-09-24.
- `saved-files.md`: the instructions file is a deliverable, saved next to the profile. New eval: agent-profile #7.
- Open: run the agent-profile evals; check the setup steps in claude.ai and Cowork by hand.

## This pass (2026-09-24): Sanity Check Fixes and Best-Practice Assumptions

A regression run of every fixture and sample, commit by commit from `main`, found no math change outside the intended ones; an audit of documented commands and fields found the items below, all fixed.

- **Best-practice assumptions** (the rule for every default): the 15 states with no state transfer tax (AK, AZ, ID, IN, KS, LA, MS, MO, MT, ND, NM, OR, TX, UT, WY) get none, never the 0.4% estimate (`national.md` `no_state_transfer_tax`, source `national`, a note to confirm local taxes). The buyer's agent fee stays included (2.5%, assumed) until the deal says otherwise.
- **Millage:** codes split on "/" too (Orange); `finance.millage_row` never guesses between districts that share a code or name, and both CMAs warn.
- **Units:** `finance.check_units` refuses a `*_pct` or cost rate written as a percent and an interest rate written as a fraction, in both CMAs and every deal's costs (`Market.with_deal`).
- **buyer-cma:** stats.py takes `--sqft --pool --subdivision --type --lat --lon` for a home with no export row; `tax_jurisdiction_index` is range-checked; `export` resolves beside report.json and is in both examples.
- **Chat templates and handoffs:** compute.py prints `comps_table`; offer-review template reads `summary.kpis`; buyer-offer-strategy reads the CMA's seller-paid stats by the handoff's names.
- **Docs:** `property.costs` in the buyer file, `du_approved`, `received` not scored, `recommendation.midpoint`, `--side`, `--packet`, the Texas evals.

## This pass (2026-09-24): Seller CMA Defaults and Table Fixes

- seller-cma builds only the report PDF by default (`render.main(..., default="pdf")`); the listing presentation is built when the request asks for it, or offered in one line afterward. New eval: seller-cma #5.
- Seller pricing table: "Time to Contract" header, strategy labels on one line. Buyer offer options, Market Check: the CMA source on its own line under the value range.
- Version 0.8.0.

## This pass (2026-09-24): No JSON Handed to the Agent

Agents were being offered `.cma.json` handoffs and data files (report.json, listing.json) next to their reports. Now the outputs folder holds deliverables only: render.py writes and prints just the PDF, deck or calendar; compute.py saves the handoff next to report.json; and every skill writes its data file in a temporary folder (`saved-files.md`, Working Files). In a new conversation the offer skills read the CMA PDF or chat summary and confirm the range, as for any other CMA. Chat summaries no longer end in a `cma-handoff v1` JSON block (the agents aren't technical); an old block is still read. Tests check that renders write no JSON.

## This pass (2026-09-24): The 360 Property View as the Subject Input

Agents will usually upload the Stellar **Cross Property 360 Property View** PDF for the subject (listing, public records, full history across MLS numbers, flood, AVM), next to the CSV export. It's preferred, not required.

- `shared/references/listing-sheet.md` (synced into both CMAs): read it with `pdftotext -layout`; section-to-field map; the 360 history grid (`ACT->PND`, `895000.00->839000`, DOM per MLS number); MLS vs. county cross-checks (county sq ft and lot, bonus rooms counted as the county records them, homestead from the tax tab); what stays with the agent (owner names, mortgage history, private remarks, showing details, the AVM); buyer (current report, no history screenshot needed) vs. seller (often the last sale's report: history and county facts only, ask what changed since).
- buyer-cma asks for two inputs, not three; seller-cma skips the fact questions the report answers.
- `finance.millage` also matches the appraiser's tax-area code (the 360's `Tax Area: 01` is unincorporated Seminole whatever the mailing city says).
- Open: no eval uses a 360 PDF yet; it needs a fully mocked one (the real sample has real owners and agents).

## This pass (2026-09-24): One Onboarding Skill

User testing found the onboarding too technical: two profile skills with no direction, two files to attach, and market numbers agents don't know. Now:

- **`agent-profile` is the only setup skill:** a two-round interview modeled on the Cruz prototypes (`sources/michael-cruz/`), at most three fill-in-the-blank questions per round (the basics; look and sound), everything skippable, saved after Round 1. One file, `profile.md` (schema 2), with who the agent is and nothing about markets. `market-profile` is gone; no reader for the old files (nobody had saved any).
- **Local costs are conventions** ([architecture](architecture.md#local-costs), `shared/references/local-costs.md`): location from the listing; the deal's numbers, then built-in Florida/Stellar, then `shared/markets/national.md` (transfer tax 0.4%, title 0.5%, fees $1,200, commission 5% total, tax 1.1%...), labeled Estimate or Assumed per line. Estimates don't mark reports Preliminary. The skill looks up the state's transfer tax from a trusted source and lists the replaceable estimates after the first report; the agent's numbers go in the deal's `costs` (`profiles.DEAL_COSTS`, `Market.with_deal`).
- **Scripts:** only `render.py` takes `--profile` (name, brokerage, colors); analysis scripts take no profile. Other MLS exports: `--columns` / `export_columns`. seller-cma no longer refuses to render without commission terms.
- Version 0.7.0 (a skill was removed).

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

- **Eval anchoring:** the CMA example reports and the CMA evals use the same property (517 Hickorywood). Runners noticed and rebuilt from the inputs, but a second example property (or evals on a different home) would test the skills more honestly.
- **Loose judgment rules** that make runs vary: time adjustments (1–2% per quarter), undocumented-systems adjustments, expected sale per pricing option. method.md now anchors the expected sale on the adjusted comps; the rest is still judgment.
- **Page-1 dot plot labels** can overlap the price line; there's no setting to move them (the scatter has `side`).
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
| 2. Medium (done 2026-09-24, validated) | 0.4.0 | Market data and checks | CORE-7, CORE-9, CORE-11 to CORE-17, CORE-19 (warning), CORE-20, CORE-21 | Done |
| | | CMA method and charts | CMA-7 to CMA-12, CMA-14, CMA-15, CMA-17, CMA-20, CMA-22 | Done |
| | | Offer pricing and programs | OFR-7 to OFR-12, OFR-18, OFR-25, OFR-30 | Done |
| | | Offer benchmarks and review UX | OFR-15, OFR-16, OFR-20, OFR-24, OFR-28 | Done |
| | | TREC and other forms (TREC 20-19, current since July 1, 2026) | OFR-19, TL-15, TL-24 | Done |
| | | Timeline wording and outputs | TL-14, TL-16, TL-17, TL-19, TL-21, TL-22, TL-25 | Done |
| | | Fair housing and design | FH-4, FH-5, DS-1 to DS-4 | Done |
| 3. Low, docs, tooling (done 2026-09-24, validated) | 0.5.0 | Skills | CORE-22 to CORE-29, CMA-23 to CMA-32, OFR-23, OFR-29, OFR-31, OFR-32, TL-20 | Done |
| | | Docs and tooling | DOC-1 to DOC-14 (DOC-13 needs a license and remote) | Done |
| 4. Evals | | Iteration 2 on the new fixtures, plus the fair-housing evals | | Open |

Fixed: OFR-1, CMA-1, CMA-13, CMA-19, CMA-21, OFR-22, CORE-1, CORE-2, CORE-8, CORE-10, CORE-24, TL-1 to TL-13 (TL-4 with the profile theme), TL-18, TL-23, OFR-33, OFR-2 to OFR-5, OFR-17, OFR-27, OFR-6, OFR-21, CORE-5, CORE-6, CORE-18, CMA-3, CMA-4, CMA-18, OFR-13, OFR-14 (and Collier from CORE-7), CMA-2, CORE-3, CORE-4, CMA-16, FH-6, FH-1, FH-2, FH-3, CMA-5, CMA-6, OFR-26, CORE-7, CORE-9, CORE-11 to CORE-17, CORE-19 (warning only; the tiered model is on the roadmap), CORE-20, CORE-21, CMA-7 to CMA-12, CMA-14, CMA-15, CMA-17, CMA-20, CMA-22, OFR-7 to OFR-12, OFR-18, OFR-25, OFR-30, OFR-15, OFR-16, OFR-20, OFR-24, OFR-28, OFR-19, TL-15, TL-24, TL-14, TL-16, TL-17, TL-19, TL-21, TL-22 (page 3 is now one appendix block), TL-25, FH-4, FH-5, DS-1 to DS-4, CORE-22, CORE-23, CORE-25 to CORE-29, CMA-23 to CMA-32, OFR-23, OFR-29, OFR-31, OFR-32, TL-20, DOC-1 to DOC-12, DOC-14.

DOC-13: MIT license (LICENSE, `license` in every manifest); repository in the manifests (now https://github.com/axelrivera/real-estate-skills) and the README.

CORE-5 note: who pays the buyer's broker is expressed by the percentages rather than a separate `buyer_broker_paid_by` field: the seller side models what the seller pays (0 when the buyer pays), and the buyer side counts the rest of the buyer's agreement as a "Buyer's Broker Fee (Not Paid by Seller)" line.

Removed with OFR-4: the seller review's "fallback counter" for cash-short buyers. With appraisal risk measured from the CMA high, the main counter already prices at the top of the range with no gap request, so the fallback could no longer trigger.

Found while verifying (not in the audit): the FR/BAR forms set no time of day, so a rolled deadline runs to the end of the next business day, not 5:00 PM (fixed with TL-1); Brevard is Space Coast MLS, not Stellar; Lee and Charlotte are seller-pay counties; Texas legal holidays exclude Columbus Day (fixed with TL-24); the FR/BAR Standard form has no inspection cancel right and seller repair limits, so the timeline now models its repair windows and OFR-33 tracks the offer engine's missing repair reserve.

Won't fix: (none yet).

## Remaining work, in order

1. **Manual smoke test** of the 0.12.0 build per [manual-testing.md](manual-testing.md) (`make package manual-kit`; uninstall the old `core` and `transactions` plugins first). The user runs it and hands back `out/manual-test/results.md`; failures become fixes before the pull request into `main`.
2. **Release** per [release-checklist.md](release-checklist.md).
3. **Broker review** of `shared/references/fair-housing.md` (see Open items).
4. **Yearly refreshes:** Florida millage when the year's rates are final (October); loan limits in `shared/markets/loan-limits.md` when FHFA and HUD publish the next year's (late November); the indexed homestead exemption in `fl.md` (January).
5. **Later / optional:** New skills and scope extensions (more state and MLS layers, the offer outcome log, trigger-description optimization) are in [roadmap.md](roadmap.md).

## Decisions worth remembering (details in the docs)

- Skills must be self-contained; `shared/` is copied into each skill's `scripts/_shared/` by `make sync` and committed.
- Markdown output comes from `assets/` templates filled by Claude; scripts only do math, parsing, validation and PDF/PPTX rendering.
- Every skill has markdown and file modes from the same data JSON; core profile skills are markdown only.
- Brand colors from the profile (one primary or buyer/seller split); status colors fixed; the subject home is black, never a second hue.
- One profile file (`profile.md`): who the agent is; only name and brokerage required; never print placeholders. No logos on reports.
- Market data in layers: state (FL) and MLS (Stellar, FL + PR) are separate; never fill Florida values for other states; each value carries its source. Per-deal costs go in the deal's data file.
- Every `*_pct` is a fraction (0.025 = 2.5%); interest `rate` is a percent.
- Offer skills consume `cma-handoff v1` (JSON file, or fenced markdown block, else extract and confirm).
- Local costs: the deal's numbers, else built-in local values, else national estimates labeled per line; commission assumed at 5% total ("Assumed") until the deal gives terms. Never Florida's numbers elsewhere.
