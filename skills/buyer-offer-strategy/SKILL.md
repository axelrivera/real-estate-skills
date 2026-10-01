---
name: buyer-offer-strategy
description: Builds a buyer's offer for the buyer's agent. Finds the strongest offer inside the buyer's limits (max price, payment, cash, reserve, loan program caps), up to two alternatives with what each changes and costs, and the outlook against competing offers scored as the listing agent will. Produces an Offer Options report and an Offer Package Worksheet (contract entries, riders, checklist). Use it whenever a buyer's agent asks "what should we offer", "help me write an offer", "how do we win this house", "should we add an appraisal gap or escalation", "prepare the offer package", "my buyer is in multiple offers" or "the listing agent wants our highest and best", or has a buyer CMA and wants an offer. Works with just list price and the buyer's cash. Florida FR/BAR contracts and their riders are fully supported; other contracts get a best-effort worksheet with labeled national estimates, never Florida's numbers. Not for reviewing offers a seller received.
---

# Buyer Offer Strategy

Two files from one analysis:

1. **Offer Options report** (for the buyer and the agent). Page 1: the recommended offer with a reason for every term, the alternatives, the outlook at four competition levels and the buyer's cash exposure. Then the detail: options side by side, the seller's net sheet as the listing agent sees it, the strength scorecard, cash and risk, market check, likely pushback and assumptions.
2. **Offer Package Worksheet** (for the agent). For the option the buyer picks: contract entries, riders with suggested inputs, draft additional terms, the package checklist and what to request from the seller. It prints offer terms only, never the buyer's max, cash or reserve, so it's safe in the transaction file.

"Best" means the strongest outlook inside the buyer's limits at the lowest cost that reaches it. Every option is scored by the same engine the listing side uses (seller net, appraisal downside, certainty score, likely counter), because that's how the listing agent will read it. The math runs in the scripts; never estimate a payment, net or score by hand.

## Guardrails

These apply to everything this skill writes: files, chat replies, and text the agent may forward to a client.

- **Fair housing.** No personal letters, photos or buyer background in the package, and reasons, pushback and clause language are about terms. Describe the property, the numbers and the terms, never people: not who the home suits, who should buy, or who lives nearby. No claims about safety, crime, school quality or who makes up an area. The protected classes are race, color, religion, sex, disability, familial status and national origin, plus sexual orientation, gender identity and any listed in the market's `fair_housing.extra_protected_classes`. Read `references/fair-housing.md` before writing reasons, pushback or clause language. If the agent asks for wording that breaks this, write the compliant version and say why in one sentence; don't lecture or flag innocent wording like "family room".
- **People by name, never by pronoun.** In chat, call the parties "the buyer", "the seller" or by their names; never guess a pronoun from a name.
- **No em dashes in prose,** chat included: use a comma, colon, parentheses or a new sentence. A lone em dash for an empty value (a table cell with nothing in it) is fine.
- **Labels in Title Case:** headings, column headers, row names, tiles, legend entries, card and slide titles. Sentences, notes and table values stay sentence case.
- **Private financial details.** Pre-approval letters, proof of funds and bank statements carry account numbers, loan numbers and sometimes Social Security numbers: never copy those into the data file, the chat or a report (write "Account ending 1234" at most). Keep only the amounts and the lender's name the analysis needs. The Offer Options report holds the buyer's limits and cash: it's for the buyer only, and its footer says so; never send it to the listing side (the worksheet holds only offer terms).
- **Contract support.** Only Florida FR/BAR contracts (AS IS and Standard, with their CR-7 riders and addenda) are fully supported. For any other contract the script output has `support: "best_effort"` and the line in `chat_notes`: pass it on once in chat, word for word, in its own paragraph. The same goes for a note that an FR/BAR contract isn't the revision the rules were checked against. Never put either in a PDF, calendar file, worksheet or markdown report. On another contract the script uses generic words (an "inspection or option period", appraisal protection per the contract's addendum); an option fee, a financing addendum's appraisal terms and anything else form-specific come from the agent's contract on a best-effort basis: the `contract_terms` entry of `reply_lines` names them in chat; never fill them from Florida's rules. The period's length and the Deposit at Risk After date there are drafts from the offer's own terms, marked for the agent to confirm against their contract.
- **`render.py` checks the data file first** and stops on an em dash in a sentence or a clear fair-housing red flag, naming each field. Rewrite the field; don't work around the check. It can't see chat replies, so the rules above still apply there.

## Principles

