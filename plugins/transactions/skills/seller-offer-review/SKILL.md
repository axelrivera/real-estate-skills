---
name: seller-offer-review
description: Reviews purchase offers on a listing for the seller's agent. For each offer it computes the seller's net (as offered and if the appraisal or inspection goes badly), a certainty score, risk flags and a counter; with two or more offers it ranks them and lays out a plan (counter, backup, decline). Answers in chat or as a seller-ready PDF. Use it whenever a listing agent says "we got an offer", "analyze this offer", "should my seller accept", "what should we counter", "net sheet for this offer", "compare these offers", "we have multiple offers", "highest and best", "which offer is best", uploads a contract, pre-approval letter or offer summary, or another offer arrives on a listing that already has one. Works with just list price, offer price and financing. Florida (FR/BAR) costs are built in; other states use the agent's market profile. Not for pricing a home before listing or writing a buyer's offer.
---

# Seller offer review

Every offer goes through the same engine: seller net sheet, downside case, certainty score, risk flags and a proposed counter. All offers on one property live in one listing file, so the single-offer and multi-offer answers never disagree. The math always runs in the scripts; never estimate a net or score by hand, because a seller will act on these numbers.

- **One active offer:** a single-offer review. Recommendation (Accept / Counter), the counter terms, key numbers, certainty, top risks and the seller's options.
- **Two or more active offers:** a comparison. The recommended offer, a plan for every offer (counter / backup / decline), the ranking and a net-vs-certainty chart.
- **One offer while others are active** ("give me the report on Offer B"): the single review, set in context. An offer worth countering alone may be a decline next to a stronger one.

## Never block on missing data

The engine fills anything missing with a conservative default and records it as an assumption with an impact level. High-impact gaps (CMA range, payoff, listing fee, concessions, buyer-broker pay, and outside Florida the local closing costs) mark the answer **Preliminary**. Build the answer with what you have, then ask for the two to four inputs that would change it most. Don't open with a questionnaire: agents answer faster once they see what's missing.

**Minimum to run:** list price, offer price and financing type. If one is missing, ask for just that.

## 1. Build the listing file

One JSON file per property: read `references/listing-file.md` for the fields. If the agent uploads a listing file from an earlier session, add the new offer to it (next letter as `id`) rather than starting over.

- **Contract or offer uploaded:** read the whole document, riders and counteroffers included (`pdftotext -layout`, or read scanned pages directly). For FR/BAR forms, and for how to read other states' contracts, read `references/contract-fields.md`.
- **Pre-approval letter or proof of funds:** set `approval` and `lender`.
- **Offer described in chat:** take what's given.

Record only what the documents or the agent say. Leave a field out rather than guess: the engine's default is labeled, a guess isn't. Buyer letters, photos and personal details never go in the file or the report (fair housing).

**Value range (for appraisal risk):** use the CMA, in this order:
1. A `.cma.json` file or a markdown reply with a `cma-handoff v1` block (from a seller CMA): pass it with `--cma`. Its low, high and midpoint become the appraisal range.
2. Any other CMA (another tool's PDF, notes, a pasted range): read the low and high, confirm them with the agent in one line, and put them in `listing.cma_low` / `cma_high`.
3. Nothing: leave them out. Appraisal risk is measured against list price and the answer is Preliminary.

**Market costs:** Florida closing costs, title rates, brokerage defaults and tax proration are built in. Include the agent's market profile when there is one (project files, uploads). Outside Florida without a profile, nothing is filled in from Florida: missing costs are left out and flagged. Read `references/seller-costs.md` when the agent asks where a cost comes from or has a title company quote.

## 2. Run and review

```
python3 scripts/review.py listing.json [--cma file.cma.json] [--market market-profile.md] [--mode single|multi] [--offer B]
```

It prints every value already formatted: the page-1 summary, each offer's net sheet, and the assumptions ranked by impact. Read it critically before answering; the rules are a first draft and the agent's judgment wins.

- **Scores** follow `references/scoring-rubric.md`. When the agent knows something the contract can't show (the lender call went badly, the buyer's agent is unreliable), set `scores.<criterion>` with a `why`.
- **Counters** follow `references/counter-rules.md`. Check the counter is realistic for this buyer: a 3.5%-down FHA buyer who asked for concessions probably can't also fund an appraisal gap. The engine adds a fallback counter for that case; mention it.
- **Overrides:** `counter`, `recommendation` or `status` in the offer when the agent decides differently. Never change a number to make the recommendation look better.

## 3. Deliver

**Quick question** ("should we take it?", "what's the net?"): answer in two or three sentences from the output. **Full review in chat:** fill in `assets/offer-review-template.md` with the output's values. **A report for the seller:**

```
python3 scripts/render.py listing.json [--cma file.cma.json] [--mode single|multi] [--offer B] [--agent agent-profile.md] [--market market-profile.md]
```

It saves the PDF to the outputs folder in the agent's seller-side brand colors. Page 1 fits on one page; if it can't render, say so and give the markdown review instead.

In chat, keep it short: the recommendation with the net and certainty; the counter (and fallback) or the plan per offer; then the top missing inputs as one question, skipped when nothing high or medium is assumed. Offer the other format in one line. Always hand back the updated listing file: the sandbox resets between conversations, so say once "upload this with the next offer and I'll add it to the comparison."

## Offers over time

- New offer: append it; the mode switches to multi on its own.
- Counter rejected, offer expired or withdrawn: `status` `declined` / `expired`. It leaves the ranking but stays in the file.
- A buyer agrees to back up: `status: "backup"`. Counter accepted: `status: "accepted"`, and offer a contract timeline for the deadlines.

## Rules that protect the seller and the agent

- **One counter out at a time** with multiple offers. Countering several buyers at once can produce two accepted contracts; the plan says so.
- **Present every offer.** The skill ranks offers; it never hides one. Only the seller drops an offer.
- **Not legal advice.** For unusual clauses, recommend a real estate attorney licensed in the property's state rather than interpreting them.
