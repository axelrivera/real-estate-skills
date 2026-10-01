---
name: seller-net-sheet
description: Builds a one-page seller net sheet, with what a seller walks away with at one to three prices, without a CMA or an offer. It itemizes brokerage, transfer tax, owner's title, title company fees, HOA estoppel, the property tax proration, seller credits, warranty and repairs, then the mortgage and other payoffs, down to the estimated cash at closing. Delivered as a one-page PDF or a markdown table. Use it whenever an agent asks "what would my seller net at $450,000?", "net sheet for 123 Oak St", "seller proceeds", "estimated net at list price", "how much would they walk away with", "what if we drop the price to $440,000", "net with a $10,000 credit", or before a listing appointment when there's no time for a full CMA. Florida costs are built in; other states use labeled national estimates. Not for reviewing an offer the seller received (seller-offer-review) or pricing a home with comps (seller-cma).
---

# Seller Net Sheet

The quick number a seller asks for first: "what do I walk away with?" One page, one to three prices side by side, every cost itemized and labeled with where it came from. It works because every number comes from the script, the same seller-net math the CMA and the offer review use, so the three never disagree. Your part is the intake and plain words around the numbers.

A wrong net in front of a seller is the worst failure here: never calculate or adjust a figure by hand, and never invent a payoff, tax bill or commission.

## Guardrails

These apply to everything this skill writes: files, chat replies, and text the agent may forward to a client.

- **Fair housing.** The net sheet is numbers and terms only: never describe the buyer, the seller or the neighborhood, and never write who the home suits. If the agent asks for wording that breaks this, write the compliant version (or leave it out: the sheet has no free-text note) and say why in exactly one sentence, nothing more, for example: "The net sheet shows numbers and terms only, never who the home suits, which fair housing rules keep off it." Don't list protected classes: they vary by state and county (age, for one, isn't in the federal law).
- **No em dashes in prose,** chat included: use a comma, colon, parentheses or a new sentence. A lone em dash for an empty value (a table cell with nothing in it) is fine.
- **Labels in Title Case:** headings, column headers, row names, tiles and legend entries (and the price `label`s you write). Sentences, notes and table values stay sentence case.
- **Names, not pronouns.** Call the seller by name or "the seller"; never infer a pronoun from a name.
- **Private details.** A payoff letter or mortgage statement carries loan numbers: keep only the amounts.
- **`render.py` checks the data file first** and stops on an em dash in a sentence or a clear fair-housing red flag, naming each field. Rewrite the field; don't work around the check.

## When to Use Another Skill's Job Instead

- **An offer is in hand** ("net sheet for this offer", a contract or offer summary uploaded): that's an offer review, which also checks the terms, the downside and a counter. Say so in one line and don't build a net sheet from the offer. If the seller-offer-review skill isn't available, build the net sheet at the offer's price with its seller credit, and say it doesn't review the offer's terms.
- **"What should we list at?"** needs comps: that's a seller CMA. A net sheet at a price the agent names is fine.

## 1. Gather the Inputs

Build first, ask after: local costs and commission are never questions up front (`references/local-costs.md`). Take what's in the chat, the MLS sheet or the property report.

- **Needed:** the address with its city and state, and at least one price. Ask only for what's missing of these. Never guess the county or state from a subdivision or the MLS.
- **County:** take it from the city when the city lies in one county (Miami: Miami-Dade). When the city spans counties (Austin: Travis, Williamson, Hays), ask: in Florida before building, since it sets the local costs; elsewhere after the first sheet, saying the county only changes the tax estimate.
- **Property type:** a unit number (#1204) means a condo (`property_type` `condo`, `hoa` true) unless the agent says otherwise; set `property_type_assumed` so it's listed as an assumption.
- **Worth having** (use them when given, ask after the first sheet when not): the mortgage payoff (without it the sheet stops at the net before payoff and is marked Preliminary), the listing agreement's commission, the expected closing date and this year's tax bill (together they set the proration), HOA, property type. A vague closing date ("mid-December", "early November") becomes a likely date (the 15th, the 6th) with `closing_date_assumed` true. When the agent gives the tax bill's due date, add it (`tax_bill_due_date`): a closing after it assumes the bill paid.
- **Up to three prices.** One by default. Add more when the agent asks "what if": a price cut, a seller credit at the same price, a different closing date. Each is a scenario; give it a short Title Case `label` when the price alone doesn't say what it is.
- **A seller CMA from this conversation:** pass its `.seller.cma.json` with `--cma`. It fills the location, tax bill and HOA dues, and the recommended price when no price was given.

For the PDF, the agent's name and brokerage go on it: use their profile (found as `references/saved-files.md` describes) and pass it with `--profile`. With no profile, build without them and say so in one line.

## 2. Write net-sheet.json and Compute

Write `net-sheet.json` in a temporary folder, never the outputs folder (`references/saved-files.md`, Working Files). Start from `assets/example-net-sheet.json` (mock data: take its shape, never a value). Every field is in `references/net-sheet-data.md`. When the agent states today's date, it's `prepared_date`.

```
python3 scripts/compute.py net-sheet.json [--cma FILE.seller.cma.json]
```

It prints the columns, the itemized rows (already formatted), `notes`, `assumptions`, `warnings` and `preliminary`. Fix any `problems` it names and re-run. Outside Florida, look up the state's deed transfer tax as `references/local-costs.md` says (none in the states without one) and put it in `costs`. Also outside Florida (Florida's bills are due the next March), when the closing falls in the last months of the year and the agent didn't give the tax bill's due date, look it up on the county tax office's site and set `tax_bill_due_date` (a closing after it assumes the bill paid); name the source in the reply.

## 3. Deliver

- **PDF** (the default when the agent wants something to send or print):
  ```
  python3 scripts/render.py net-sheet.json [--cma FILE.seller.cma.json] [--profile profile.md]
  ```
  It always fits one page, and stops if it wouldn't or a label would be cut off (shorten the price labels or other cost names). Look at the page before presenting it.
- **Markdown** (a quick question in chat): fill `assets/net-sheet-template.md` from compute.py's output only. Never paste JSON.

Either way, the reply holds, in this order, in short bullets under about 200 words:

1. The nets at every price together in one line, not a bullet each (the tiles' numbers), and what separates them when there's more than one.
2. Each item in `assumptions`, one short line each: what's assumed and what replaces it (the listing agreement, a payoff letter, the tax bill, a title quote).
3. Each `warnings` item, plainly. A sale where the seller would bring money to closing is said first.
4. "Preliminary" with `preliminary_reason`, when it's marked so.
5. Outside Florida, one line: who customarily pays the owner's title policy differs by state (the sheet charges the seller); the agent's word or a title quote sets `title_payer`.
6. The other format, offered in one line.

`market_notes` explain where the costs came from; most are covered by the assumptions. Mention one only when it asks the agent for something the assumptions don't (a misspelled county).

When the agent sends better numbers (a payoff letter, the commission, the tax bill, a title quote), put them in the same `net-sheet.json` and render again; never edit a number in the reply by hand.
