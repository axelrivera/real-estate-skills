---
name: buyer-cma
description: Builds a buyer-side comparative market analysis for a specific listing, covering the supported value range, the full listing history, adjusted comps, a price-vs-size scatterplot, competition, market conditions, the buyer's real costs (taxes at their price, insurance drivers, payment scenarios, price vs. seller credit), watch items, questions for the listing agent, and a suggested opening offer with target and walk-away. Delivered as a polished PDF or a markdown summary, in English or Spanish. Use it whenever an agent shares an MLS listing sheet, a price-history screenshot or a CMA export for a home their buyer is considering, or asks "run a CMA on this listing", "is this priced right?", "what should my buyer offer?", "comps for 123 Oak St", or "same buyer report as last time". Its handoff feeds the buyer-offer-strategy skill. Not for pricing a seller's listing.
---

# Buyer CMA

A report for a buyer deciding whether and how to offer. It works because it tells the truth, including the parts that argue against buying or against a low offer. The scripts handle the math, charts and layout. The judgment is yours: reading the listing honestly, choosing and adjusting comps, and explaining each number in plain words to a buyer who may never have bought a house.

Every number is computed by a script and never typed by hand, because a wrong figure in a document carrying the agent's license number is the worst failure this skill can produce. Never invent comps, prices, dates, roof ages or tax figures.

## 1. Gather the inputs

You need three things. If one is missing, ask for it and say why it matters:

1. **Listing sheet** for the subject (PDF or screenshot): facts, remarks, tax, owner, occupancy, showing and offer instructions.
2. **Listing history** (screenshot of the MLS history grid): every list date, price change, off/on market, pending, cancel and relist.
3. **CMA export** (CSV) of nearby sales from about the last 6 months, plus active, pending, expired and canceled listings.

In the same message, ask the buyer questions the offer depends on: when they need to move (lease ending, home to sell), how they're financing (loan type, down payment, cash for closing), and how much they want this house. Don't block on them; without answers, plan for a typical first-time buyer and say so in the conditions.

Use the agent's market profile when there is one (Project files, uploads). Florida and Stellar MLS are built in. For a PDF, the agent's name and brokerage go on it: use their agent profile, or ask for the two in the same message.

**Quick gut check** ("is it priced right? just tell me"): run stats.py, pick and adjust the comps, and still run compute.py for the median and range (the payment and tax blocks can be short). Answer in a few sentences plus the handoff block; skip the full template unless asked.

## 2. Read the subject and the market

- Rebuild the full history from the screenshot and run the numbers:
  ```
  python3 scripts/stats.py export.csv --address "<address as in the export>" --state <ST> --county <county> [--mls <MLS>] [--market market-profile.md] [--split-date YYYY-MM-DD]
  ```
  Pick a split date so "recent" is roughly the last 2–3 months.
- Search quickly: the address itself (claims that disappeared from the listing), the current 30-year mortgage rate (Freddie Mac weekly survey), and, when the market profile has no millage for the area, the county's current millage.

Read `references/method.md` for reading the history, choosing and adjusting comps, and classifying homes for the chart.

## 3. Write report.json

Copy `assets/example-report.json` (an approved report) and replace every value; its length and tone are the target. It describes a sample home with illustrative details: take its structure and tone, never a fact (a sale price, a repair, a record) into a real report. Read `references/report-data.md` for every field, `references/offer-plan.md` before setting the offer plan and credit scenarios, `references/costs.md` for taxes, insurance and payments, and `references/writing.md` for how each section reads. Write `summary_page` last; write `{median_adjusted}` where page 1 quotes the median adjusted value and the script fills it in. For Spanish, set `"language": "es"` and write every field in Spanish.

Then compute:

```
python3 scripts/compute.py report.json [--market market-profile.md]
```

Fix every item in `warnings` (a credit over the program limit, a walk-away above the range, a tax estimated without millage) and re-run. It also saves `<address>.cma.json`, the handoff the offer skills read.

## 4. Deliver

- **Report to send or print:** `python3 scripts/render.py report.json [--agent agent-profile.md] [--market market-profile.md]`. It saves the PDF and the handoff. Read what it prints: page 1 must fit on one page (shorten the summary wording, never drop an element); flip a chart callout's `side` if a label overlaps. Look at the pages before presenting.
- **Summary in chat:** fill in `assets/buyer-cma-template.md` from report.json and compute.py's output (numbers only from the output, already formatted), and end with its `handoff_block` so a later offer conversation can use it.

Either way, reply briefly: the range, where the asking price sits, the 2–3 findings that matter most, and anything the agent must verify before sending (condition judgments, tax jurisdiction, placeholders). Cite the web sources you used. Offer the other format in one line.
