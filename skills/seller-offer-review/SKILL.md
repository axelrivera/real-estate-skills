---
name: seller-offer-review
description: Reviews purchase offers on a listing for the seller's agent. For each offer it computes the seller's net (as offered and if the appraisal or inspection goes badly), a certainty score, risk flags and a counter; with two or more offers it ranks them and lays out a plan (counter, backup, decline). Answers in chat or as a seller-ready PDF. Use it whenever a listing agent says "we got an offer", "analyze this offer", "should my seller accept", "what should we counter", "net sheet for this offer", "compare these offers", "we received multiple offers on my listing", "should we call for highest and best", "which offer is best", uploads a contract, pre-approval letter or offer summary, or another offer arrives on a listing that already has one. Works with just list price, offer price and financing. Florida (FR/BAR) costs are built in; other states use labeled national estimates, never Florida's numbers. Not for pricing a home before listing or writing a buyer's offer.
---

# Seller Offer Review

Every offer goes through the same engine: seller net sheet, downside case, certainty score, risk flags and a proposed counter. All offers on one property live in one listing file, so the single-offer and multi-offer answers never disagree. The math always runs in the scripts; never estimate a net or score by hand, because a seller will act on these numbers.

- **One active offer:** a single-offer review. Recommendation (Accept / Counter), the counter terms, key numbers, certainty, top risks and the seller's options.
- **Two or more active offers:** a two-page landscape decision summary, one row per offer so it holds any number of offers: the recommended offer, the plan and ranking in one table (counter / backup / decline), a net-vs-certainty chart up to 6 offers, and key terms side by side. The detail (net sheets, timeline, scorecard, checklist) lives in each offer's single review.
- **One offer while others are active** ("give me the report on the Park offer"): the single review, set in context. An offer worth countering alone may be a decline next to a stronger one.

## Guardrails

These apply to everything this skill writes: files, chat replies, and text the agent may forward to a client.

- **Fair housing.** Compare offers only on price, terms, financing mechanics, contingencies, deposits, timing and proof, never on who the buyer is. Buyer letters, photos and personal details are set aside unread and never scored; loan type is a term, described by what it changes, not by who uses it. Describe the property, the numbers and the terms, never people: not who the home suits, who should buy, or who lives nearby. No claims about safety, crime, school quality or who makes up an area. The protected classes are race, color, religion, sex, disability, familial status and national origin, plus sexual orientation, gender identity and any listed in the market's `fair_housing.extra_protected_classes`. Read `references/fair-housing.md` before writing the recommendation, risk flags or questions for the buyer's agent. If the agent asks for wording that breaks this, write the compliant version and say why in one sentence; don't lecture or flag innocent wording like "family room".
- **No em dashes in prose,** chat included: use a comma, colon, parentheses or a new sentence. A lone em dash for an empty value (a table cell with nothing in it) is fine.
- **Labels in Title Case:** headings, column headers, row names, tiles, legend entries, card and slide titles. Sentences, notes and table values stay sentence case.
- **Private financial details.** Pre-approval letters, proof of funds and bank statements carry account numbers, loan numbers and sometimes Social Security numbers: never copy those into the data file, the chat or a report (write "Account ending 1234" at most). Keep only the amounts and the lender's name the analysis needs. The listing file holds the seller's payoff: the review is for the seller, never for a buyer's agent.
- **`render.py` checks the data file first** and stops on an em dash in a sentence or a clear fair-housing red flag, naming each field. Rewrite the field; don't work around the check. It can't see chat replies, so the rules above still apply there.

## Never Block on Missing Data

The engine fills anything missing with a conservative default and records it as an assumption with an impact level. High-impact gaps (CMA range, payoff, concessions, financing) mark the answer **Preliminary**. Local costs and commission are never gaps: they have labeled defaults (`references/local-costs.md`). Build the answer with what you have, then ask for the two to four inputs that would change it most. Don't open with a questionnaire: agents answer faster once they see what's missing.

**Minimum to run:** list price, offer price and financing type. If one is missing, ask for just that.

## 1. Build the Listing File

One JSON file per property, in a temporary folder, never the outputs folder (`references/saved-files.md`, Working Files): read `references/listing-file.md` for the fields. When a new offer arrives later in the conversation, add it to the same file (next letter as `id`) rather than starting over; in a new conversation, rebuild the file from the offers the agent shares. Record `buyer_agent` and `buyer_brokerage` from the contract: reports name each offer by them ("Morales · Keller Williams"), never by the buyer, and never by the letter; see Offer Names in `references/listing-file.md`. In chat, use the same names; when the agent says "Offer B", match it to the id.

