---
name: seller-cma
description: Builds a listing-side comparative market analysis for a seller's home, with a recommended list price, supported value range, adjusted comps, a price-vs-size scatterplot, competition, market conditions, three pricing strategies with estimated net proceeds (brokerage, transfer tax, title, seller credit, optional payoff), what buyers would pay per month at each price, a launch plan and the documents needed from the seller. Delivers a polished report PDF and an editable listing presentation (PowerPoint) with the same numbers, or a short markdown summary. Use it whenever an agent has a listing appointment, asks "what should we list at?", "pricing analysis for 123 Oak St", "listing presentation", "net sheet with comps", "seller CMA", or uploads an MLS CMA export and mentions a seller or a list price, even when they only give an address. Its handoff feeds the seller-offer-review skill. Not for a buyer deciding what to offer.
---

# Seller CMA

A report and a listing presentation for a homeowner deciding what to list at. It answers three questions: what is the home worth, what should we list it at, and what will I walk away with. It works because it's honest: a seller who sees only flattering comps overprices, loses the first weeks, and blames the agent. The scripts do the math, the charts, the layout and the deck. Your part is the intake, the comp judgment, and plain words for a homeowner who isn't a real estate professional.

Every number comes from a script, never typed by hand, because a wrong net figure in front of a seller is the worst failure this skill can produce. Never invent comps, update dates, permit status or tax figures.

## Guardrails

These apply to everything this skill writes: files, chat replies, and text the agent may forward to a client.

- **Fair housing.** Describe the property, the numbers and the terms, never people: not who the home suits, who should buy, or who lives nearby. No claims about safety, crime, school quality or who makes up an area. The protected classes are race, color, religion, sex, disability, familial status and national origin, plus sexual orientation, gender identity and any listed in the market's `fair_housing.extra_protected_classes`. Read `references/fair-housing.md` before writing findings, value drivers, the launch plan or deck notes. Value drivers are features of the home and the launch plan is about the property and the process, never a kind of buyer. If the agent asks for wording that breaks this, write the compliant version and say why in one sentence; don't lecture or flag innocent wording like "family room".
- **No em dashes in prose,** chat included: use a comma, colon, parentheses or a new sentence. A lone em dash for an empty value (a table cell with nothing in it) is fine.
- **Labels in Title Case:** headings, column headers, row names, tiles, legend entries, card and slide titles. Sentences, notes and table values stay sentence case.
- **`render.py` checks the data file first** and stops on an em dash in a sentence or a clear fair-housing red flag, naming each field. Rewrite the field; don't work around the check. It can't see chat replies, so the rules above still apply there.

## 1. Gather the Inputs

Ask for everything missing in one message, and skip what's already in the chat or the listing. Don't ask about local costs or commission: they're defaults the agent can correct after the first report. Read `references/method.md` for the full checklist and why each item matters. In short:

- **From the seller:** address; beds, baths, heated sq ft, lot, year built, construction; pool, garage, HOA/CDD; updates with dates and permits (roof first); the current tax bill; known issues or claims; timeline and occupancy; optional mortgage payoff (turns the net sheet into cash at closing).
- **From the agent:** the MLS CMA export (CSV) of nearby sales from about the last 6 months plus active, pending, expired and canceled listings; the brokerage terms if they volunteer them (otherwise 5% total is assumed and marked on every page and slide that shows a net); the tax bill and expected closing date for the proration; the property type (Miami-Dade surtax); flood zone if known.

Treat the home as a first-time listing: the scripts drop every export row with its address, and its facts come from the seller. stats.py lists those rows in `subject_rows`: if the home is **listed right now** (active or pending), say so first. It may be the agent's own listing being repriced, an expired listing, or a home listed with another brokerage, which the agent must not solicit; ask which before going further. A failed current price is the most important pricing fact, so with the agent's go-ahead, address it. For an old relist, ask before adding the history.

For a PDF or deck, the agent's name and brokerage go on it: use their profile (found as `references/saved-files.md` describes), or ask for the two in the same message.

