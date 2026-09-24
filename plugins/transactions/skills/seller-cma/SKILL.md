---
name: seller-cma
description: Builds a listing-side comparative market analysis for a seller's home, with a recommended list price, supported value range, adjusted comps, a price-vs-size scatterplot, competition, market conditions, three pricing strategies with estimated net proceeds (brokerage, transfer tax, title, seller credit, optional payoff), what buyers would pay per month at each price, a launch plan and the documents needed from the seller. Delivers a polished report PDF and an editable listing presentation (PowerPoint) with the same numbers, or a short markdown summary. Use it whenever an agent has a listing appointment, asks "what should we list at?", "pricing analysis for 123 Oak St", "listing presentation", "net sheet with comps", "seller CMA", or uploads an MLS CMA export and mentions a seller or a list price, even when they only give an address. Its handoff feeds the seller-offer-review skill. Not for a buyer deciding what to offer.
---

# Seller CMA

A report and a listing presentation for a homeowner deciding what to list at. It answers three questions: what is the home worth, what should we list it at, and what will I walk away with. It works because it's honest: a seller who sees only flattering comps overprices, loses the first weeks, and blames the agent. The scripts do the math, the charts, the layout and the deck. Your part is the intake, the comp judgment, and plain words for a homeowner who isn't a real estate professional.

Every number comes from a script, never typed by hand, because a wrong net figure in front of a seller is the worst failure this skill can produce. Never invent comps, update dates, permit status or tax figures.

## 1. Gather the inputs

Ask for everything missing in one message. Skip what's already in the chat, project files or the agent profile. Read `references/method.md` for the full checklist and why each item matters. In short:

- **From the seller:** address; beds, baths, heated sq ft, lot, year built, construction; pool, garage, HOA/CDD; updates with dates and permits (roof first); the current tax bill; known issues or claims; timeline and occupancy; optional mortgage payoff (turns the net sheet into cash at closing).
- **From the agent:** the MLS CMA export (CSV) of nearby sales from about the last 6 months plus active, pending, expired and canceled listings; the brokerage terms to model (without them, the market default is used and labeled a placeholder); flood zone if known.

Treat the home as a first-time listing: the scripts drop every export row with its address, and its facts come from the seller. stats.py lists those rows in `subject_rows`: if the home is **listed right now** (active or pending), say so first. It may be the agent's own listing being repriced, an expired listing, or a home listed with another brokerage, which the agent must not solicit; ask which before going further. A failed current price is the most important pricing fact, so with the agent's go-ahead, address it. For an old relist, ask before adding the history.

For a PDF or deck, the agent's name and brokerage go on it: use their agent profile, or ask for the two in the same message.

**No MLS export** (the agent typed a few comps): skip stats.py, write the comps and competition from what you were given, and build the market table and key stats from those sales and the rate; say in the method that the market numbers come from a short list. The scatter slide is left out on its own.

Use the agent's market profile when there is one. Florida and Stellar MLS are built in. Outside them, closing costs and commission come from the agent or their market profile; a missing value is never filled with Florida's, and the report is marked Preliminary until it's supplied.

## 2. Read the market

```
python3 scripts/stats.py export.csv --address "<address as in the export>" --sqft <sqft> [--pool] --subdivision "<name>" --state <ST> --county <county> [--mls <MLS>] [--market market-profile.md] [--split-date YYYY-MM-DD]
```

Pick a split date so "recent" is roughly the last 2–3 months. Search the web for the latest Freddie Mac 30-year rate and, when the market profile has no millage for the home's taxing district, the county's current millage. Cite both in your reply.

Read `references/method.md` for choosing and adjusting comps, setting the range and the recommended price, and the three pricing strategies.

## 3. Write report.json

Copy `assets/example-report.json` (an approved report) and replace every value; its length and tone are the target. It describes a sample home with illustrative details: take its structure and tone, never a fact (a sale price, a repair, a record) into a real report. Read `references/report-data.md` for every field, `references/costs.md` before the costs and buyer-payment blocks, and `references/writing.md` for how each section reads. Write `summary_page` last; write `{median_adjusted}` where page 1 quotes the median adjusted value and the script fills it in.

For the presentation, put its wording under `deck` in report.json (copy `assets/example-deck-content.json`; read `references/deck-content.md`). It holds wording only: prices, nets and payments come from the report, and `{list_price}`-style placeholders fill them in.

Then compute:

```
python3 scripts/compute.py report.json [--market market-profile.md]
```

Fix every item in `warnings` (a recommended price outside the range, a missing tax rate, a missing local cost) and re-run. Without brokerage terms outside Florida the nets would leave out the commission, so render.py refuses to build the files until `costs` has them (0 is fine): ask the agent. For a chat-only answer, compute.py needs `subject`, `recommendation`, `comps.cards`, `pricing.strategies`, `costs` and `buyer_payment`; the prose sections and `deck` can stay short. Tell the agent about each item in `assumptions` (placeholder brokerage, built-in title fees). It also saves `<address>.cma.json`, the handoff seller-offer-review reads.

## 4. Deliver

- **Report and presentation (default for a listing appointment):**
  ```
  python3 scripts/render.py report.json --format all [--agent agent-profile.md] [--market market-profile.md]
  ```
  `--format pdf` or `--format pptx` builds just one. Read what it prints: page 1 must fit on one page (shorten the summary wording, never drop an element); flip a chart callout's `side` if a label overlaps. Look at every page and slide before presenting; `references/deck-content.md` explains how to check the deck. If the deck can't be built (no Node), say so plainly and deliver the PDF.
- **Summary in chat:** fill in `assets/seller-cma-template.md` from report.json and compute.py's output (numbers only from the output, already formatted), and end with its `handoff_block`.

Either way, reply briefly: the recommended price and range, the one or two facts driving it, how the three strategies compare, and every placeholder the agent must replace before the appointment (brokerage terms, update dates, flood zone, payoff, title company quote). Say "Preliminary" plainly if compute.py marked it so. Offer the other format in one line. Keep the chat reply short when files are delivered (about 150 words): the files carry the detail, and a long reply repeating them gets skimmed.
