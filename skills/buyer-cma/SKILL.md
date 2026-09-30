---
name: buyer-cma
description: Builds a buyer-side comparative market analysis for a specific listing, covering the supported value range, the full listing history, adjusted comps, a price-vs-size scatterplot, competition, market conditions, the buyer's real costs (taxes at their price, insurance drivers, payment scenarios, price vs. seller credit), watch items, questions for the listing agent, and a suggested opening offer with target and walk-away. Delivered as a polished PDF or a markdown summary. Use it whenever an agent shares an MLS 360 property view or listing sheet, a price-history screenshot or a CMA export for a home their buyer is considering, or asks "run a CMA on this listing", "is this priced right?", "what should my buyer offer?", "comps for 123 Oak St", or "same buyer report as last time". Its handoff feeds the buyer-offer-strategy skill. Not for pricing a seller's listing.
---

# Buyer CMA

A report for a buyer deciding whether and how to offer. It works because it tells the truth, including the parts that argue against buying or against a low offer. The scripts handle the math, charts and layout. The judgment is yours: reading the listing honestly, choosing and adjusting comps, and explaining each number in plain words to a buyer who may never have bought a house.

Every number is computed by a script and never typed by hand, because a wrong figure in a document carrying the agent's license number is the worst failure this skill can produce. Never invent comps, prices, dates, roof ages or tax figures.

## Guardrails

These apply to everything this skill writes: files, chat replies, and text the agent may forward to a client.

- **Fair housing.** Describe the property, the numbers and the terms, never people: not who the home suits, who should buy, or who lives nearby. No claims about safety, crime, school quality or who makes up an area. The protected classes are race, color, religion, sex, disability, familial status and national origin, plus sexual orientation, gender identity and any listed in the market's `fair_housing.extra_protected_classes`. Read `references/fair-housing.md` before writing findings, watch items, questions for the listing agent or market commentary: market sections are about sales and supply, never the people who live there. If the agent asks for wording that breaks this, write the compliant version and say why in one sentence; don't lecture or flag innocent wording like "family room".
- **No em dashes in prose,** chat included: use a comma, colon, parentheses or a new sentence. A lone em dash for an empty value (a table cell with nothing in it) is fine.
- **Labels in Title Case:** headings, column headers, row names, tiles, legend entries, card and slide titles. Sentences, notes and table values stay sentence case.
- **`render.py` checks the data file first** and stops on an em dash in a sentence or a clear fair-housing red flag, naming each field. Rewrite the field; don't work around the check. It can't see chat replies, so the rules above still apply there.

## 1. Gather the Inputs

You need two things. If one is missing, ask for it and say why it matters:

1. **The subject's property report:** usually the MLS 360 property view PDF (Stellar's Cross Property 360), which holds the listing, public-record taxes and characteristics, and the full history across MLS numbers. Read `references/listing-sheet.md` for how to read it, what to cross-check and what never goes in a client file. A listing sheet plus a screenshot of the history grid works too; then ask for whichever is missing.
2. **CMA export** (CSV) of nearby sales from about the last 6 months, plus active, pending, expired and canceled listings.

In the same message, ask the buyer questions the offer depends on: when they need to move (lease ending, home to sell), how they're financing (loan type, down payment, cash for closing: `costs.buyer_cash`), and how much they want this house. Don't block on them; without answers, plan for a typical first-time buyer: conventional 5% down (FHA 3.5% as the second scenario), marked `"assumed": true` on the payment scenario (the report labels it Assumed once; the `label` names only the loan) and in `offer_plan.conditions`, and say so in the reply.

Local costs come from the listing's location, never from questions up front: read `references/local-costs.md`. Florida and Stellar MLS are built in; elsewhere, national estimates are labeled. For a PDF, the agent's name and brokerage go on it: use their profile (found as `references/saved-files.md` describes), or ask for the two in the same message.