**No MLS export** (the agent typed a few comps): skip stats.py, write the comps and competition from what you were given, and build the market table and key stats from those sales and the rate; say in the method that the market numbers come from a short list. The scatter slide is left out on its own.

Local costs come from the home's location: read `references/local-costs.md`. Florida and Stellar MLS are built in; elsewhere, national estimates are labeled Estimate (never Florida's numbers), and you look up the state's transfer tax from a trusted source.

## 2. Read the Market

```
python3 scripts/stats.py export.csv --address "<address as in the export>" --sqft <sqft> [--pool] --subdivision "<name>" [--type <property_type>] [--lat <lat> --lon <lon>] --state <ST> --county <county> [--mls <MLS>] [--columns columns.json] [--split-date YYYY-MM-DD]
```

Pick a split date so "recent" is roughly the last 2–3 months. When the export has no Distance column (a zip or subdivision search), distances come from Latitude and Longitude: pass the home's `--lat`/`--lon` (and `latitude`/`longitude` in report.json) when it has no row of its own in the export. For an MLS that isn't built in, map the export's headers to the field names in `references/report-data.md` and pass them with `--columns` (and as `export_columns` in report.json). Search the web for the latest Freddie Mac 30-year rate, the county's current millage when there's none built in for the home's taxing district, and outside Florida the state's transfer tax. Cite them in your reply.

Read `references/method.md` for choosing and adjusting comps, setting the range and the recommended price, and the three pricing strategies. For a condo, also read `references/condo.md` (comps, adjustments, association and lending questions).

## 3. Write report.json

Copy `assets/example-report.json` (an approved report) and replace every value; its length and tone are the target. It describes a sample home with illustrative details: take its structure and tone, never a fact (a sale price, a repair, a record) into a real report. Read `references/report-data.md` for every field, `references/costs.md` before the costs and buyer-payment blocks, and `references/writing.md` for how each section reads. Write `summary_page` last; write `{median_adjusted}` where page 1 quotes the median adjusted value and the script fills it in.

For the presentation, put its wording under `deck` in report.json (copy `assets/example-deck-content.json`; read `references/deck-content.md`). It holds wording only: prices, nets and payments come from the report, and `{list_price}`-style placeholders fill them in.

Then compute:

```
python3 scripts/compute.py report.json
```

Fix every item in `warnings` (a recommended price outside the range, a missing tax rate) and re-run. For a chat-only answer, compute.py needs `subject`, `recommendation`, `comps.cards`, `pricing.strategies`, `costs` and `buyer_payment`; the prose sections and `deck` can stay short. Tell the agent about each item in `assumptions` (assumed brokerage, estimated costs, built-in title fees). It also saves `<address>.seller.cma.json`, the handoff seller-offer-review reads.

## 4. Deliver

- **Report and presentation (default for a listing appointment):**
  ```
  python3 scripts/render.py report.json --format all [--profile profile.md]   # the profile puts the agent's name and colors on it
  ```
  `--format pdf` or `--format pptx` builds just one. Read what it prints: page 1 must fit on one page (shorten the summary wording, never drop an element); flip a chart callout's `side` if a label overlaps. Look at every page and slide before presenting; `references/deck-content.md` explains how to check the deck. If the deck can't be built (no Node), say so plainly and deliver the PDF.
- **Summary in chat:** fill in `assets/seller-cma-template.md` from report.json and compute.py's output (numbers only from the output, already formatted), and end with its `handoff_block`.

Either way, reply briefly: the recommended price and range, the one or two facts driving it, how the three strategies compare, and what the agent can replace to sharpen the nets (brokerage terms, estimated costs, payoff, title company quote), as `references/local-costs.md` shows, plus any placeholder (update dates, flood zone). Say "Preliminary" plainly if compute.py marked it so. Offer the other format in one line. Keep the chat reply short when files are delivered (about 150 words): the files carry the detail, and a long reply repeating them gets skimmed.