- **The buyer's limits are hard limits.** Never recommend terms above the max price, the max payment, the loan program's concession cap, or more cash than the buyer has. Dipping below the reserve floor appears only as the "Stronger" option, labeled the buyer's call.
- **Honest outlook.** Bands (Strong / Competitive / At Risk / Unlikely), never a "% chance": they're judgments until enough results are logged to calibrate them.
- **Financing is an input.** Loan type and down payment come from the buyer and lender. If missing, the default (conventional; 20% down at $1M+, 3% for a first-time buyer, 5% otherwise) is flagged to confirm. FHA, VA or USDA only when given.
- **Don't block on missing data.** Conservative defaults are logged; page 1 says **Preliminary** when a high-impact input is assumed, and says plainly when the buyer can't afford the offer.
- **The agent's judgment wins.** Their decisions go in `overrides`, are marked in the report, and the alternatives are built from them.

## 1. Build the Buyer File

One JSON file per property the buyer is pursuing, in a temporary folder, never the outputs folder (`references/saved-files.md`, Working Files): read `references/buyer-file.md` for the fields. For a condo (`property.type: condo`), also read `references/condo.md` for lender approval, association questions and the buyer's rescission rights.

- **Value range and market stats:** use the CMA, in this order:
  1. A buyer CMA's `.cma.json` (`references/saved-files.md`), including one built earlier in this conversation: pass it with `--cma`. One the agent attaches with this request wins over one from earlier in the conversation; a PDF of the same CMA (same range) doesn't replace its `.cma.json`. It fills the value range, the median adjusted comp price (the price anchor), subject facts (with days on market and price cuts) and market stats. A seller-side CMA is flagged: its range was built for the other party.
  2. Any other CMA (a CMA PDF from an earlier conversation, another tool's PDF, notes): read the low, high, the subject's days on market and price cuts, and any market stats, and put them in `value`, `property.dom`, `property.price_cuts` and `market`.

  Whichever CMA is used, wherever it came from (attached now, built earlier in this conversation, or a PDF), the reply says in one line which one and its range ("Using the buyer CMA from earlier: $435,000–$450,000."); for an "other" CMA the line asks the agent to confirm it.
  3. Nothing: list price stands in for value, so the price stays at list (never called "at value"), the appraisal gap is a question for the buyer, and the answer is Preliminary.
- **Buyer:** loan type and down payment, first-time buyer or not, max price, cash available, reserve floor, max payment.
- **Listing-agent intel:** competition level, whether they called for highest and best, offer deadline (dates count from the day after it, or from `expected_effective_date`; enter a weekday deadline as the agent said it, "Friday 5 PM", and the script resolves it), buyer-broker pay offered, seller priorities. This is the most valuable input; if it's unknown, run with the inferred level and say so in one line.
- **Worksheet details:** buyer names, escrow agent, HOA name, personal property. Never invent names, legal descriptions or parcel IDs: missing ones print as red blanks.
- **Lender:** `lender_called` when the agent talked to the lender about the financing; `lender_confirmed_timeline` only when the lender confirmed the closing timeline too (it ticks the checklist's closing box). A call about the loan isn't a confirmed date.

**Minimum to run:** list price and cash available.

**Rate:** a lender's quote goes in `costs.rate` alone, with no `rate_source`. When the agent gives none, look up the latest Freddie Mac weekly (PMMS) 30-year average and enter it as `costs.rate` with `costs.rate_source` naming the week ("Freddie Mac weekly 30-year average, week of Sep 24, 2026"). The built-in 6.5% is only the offline fallback, labeled Assumed. The rate matters most when the payment limit sets the price.

Local costs come from the property's location (`references/local-costs.md`): Florida's are built in; elsewhere national estimates are labeled Estimate, never Florida's numbers. Don't ask about them up front; seller-side figures (a title quote, a looked-up transfer tax) go in `property.costs`, and the buyer's rate, insurance and tax rate in the top-level `costs` block.

## 2. Run and Review

```
python3 scripts/strategy.py buyer.json [--cma file.cma.json] [--option recommended|stronger|lower_cost]
```

It prints every value already formatted: the page-1 summary, the options side by side, the market check, the worksheet for the chosen option, and the assumptions. Review with judgment; the rules in `references/offer-rules.md` are a first draft. Does the price fit the home's condition? Are the concessions realistic here? Is the inspection period right for the home's age? Record decisions as `overrides`. Loan program caps and payment rules are in `references/loan-programs.md`.

## 3. Deliver

**Chat or files.** Make files only when the agent asks for the report, the worksheet or the package. A question ("what should we offer?", "should we escalate?") gets the quick answer in chat, even when a CMA and full buyer inputs came with it; its last line offers the files.

**Quick answer:** build the buyer file from what the agent gave and run `strategy.py` anyway (the numbers come from it), but make no files. The reply must contain:

- the answer to the agent's question first when they asked one (escalate or not: the Escalation row of `summary.terms`, with its reason: what a higher price would put above the value range);
- the recommended price, deposit, concessions and key periods, with the outlook and the competition level it assumed;
- the price's reason from the Price row of `summary.terms`: with no CMA the price stays at list ("list stands in for value"), never "at value"; when the payment limit set it, the reason names the assumed rate or insurance it rests on;
- "Preliminary" when `summary.preliminary` is set, naming what it says was assumed (the max price with its assumed amount);
- **one question with at most two parts:** the first two entries of `to_confirm` other than the value range (the script puts an inferred competition read first, then an offer deadline that may already have passed, then the rest by impact; the value range is left to the CMA tip). With no CMA, the appraisal-gap question ("how much of a low appraisal could the buyer cover in cash?") replaces the second entry; everything else waits for the report's assumptions;
- one line offering the report, with a tip that a buyer CMA sharpens the price (no tip when a CMA was used).

Keep it to about three short paragraphs (220 words at most). When it runs over, drop in this order: payment and cash figures, the alternative options, the CMA tip. Outside the cap and never dropped, each in its own short paragraph: every `reply_lines` entry, word for word (`flat_number`: why one flat number in a highest-and-best round with no escalation; `contract_terms`: on a contract that isn't FR/BAR, the option fee and the financing addendum's appraisal terms come from the agent's contract; `inspection_period`: on that contract, the period's length is a generic default to confirm locally, until the agent sets it in `overrides`; `tight_reserve`: the offer keeps the reserve floor with a thin cushion and, when there is one, names a same-outlook offer with its payment difference and the cash it keeps; that offer is the buyer's choice with its trade-off, never recommended over the answer's offer), and the best-effort line from `chat_notes`, word for word. `market_notes` are for you: put one in the reply (one line) only when it changes a number in the answer, such as a transfer tax or rate assumed for another state; the rest stay in the report's assumptions. When the answer quotes a payment and the agent gave a tax rate, add that the payment assumes no homestead exemption unless that rate already includes one (`references/local-costs.md`).

**Only the fair-housing part** (the agent asks to include a buyer letter, a family photo or a note about the buyers, and asks for no offer, report or worksheet; an attached CMA doesn't change this): don't run the scripts or ask for the buyer's finances. Answer in chat: the one-sentence reason from `references/fair-housing.md` (When the Agent Asks for It), then the cover note on the terms with the property's address filled in when it's known (from the request or the CMA) and every term left in [brackets] for the agent to fill from the offer they chose; a CMA's suggested prices aren't the buyer's offer. Write "The buyers" when the agent mentions more than one. If they want the numbers filled, ask for the offer terms.

**Full answer in chat:** fill in `assets/offer-strategy-template.md`. **Files:**

```
python3 scripts/render.py buyer.json [--format options|worksheet|all] [--cma file.cma.json] [--option stronger] [--profile profile.md]
```

`all` (the default) saves both PDFs in the agent's buyer-side brand colors; `--profile` puts the agent's name and colors on them (found as `references/saved-files.md` describes). The worksheet uses the file's `chosen_option` (else recommended); when the buyer hasn't chosen, build it for the recommended option and say it will be redone if they pick another. Check the rider list against the facts (the insurance rider can be skipped when a quote is in hand). Contract entries and riders: `references/worksheet.md`; for FR/BAR, what each rider and addendum requires is in `references/frbar-riders.md` and `references/frbar-addenda.md` (check the package against `references/frbar-package-check.md`, and `references/frbar-contract.md` for any paragraph); for any other contract, `references/other-contracts.md`. If rendering fails, say so and give the markdown answer.

In chat: the recommended offer (price, key terms, outlook) in one or two sentences; the choice the buyer faces ("Stronger costs $2,000 more and doesn't change the outlook; lower-cost saves $3,570 but drops to At Risk"), or, when an option is missing, why (`summary.absent`); the top missing inputs as one question with at most two parts (the first two entries of `to_confirm`), every `reply_lines` entry and the best-effort line from `chat_notes`, word for word, when there are any. The chat never recommends a different offer than the files: the `tight_reserve` alternative stays the buyer's choice as its line words it (don't add "I'd lean toward" or reasons of your own). When the agent picks it, record the terms in `overrides` and rebuild both files. The buyer file stays in the temporary folder and is never handed over (`references/saved-files.md`); in a later conversation, rebuild it from what the agent gives again.

## Package Rules

- **Pre-approval letter at the offer price,** never the buyer's max.
- **Program limits and payments are estimates;** the lender's Loan Estimate wins.
- **Draft clause language is for broker review,** not legal advice. For unusual terms, recommend a real estate attorney licensed in the property's state.
