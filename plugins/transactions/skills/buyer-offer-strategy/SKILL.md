---
name: buyer-offer-strategy
description: Builds a buyer's offer for the buyer's agent. Finds the strongest offer inside the buyer's limits (max price, payment, cash, reserve, loan program caps), adds up to two alternatives with what each changes and costs, and shows the outlook against competing offers and the buyer's cash exposure, scored the way the listing agent will score it. Produces an Offer Options report and an Offer Package Worksheet (contract entries, riders, draft terms, checklist). Use it whenever a buyer's agent asks "what should we offer", "help me write an offer", "how do we win this house", "should we add an appraisal gap or escalation", "prepare the offer package", "we're in multiple offers" or "highest and best", or has a buyer CMA and wants to move to an offer. Works with just list price and the buyer's cash; sharpens with a CMA, lender numbers and listing-agent intel. Florida (FR/BAR) is built in; other states use the agent's market profile. Not for reviewing offers a seller received.
---

# Buyer offer strategy

Two files from one analysis:

1. **Offer Options report** (for the buyer and the agent). Page 1: the recommended offer with a reason for every term, the alternatives, the outlook at four competition levels and the buyer's cash exposure. Then the detail: options side by side, the seller's net sheet as the listing agent sees it, the strength scorecard, cash and risk, market check, likely pushback and assumptions.
2. **Offer Package Worksheet** (for the agent). For the option the buyer picks: contract entries, riders with suggested inputs, draft additional terms, the package checklist and what to request from the seller. It prints offer terms only, never the buyer's max, cash or reserve, so it's safe in the transaction file.

"Best" means the strongest outlook inside the buyer's limits at the lowest cost that reaches it. Every option is scored by the same engine the listing side uses (seller net, appraisal downside, certainty score, likely counter), because that's how the listing agent will read it. The math runs in the scripts; never estimate a payment, net or score by hand.

## Principles

- **The buyer's limits are hard limits.** Never recommend terms above the max price, the max payment, the loan program's concession cap, or more cash than the buyer has. Dipping below the reserve floor appears only as the "Stronger" option, labeled the buyer's call.
- **Honest outlook.** Bands (Strong / Competitive / At risk / Unlikely), never a "% chance": they're judgments until enough results are logged to calibrate them.
- **Financing is an input.** Loan type and down payment come from the buyer and lender. If missing, the default (conventional; 20% down at $1M+, 3% for a first-time buyer, 5% otherwise) is flagged to confirm. FHA, VA or USDA only when given.
- **Don't block on missing data.** Conservative defaults are logged; page 1 says **Preliminary** when a high-impact input is assumed, and says plainly when the buyer can't afford the offer.
- **The agent's judgment wins.** Their decisions go in `overrides`, are marked in the report, and the alternatives are built from them.

## 1. Build the buyer file

One JSON file per property the buyer is pursuing: read `references/buyer-file.md` for the fields.

- **Value range and market stats:** use the CMA, in this order:
  1. A `.cma.json` file or a markdown reply with a `cma-handoff v1` block (from a buyer CMA): pass it with `--cma`. It fills the value range, the median adjusted comp price (the price anchor), subject facts and market stats.
  2. Any other CMA (another tool's PDF, notes): read the low, high and any market stats, confirm them with the agent in one line, and put them in `value` and `market`.
  3. Nothing: list price stands in for value and the answer is Preliminary.
- **Buyer:** loan type and down payment, first-time buyer or not, max price, cash available, reserve floor, max payment.
- **Listing-agent intel:** competition level, offer deadline, buyer-broker pay offered, seller priorities. This is the most valuable input; if it's unknown, run with the inferred level and say so in one line.
- **Worksheet details:** buyer names, escrow agent, HOA name, personal property. Never invent names, legal descriptions or parcel IDs: missing ones print as red blanks.

**Minimum to run:** list price and cash available.

Include the agent's market profile when there is one. Florida costs are built in; outside Florida nothing is filled in from Florida, and missing local costs are flagged.

## 2. Run and review

```
python3 scripts/strategy.py buyer.json [--cma file.cma.json] [--market market-profile.md] [--option recommended|stronger|lower_cost]
```

It prints every value already formatted: the page-1 summary, the options side by side, the market check, the worksheet for the chosen option, and the assumptions. Review with judgment; the rules in `references/offer-rules.md` are a first draft. Does the price fit the home's condition? Are the concessions realistic here? Is the inspection period right for the home's age? Record decisions as `overrides`. Loan program caps and payment rules are in `references/loan-programs.md`.

## 3. Deliver

**Quick question** ("what should we offer?"): two or three sentences from the output. **Full answer in chat:** fill in `assets/offer-strategy-template.md`. **Files:**

```
python3 scripts/render.py buyer.json [--format options|worksheet|all] [--cma file.cma.json] [--option stronger] [--agent agent-profile.md] [--market market-profile.md]
```

`all` (the default) saves both PDFs in the agent's buyer-side brand colors. The worksheet uses the file's `chosen_option` (else recommended); when the buyer hasn't chosen, build it for the recommended option and say it will be redone if they pick another. Check the rider list against the facts (the insurance rider can be skipped when a quote is in hand). Contract entries and riders for FR/BAR and other states: `references/worksheet.md`. If rendering fails, say so and give the markdown answer.

In chat: the recommended offer (price, key terms, outlook) in one or two sentences; the choice the buyer faces ("Stronger costs $2,000 more and doesn't change the outlook; lower-cost saves $3,570 but drops to At risk"); the top missing input as one question (usually the listing agent's competition read). Hand back the updated buyer file for next time.

## Guardrails

- **Pre-approval letter at the offer price,** never the buyer's max.
- **No personal letters, photos or buyer background** in the package (fair housing).
- **Program limits and payments are estimates;** the lender's Loan Estimate wins.
- **Draft clause language is for broker review,** not legal advice. For unusual terms, recommend a real estate attorney licensed in the property's state.