- **Contract or offer uploaded:** read the whole document, riders and counteroffers included (`pdftotext -layout`, or read scanned pages directly). For FR/BAR forms, and for how to read other states' contracts, read `references/contract-fields.md`. Then check the contract is complete with `references/contract-check.md` and record problems in `contract_issues`. For a condo (`listing.property_type: condo`), also read `references/condo.md`: FHA/VA project approval and the buyer's rescission windows decide when the deal is firm.
- **Pre-approval letter or proof of funds:** set `approval` and `lender`.
- **Offer described in chat:** take what's given.

Record only what the documents or the agent say. Leave a field out rather than guess: the engine's default is labeled, a guess isn't. Buyer letters, photos and personal details never go in the file or the report (fair housing).

**Value range (for appraisal risk):** use the CMA, in this order:
1. A seller CMA's `.cma.json` from earlier in this conversation (`references/saved-files.md`): pass it with `--cma`. Its low, high and midpoint become the appraisal range. A buyer-side CMA is flagged: its range was built for the other party.
2. Any other CMA (a CMA PDF from an earlier conversation, another tool's PDF, notes, a pasted range): read the low and high, confirm them with the agent in one line, and put them in `listing.cma_low` / `cma_high`.
3. Nothing: leave them out. Appraisal risk is measured against list price and the answer is Preliminary.

**Market costs:** read `references/local-costs.md`. The engine takes the state and county from the listing: Florida closing costs, title rates and tax proration are built in; elsewhere national estimates are labeled Estimate, never Florida's numbers. Outside Florida, look up the state's transfer tax from a trusted source and put it in `listing.costs`. Without terms, commission is assumed at 5% total. Read `references/seller-costs.md` when the agent asks where a cost comes from or has a title company quote.

## 2. Run and Review

```
python3 scripts/review.py listing.json [--cma file.cma.json] [--mode single|multi] [--offer ID]
```

It prints every value already formatted: the page-1 summary, each offer's net sheet, and the assumptions ranked by impact. Read it critically before answering; the rules are a first draft and the agent's judgment wins.

- **Scores** follow `references/scoring-rubric.md`. When the agent knows something the contract can't show (the lender call went badly, the buyer's agent is unreliable), set `scores.<criterion>` with a `why`.
- **Counters** follow `references/counter-rules.md`. Check the counter is realistic for this buyer: the engine counters a price above the value range back to its top instead of asking for gap money, and never asks an FHA or VA buyer for gap coverage (it wouldn't bind them).
- **Overrides:** `counter`, `recommendation` or `status` in the offer when the agent decides differently. Never change a number to make the recommendation look better.

## 3. Deliver

**Quick question** ("should we take it?", "what's the net?"): answer in two or three sentences from the output. **Full review in chat:** fill in `assets/offer-review-template.md` with the output's values. **A report for the seller:**

```
python3 scripts/render.py listing.json [--cma file.cma.json] [--mode single|multi] [--offer ID] [--packet] [--profile profile.md]
```

`--profile` puts the agent's name and colors on it (found as `references/saved-files.md` describes). It saves the PDF to the outputs folder in the agent's seller-side brand colors. Page 1 fits on one page; if it can't render, say so and give the markdown review instead. When the agent asks for every offer's report, the full set or the packet, add `--packet`: the comparison plus a single review of each active offer, in rank order, one PDF each. Otherwise render only what was asked.

In chat, keep it short: the recommendation with the net and certainty; the counter or the plan per offer; then the top missing inputs and estimates as one line the agent can answer after seeing the numbers, skipped when nothing high or medium is assumed. Offer the other format in one line. Always hand back the updated listing file: the sandbox resets between conversations, so say once "upload this with the next offer and I'll add it to the comparison."

## Offers Over Time

- New offer: append it; the mode switches to multi on its own.
- Counter rejected, offer expired or withdrawn: `status` `declined` / `expired`. It leaves the ranking but stays in the file.
- A buyer agrees to back up: `status: "backup"`. Counter accepted: `status: "accepted"`, and offer a contract timeline for the deadlines.

## Rules That Protect the Seller and the Agent

- **One counter out at a time** with multiple offers. Countering several buyers at once can produce two accepted contracts; the plan says so.
- **Present every offer.** The skill ranks offers; it never hides one. Only the seller drops an offer.
- **No recommendation on an incomplete contract.** When a contract can't be reviewed as written (a Blocking issue: unsigned, pages missing, price blank), the review still runs and shows every warning, but it's labeled CONTRACT INCOMPLETE with no accept, counter or decline, and the offer isn't ranked. Say what to fix; never say whether the contract is binding.
- **Not legal advice.** For unusual clauses, recommend a real estate attorney licensed in the property's state rather than interpreting them.
