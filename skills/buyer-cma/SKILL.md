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

In the same message, ask the buyer questions the offer depends on: when they need to move (lease ending, home to sell), how they're financing (loan type, down payment, cash for closing: `costs.buyer_cash`), and how much they want this house. Don't block on them; without answers, plan for a typical first-time buyer and say so in the conditions.

Local costs come from the listing's location, never from questions up front: read `references/local-costs.md`. Florida and Stellar MLS are built in; elsewhere, national estimates are labeled. For a PDF, the agent's name and brokerage go on it: use their profile (found as `references/saved-files.md` describes), or ask for the two in the same message.

**Quick gut check** ("is it priced right? just tell me"): run stats.py, pick and adjust the comps, and write a report.json with only `subject`, `comps.cards` and `history.events` (the card fields optional at this stage are in `references/report-data.md`). compute.py prints the median adjusted value, the history's counts and `rough`: a rough range (the adjusted comps' span) and a rough opening, target and walk-away from the median (the rule is in `references/offer-plan.md`). Answer in chat, under about 150 words, with no template: the rough range and where asking sits against the median (`asking_vs_median`), one or two facts behind it (the history's counts, a comp that settles it), and the rough opening, target and walk-away, each called rough. Offer the full report in one line.

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

Write it in a temporary folder, never the outputs folder (`references/saved-files.md`, Working Files). Copy `assets/example-report.json` (an approved report) and replace every value; its length and tone are the target. It describes a sample home with illustrative details: take its structure and tone, never a fact (a sale price, a repair, a record) into a real report. Read `references/report-data.md` for every field, `references/offer-plan.md` before setting the offer plan and credit scenarios, `references/costs.md` for taxes, insurance and payments, and `references/writing.md` for how each section reads. Write `summary_page` last. Where any wording quotes a computed number, write its placeholder and the scripts fill it in every field: `{median_adjusted}`, `{price_cuts}` ("4 price cuts"), `{price_cut_count}`, `{price_increases}`, `{price_cut_total}`, `{price_cut_pct}`, `{failed_contracts}`, `{active_days}` ("119 days"), `{first_listed}`, `{trend_at_subject}`, `{r2_share}`. Any other `{name}` is warned, since it would print as typed.

Then compute:

```
python3 scripts/compute.py report.json
```

Fix every item in `warnings` (a credit over the program limit, a walk-away above the range, a tax estimated without millage, an outlier comp, cash to close over the buyer's cash, an unfilled placeholder) and re-run; a history row out of order or an MLS number mismatch is a question for the agent, so name it in the reply. To set the range, run it first with only `subject` and `comps` (as in the gut check) for the median adjusted value. It also saves `<address>.buyer.cma.json` next to report.json, the handoff an offer skill reads later in this conversation: a working file, never shown or offered to the agent.

## 4. Deliver

- **Report to send or print:** `python3 scripts/render.py report.json [--profile profile.md]` (the profile puts the agent's name and colors on it). It saves the PDF, the only file to present. Read what it prints: page 1 must fit on one page (shorten the summary wording, never drop an element); chart labels step aside from the markers on their own, and a label it says still overlaps needs a shorter label or another `side`. Look at the pages before presenting.
- **Summary in chat:** fill in `assets/buyer-cma-template.md` from compute.py's output (numbers and page-1 wording from the output, already formatted and with the placeholders filled). Never paste JSON or code blocks into a reply: the agent isn't technical, and the offer skills read the handoff file compute.py saved.

**"Add this to the summary":** the summary is page 1 (the chat summary in markdown mode). Page 1 has no free-text slot, so work the point into the headline or into the `why` bullet it fits best, keeping exactly three. A fact about the home rather than the offer goes in `subject.summary` (The Home). Say in the reply where it went.

**The reply** when files are delivered carries only what the agent needs to act, in this order, and stays under about 250 words (the files carry the detail):

1. The file, and the range with where the asking price sits.
2. The 2–3 findings that matter most (the history's counts from compute.py, never recounted).
3. The plan: opening, target and walk-away.
4. What to verify before sending: condition judgments, the tax district, anything compute.py warned about (history order, MLS number), and agent-only watch items: facts from Realtor Remarks or private notes that shape the negotiation (the listing agent is related to the seller, proof of funds required) go here only, never in the report (`references/listing-sheet.md`).
5. The estimates that could be replaced, as `references/local-costs.md` shows, and any buyer answers still missing.
6. The web sources you used, and the other format in one line.

A fair-housing change the agent asked for gets its one sentence (Guardrails) on top of these.
