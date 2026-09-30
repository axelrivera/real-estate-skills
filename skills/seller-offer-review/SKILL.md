---
name: seller-offer-review
description: Reviews purchase offers on a listing for the seller's agent. For each offer it computes the seller's net (as offered and if the appraisal or inspection goes badly), a certainty score, risk flags and a counter; with two or more offers it ranks them and lays out a plan (counter, backup, decline). Answers in chat or as a seller-ready PDF. Use it whenever a listing agent says "we got an offer", "analyze this offer", "should my seller accept", "what should we counter", "net sheet for this offer", "compare these offers", "we got multiple offers", "should we call for highest and best", uploads a contract, pre-approval letter or offer summary, or another offer arrives on a listing that already has one. Works with just list price, offer price and financing. Florida FR/BAR contracts and costs are fully supported; other contracts get a best-effort read. Not for pricing a home before listing or writing a buyer's offer.
---

# Seller Offer Review

Every offer goes through the same engine: seller net sheet, downside case, certainty score, risk flags and a proposed counter. All offers on one property live in one listing file, so the answers never disagree. The math always runs in the scripts; never estimate a net or score by hand. One active offer gets a single review (Accept or Counter, the counter, key numbers, certainty, risks, options); two or more get a two-page decision summary (plan and ranking, chart, key terms), with the detail in each offer's single review.

## Guardrails

These apply to everything this skill writes: files, chat replies, and text the agent may forward to a client.

- **Fair housing.** Compare offers only on price, terms, financing mechanics, contingencies, deposits, timing and proof, never on who the buyer is. Buyer letters, photos and personal details are set aside unread and never scored; loan type is a term, described by what it changes, not by who uses it. Describe the property, the numbers and the terms, never people: not who the home suits, who should buy, or who lives nearby. No claims about safety, crime, school quality or who makes up an area. The protected classes are race, color, religion, sex, disability, familial status and national origin, plus sexual orientation, gender identity and any listed in the market's `fair_housing.extra_protected_classes`. If the seller already saw a buyer letter, or the terms ranking happens to match a request on a protected ground, rank on terms and write down the terms reason (`ranking_reason` in the listing file). Read `references/fair-housing.md` before writing the recommendation, risk flags or questions for the buyer's agent. If the agent asks for wording that breaks this, write the compliant version and say why in one sentence; don't lecture or flag innocent wording like "family room".
- **People by name, never by pronoun.** In chat, call the parties "the buyer", "the seller" or by their names; never guess a pronoun from a name. Offers are named by the buyer's agent and brokerage (Offer Names in `references/listing-file.md`), never by the buyer or the letter.
- **No em dashes in prose,** chat included: use a comma, colon, parentheses or a new sentence. A lone em dash for an empty value is fine.
- **Labels in Title Case:** headings, column headers, row names, tiles, legend entries, card and slide titles. Sentences, notes and table values stay sentence case.
- **Private financial details.** Pre-approval letters, proof of funds and bank statements carry account and loan numbers and sometimes Social Security numbers: never copy those into the data file, the chat or a report ("Account ending 1234" at most). Keep only the amounts and the lender's name. The listing file holds the seller's payoff: the review is for the seller, never for a buyer's agent.
- **Contract support.** Only Florida FR/BAR contracts (AS IS and Standard, with their CR-7 riders and addenda) are fully supported. For any other contract the script output has `support: "best_effort"` and the line to use in `chat_notes`: say it once in chat, in your own short words. The same goes for a note that an FR/BAR contract isn't the revision the rules were checked against. Never put either in a PDF or markdown report.
- **`render.py` checks the data file first** and stops on an em dash in a sentence or a clear fair-housing red flag, naming each field. Rewrite the field; don't work around the check. It can't see chat replies, so the rules above still apply there.

## Never Block on Missing Data

The engine fills anything missing with a conservative default and records it as an assumption with an impact level. High-impact gaps (CMA range, payoff, concessions, financing, contract form) mark the answer **Preliminary**. Local costs and commission are never gaps: they have labeled defaults (`references/local-costs.md`). Build the answer with what you have, then ask for the two to four inputs that would change it most, never a questionnaire first.