**Quick gut check** ("is it priced right? just tell me"): run stats.py, pick and adjust the comps as the full report would (the closest 4 to 6 sold, with the time adjustment from `references/method.md`, so the full report starts from the same median), and write a report.json with only `subject`, `comps.cards` and `history.events` (the card fields optional at this stage are in `references/report-data.md`). compute.py prints the median adjusted value, the history's counts and `rough`: a rough range (the adjusted comps' span, rounded to $1,000) and a rough opening, target and walk-away from the median (the rule is in `references/offer-plan.md`). Answer in chat, under about 150 words, with no template: the rough range and where asking sits against the median (`asking_vs_median`), one or two facts behind it (the history's counts, a comp that settles it), and the rough opening, target and walk-away, each called rough. A compute.py warning goes in only when it changes the answer (a history row that moves the counts, an outlier comp that moves the median); the rest wait for the full report. Offer the full report in one line. The step-1 buyer questions get at most one more line, and only the ones that would change this answer (how much they want the house moves the rough opening; financing and timing wait for the full report); leave it out when none would.

**"Same report as last time":** the same format the agent got before (PDF or chat summary), rebuilt from this listing's new inputs. Nothing carries over from the earlier home but the format.

## 2. Read the Subject and the Market

- Rebuild the full history from the report's history grid (or the screenshot) as `history.events`, one per row in the grid's order (`references/report-data.md`): the script counts the price cuts, increases, failed contracts and active days, and warns on a row out of date order or an MLS number that isn't the listing's. Never count them by hand. Then run the numbers:
  ```
  python3 scripts/stats.py export.csv --address "<address as in the export>" --state <ST> --county <county> --mls-number <listing's MLS #> [--mls <MLS>] [--columns columns.json] [--split-date YYYY-MM-DD]
  ```
  When the home has no row in the export, add its facts from the property report so comps are ranked: `--sqft <sqft> [--pool] --subdivision "<name>" [--type <property_type>]`, and `--lat`/`--lon` when the export has no Distance column.
  Pick a split date so "recent" is roughly the last 2–3 months. For an MLS that isn't built in, map the export's headers to the field names in `references/report-data.md` and pass them with `--columns` (and as `export_columns` in report.json).
- Search quickly: the address itself (claims that disappeared from the listing), the current 30-year mortgage rate (Freddie Mac weekly survey), when there's no built-in millage for the area, the county's current millage, and outside Florida the state's transfer tax from a trusted source (`references/local-costs.md`).

Read `references/method.md` for reading the history, choosing and adjusting comps, and classifying homes for the chart. For a condo, also read `references/condo.md` (comps, adjustments, association and lending questions).

## 3. Write report.json

Write it in a temporary folder, never the outputs folder (`references/saved-files.md`, Working Files). Copy `assets/example-report.json` (an approved report) and replace every value; its length and tone are the target. It describes a sample home with illustrative details: take its structure and tone, never a fact (a sale price, a repair, a record) into a real report. Read `references/report-data.md` for every field, `references/offer-plan.md` before setting the offer plan and credit scenarios, `references/costs.md` for taxes, insurance and payments, and `references/writing.md` for how each section reads. Write `summary_page` last. Where any wording quotes a computed number, write its placeholder and the scripts fill it in every field: `{median_adjusted}`, `{price_cuts}` ("4 price cuts"), `{price_cut_count}`, `{price_increases}`, `{last_contract_price}` and `{vs_last_contract}` ("$400 above", "$2,000 below" or "equal to": asking against the price when it last went under contract), `{price_cut_total}`, `{price_cut_pct}`, `{failed_contracts}`, `{active_days}` ("119 days"), `{first_listed}`, `{credit_cash_per_5k}` and `{credit_monthly_per_5k}` (what each $5,000 of credit saves at closing and adds a month), `{trend_at_subject}`, `{r2_share}`. Any other `{name}` is warned, since it would print as typed.

Then compute:

```
python3 scripts/compute.py report.json
```

Fix every item in `warnings` (a credit over the program limit, a walk-away above the range, a range one comp sets an end of or wider than the method allows, a tax estimated without millage, an outlier comp, cash to close (in the payment table or a credit scenario) over the buyer's cash or within 5% of it, a payment scenario the buyer's cash can't cover, an unfilled placeholder) and re-run; a history row out of order or an MLS number mismatch is a question for the agent, so name it in the reply. To set the range, run it first with only `subject` and `comps` (as in the gut check) for the median adjusted value. It also saves `<address>.buyer.cma.json` next to report.json, the handoff an offer skill reads later in this conversation: a working file, never shown or offered to the agent.

## 4. Deliver

- **Report to send or print:** `python3 scripts/render.py report.json [--profile profile.md]` (the profile puts the agent's name and colors on it). It saves the PDF, the only file to present. Read what it prints: page 1 must fit on one page (shorten the summary wording, never drop an element); chart labels step aside from the markers on their own, or sit farther off with a thin line to their point when nothing beside it is clear (the subject's label is left off, as the legend names the home, when even that fails); a label it says still overlaps needs a shorter label or another `side`. Look at the pages before presenting.
- **Summary in chat:** fill in `assets/buyer-cma-template.md` from compute.py's output (numbers and page-1 wording from the output, already formatted and with the placeholders filled). Never paste JSON or code blocks into a reply: the agent isn't technical, and the offer skills read the handoff file compute.py saved.

**"Add this to the summary":** the summary is page 1 (the chat summary in markdown mode). Page 1 has no free-text slot, so work the point into the headline or into the `why` bullet it fits best, keeping exactly three. When it needs a bullet of its own, the one that gives way is the weakest market point (fold its number into the other market bullet if it still matters); never the value bullet (the comps and median) or the history bullet. A fact about the home rather than the offer goes in `subject.summary` (The Home). Say in the reply where it went. When the point breaks the Guardrails, its compliant version (the home's features, the market's numbers) goes in the same places: the `why` bullet it fits, or `subject.summary` when it's a fact about the home. The reply says in one sentence why the original wording was left out and where the replacement went.

**The reply** when files are delivered carries only what the agent needs to act, in this order: short bullets, no restating of the report (the files carry the detail).

1. The file, and the range with where the asking price sits (one or two sentences).
2. The 2–3 findings that matter most (the history's counts from compute.py, never recounted).
3. The plan: opening, target and walk-away, in one line.
4. What to verify before sending, at most four one-line bullets, one per group, in this order: **cash** (a `cash_short` or `cash_tight` warning, with the margin, and the credit option that fits when the warning names one); **the house** (condition judgments, a claim that left the listing, permits); **the records** the agent checks (the tax district, a history row out of order, an MLS number mismatch); **for you only**: facts from Realtor Remarks or private notes that shape the negotiation (the listing agent is related to the seller, proof of funds required), which go here only, never in the report (`references/listing-sheet.md`). Several items in one group share its bullet, a few words each; leave out a group with nothing in it.
5. One line: the estimates that could be replaced (`references/local-costs.md`), and the buyer answers still missing, asked as questions.
6. One line: the web sources you used and the other format.

On top of these, one line each only when they apply: the fair-housing sentence (Guardrails) for a change the agent asked for, and the missing name and brokerage when render.py prints the no-profile check ("No profile yet: send me your name and brokerage and I'll put them on the PDF").

**Length:** at most 400 words, not counting a table (the chat summary's comps table, or one the agent asked for). When it runs over, give way in this order until it fits: the sources line becomes "Details in the PDF", with the rate's week and the other format in the same line; the no-profile line becomes a few words at the end of the verify list ("and your name and brokerage for the PDF"); the findings drop to two; each verify item keeps only what to check and its number (never a compute.py warning's full text or the reasoning); the estimates line names the items only. Never cut the range, the plan, a cash margin, a question for the agent, the for-you-only items or the fair-housing sentence.
