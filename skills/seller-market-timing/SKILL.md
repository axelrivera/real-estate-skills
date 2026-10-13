---
name: seller-market-timing
description: Builds a Buying Pattern chart for a listing appointment, a one-page landscape scatter of a neighborhood's closed sales by month (each sale a dot at the month it went under contract, by sold price) with the busy season boxed, the busiest month marked, and when to list to be on the market as the season opens. Made from an MLS export of the last 24 months of closed sales (12 to 36). Delivered as a one-page PDF for the agent to talk through with the seller, or a month-by-month markdown table. Use it whenever an agent asks "when is the best time to list?", "market timing chart", "buying pattern", "seasonality for Sample Ridge", "when do homes sell in this neighborhood", "should we wait until spring?", or uploads closed sales and asks which months are busiest. Not for pricing a home (seller-cma) or a seller's net (seller-net-sheet).
---

# Seller Market Timing

The chart behind the "when should we list?" conversation: every closed sale in the neighborhood folded onto one January to December axis, so the seller sees when buyers commit and how far ahead to be on the market. It's the agent's tool for the listing appointment, not a client report: one page, no notes. Every count, season and date on it comes from the script; your part is the export, the area's name, and plain words around what the script found.

## Guardrails

These apply to everything this skill writes: files, chat replies, and text the agent may forward to a client.

- **Fair housing.** The chart is sales, prices and months only. Never describe who buys in the area, who lives there, or why a season is busy in terms of people (families, retirees, snowbirds, school-year moves). Talk about the market: sales, prices, days on market. If the agent asks for wording that breaks this, write the compliant version and say why in one sentence.
- **No em dashes in prose,** chat included: use a comma, colon, parentheses or a new sentence. A lone em dash for an empty value (a table cell with nothing in it) is fine.
- **Labels in Title Case:** headings, column headers, legend entries and the `area` name. Sentences and table values stay sentence case.
- **The area name is a name, never a figure or a description:** "Sample Ridge", never "Sample Ridge 2 Story Homes" or "Sample Ridge, Great Schools".
- **`render.py` checks the data file first** and stops on an em dash in a sentence, a clear fair-housing red flag, or tool words, data keys or jargon in client text (`references/client-wording.md`). Rewrite the field; don't work around the check.

## 1. Get the Export

The chart needs an MLS export (CSV) of **closed sales** in the neighborhood: the more homes like the seller's, the better (one subdivision, or a tight radius with similar homes). Ask for it if it isn't in the chat. Tell the agent how, in short lines:

- Search sold listings in the neighborhood with a close date in the **last 26 months** (38 for a three-year chart): the extra two months catch sales that went under contract at the start of the window.
- Export with the **Contract Date** (Purchase Contract Date), **Close Date**, **Close Price** and **CDOM** columns. Stellar's CMA export has them; another MLS needs its headers mapped (`references/market-timing-data.md`).

Also take the area's name for the chart (the subdivision or neighborhood) and its county and state, which pick the MLS's column names. No profile is needed; with one, the chart uses the agent's brand color (`references/saved-files.md`).

**How much data:** 24 months by default, so every month has two seasons behind it and a pattern can repeat. 12 months is one season, where one unusual month looks like a trend; 36 is the strongest read. Use what the agent asks for (12, 24 or 36).

## 2. Write market-timing.json and Compute

Write `market-timing.json` in a temporary folder, never the outputs folder (`references/saved-files.md`, Working Files). Start from `assets/example-market-timing.json` (mock data: take its shape, never a value). Every field is in `references/market-timing-data.md`. When the agent states today's date, it's `as_of`.

```
python3 scripts/compute.py market-timing.json
```

It prints the subtitle, the `takeaway`, a row per month (sales, median sold price, busy or busiest), the `seasons`, `peak_month`, `list_by` and `warnings`. Fix any `problems` it names (a missing column, no sales in the window) and re-run. Never count sales, pick a season or work out a listing date yourself.

When the agent knows the season differs from what the sales show ("our season really starts in February"), set `season_override` to those months; the chart boxes them and the run says the season is the agent's.

## 3. Deliver

- **PDF** (the default: it's for the listing appointment):
  ```
  python3 scripts/render.py market-timing.json [--profile profile.md]
  ```
  One landscape page. Look at the page before presenting it.
- **Markdown** (a quick question in chat): fill `assets/market-timing-template.md` from compute.py's output only. Never paste JSON.

Either way, the reply holds, in short lines under about 120 words:

1. The `takeaway`, as written.
2. Each `warnings` item, plainly, with what fixes it (a longer export, the Contract Date column).
3. One or two talking points from the numbers, in the agent's voice: how many sales fell in the season, and how the `list_by` date relates to the seller's timeline. Never a reason about people.
4. The other format, offered in one line.