**Minimum to run:** list price, offer price and financing type. If one is missing, ask for just that.

## 1. Build the Listing File

One JSON file per property, in a temporary folder, never the outputs folder (`references/saved-files.md`, Working Files); the fields are in `references/listing-file.md`. It's a working file: never hand it to the agent or offer it for download. A new offer or counter later in the conversation goes into the same file (Offers Over Time in `references/listing-file.md`). In a new conversation, rebuild it from the documents the agent uploads again, plus the numbers from the earlier report the agent gives (payoff, CMA range, commission). Record `buyer_agent` and `buyer_brokerage` from the contract ("Morales · Palmetto Coast Realty"); when the agent says "Offer B", match it to the id.

- **Contract or offer uploaded:** read all of it, riders and counteroffers included (`pdftotext -layout`, or read scanned pages directly); `references/contract-fields.md` says where each field lives. FR/BAR: `references/frbar-riders.md`, `references/frbar-addenda.md` and `references/frbar-contract.md`; any other contract: `references/other-contracts.md`. Check it's complete with `references/contract-check.md` (and `references/frbar-package-check.md`) and record what the engine doesn't raise in `contract_issues`. No seller-paid costs in it: `seller_concessions: 0`. A counteroffer chain: the terms that would govern if signed, and the seller's earlier counters in `prior_counters`. A condo: also `references/condo.md`.
- **Pre-approval letter or proof of funds:** `approval`, `lender`, and the letter's caps in `approval_max_price` / `approval_max_loan`.
- **Offer described in chat:** take what's given.
- **Another state's paid or free termination period** (a Texas option period, a due-diligence or attorney-review period): record it as `inspection_days`, leave `inspection_walkaway` out unless the agent confirmed the contract lets the buyer cancel for any reason in it (the engine then records a high-impact assumption that it does), and put any option or due-diligence fee in `other_terms`. Say in chat that the period was treated as a walk-away window.

Record only what the documents or the agent say: the engine's default is labeled, a guess isn't. Buyer letters, photos and personal details never go in the file or the report.

**Value range:** a seller CMA's `.cma.json` from earlier in this conversation goes in with `--cma`; any other CMA's low and high, confirmed with the agent in one line, go in `listing.cma_low` / `cma_high`; with none, appraisal risk is measured against list price and the answer is Preliminary. **Market costs:** the engine takes them from the listing's state and county (`references/local-costs.md`, `references/seller-costs.md`); with no state anywhere, an FR/BAR contract means Florida (labeled Assumed), anything else national estimates; outside Florida, look up the state's transfer tax and put it in `listing.costs`. Details for both are in Value Range and Costs in `references/listing-file.md`.

## 2. Run and Review

```
python3 scripts/review.py listing.json [--cma file.cma.json] [--mode single|multi] [--offer ID]
```

It prints every value already formatted: the page-1 summary, each offer's net sheet, and the assumptions ranked by impact. Read it critically before answering; the rules are a first draft and the agent's judgment wins.

- **Scores** follow `references/scoring-rubric.md`. When the agent knows something the contract can't show (the lender call went badly), set `scores.<criterion>` with a `why`.
- **Counters** follow `references/counter-rules.md`. Check the counter is realistic for this buyer: with a CMA, a price above the value range is countered back to its top; without one the price stands and the counter asks for gap coverage; FHA and VA buyers are never asked for gap coverage. The counter never changes a term nobody gave (an assumed inspection period): ask the agent to confirm it instead. When a buyer's counter changed a term the seller never answered, or left the loan amount and balance to close at an earlier price, the counter has a row for it; keep those rows.
- **Overrides:** `counter`, `recommendation` or `status` in the offer when the agent decides differently. Never change a number to make the recommendation look better.

## 3. Deliver

Pick the reply by what the agent asked for; every number comes from the output. Caps are for the prose; tables, and the one line each Blocking or High issue takes, don't count toward them.

| Asked For | The Reply Contains | Cap |
|---|---|---|
| **Quick question** ("should we take it?", "what should my seller do?") | `summary.title` and the net with certainty; each Blocking or High issue with its fix, one line each (never a plain "yes" past one); when countering, the changed terms in one line; with 2+ offers, the plan in one line per offer; every line of `estimated_costs` in one short "Estimated:" line; the top missing inputs as one question; the PDF offered in one line | about 200 words, no tables. A lapsed offer (`summary.revive`) adds its reference counter table and the net as written, labeled reference only |
| **Quick net sheet** ("net sheet please", "what would my seller net?") | the offer's net sheet table from `offers[].net_sheet` (drop the Downside column when `downside_counts` is empty), the net with payoff status, one line with the recommendation and counter, `estimated_costs` in one line with what replaces them (a title quote, the tax bill), the PDF offered in one line | one table plus about 150 words |
| **Comparison question** (Rider K vs. a plain Standard offer, AS IS vs. Standard, cash vs. financed) | the quick-question lines, then the comparison below | about 350 words |
| **Re-rank request** ("rank B first", "the seller likes B") | the ranking the terms support, one sentence on why, and the terms reason in `ranking_reason`; a new PDF when the ranking or the plan changed | about 150 words |
| **Full review in chat** | `assets/offer-review-template.md`, filled in | the template |
| **A report for the seller** | the PDF below, then the chat lines under it | about 120 words |

**Top risks** come from `summary.risks` and `offers[].biggest_risk`, deal risks first (a passed deadline, sale contingency, financing, appraisal gap). The seller's flood disclosure is a listing-side reminder: it's last in the flags and on the checklist, never the biggest risk; in chat, mention it in a clause at most.

**A report for the seller:**

```
python3 scripts/render.py listing.json [--cma file.cma.json] [--mode single|multi] [--offer ID] [--packet] [--profile profile.md]
```

`--profile` puts the agent's name and colors on it (`references/saved-files.md`). The PDF goes to the outputs folder; if it can't render, give the markdown review. `--packet` (every offer's report): the comparison plus a single review of each active offer.

With the PDF, the chat says: the recommendation with the net and certainty; the counter or the plan per offer; then the top missing inputs as one line. Offer the other format in one line.

**Rider K questions** ("how does Rider K compare to a normal Standard offer?"): run the offer as written only; there's no second listing file for a plain Standard version. Explain the difference from Rider K on the Standard Form in `references/scoring-rubric.md`: it firms the deal sooner than the Standard repair windows, the seller owes no repairs (so the downside has the inspection credit, not the General Repair Limit), why the scores may match, and its red flags. Quote only numbers from the output; describe the plain Standard side in words.

**Time for acceptance passed:** the review is CONTRACT INCOMPLETE and shows, as reference, what a seller counter with a new time for acceptance could look like (`summary.revive`). State the fact (the offer's own deadline has passed), never whether it can still be accepted, and never a send-by date in the past. The quick answer still gives the net as written and the certainty, labeled reference only. Only likely passed (delivery date unknown): ask when it was delivered.

**Year built:** when `to_confirm` asks for it (riders were read from an FR/BAR package and the year is missing), ask for it in the missing-inputs question: a home built before 1978 needs the lead-based paint disclosure (Rider P) before accepting.

**Terms reason:** when the seller saw a buyer letter, or wants an offer the ranking doesn't put first, write the terms reason for the pick in the listing file's `ranking_reason` (price, terms, financing, timing; never the buyer). It prints on the report as Terms Reason.

## Rules That Protect the Seller and the Agent

- **One counter out at a time** with multiple offers: countering several buyers at once can produce two accepted contracts.
- **Present every offer.** The skill ranks offers; it never hides one. Only the seller drops an offer.
- **No recommendation on an incomplete contract.** A Blocking issue (unsigned, pages missing, price blank) labels the review CONTRACT INCOMPLETE with no accept, counter or decline, and the offer isn't ranked. Say what to fix; never say whether the contract is binding.
- **Not legal advice.** For unusual clauses, recommend a real estate attorney licensed in the property's state rather than interpreting them.
