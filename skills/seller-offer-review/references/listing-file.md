# Listing File

One JSON file per property, with every offer in it. `scripts/review.py` analyzes it and `scripts/render.py` builds the PDF. Only `listing.list_price` and, per offer, `price` and `financing` are needed. Anything else that's missing gets the default below and is recorded as an assumption:

- **high:** can change the recommendation or move the net by thousands (the answer is marked Preliminary)
- **med:** changes a score or a line item
- **low:** minor

```json
{
  "analysis_date": "2026-09-23",
  "listing": {"address": "418 Heron Lake Dr, Longwood, FL 32750", "list_price": 425000, "cma_low": 415000, "cma_high": 428000},
  "seller": {"name": "Pat Seller", "payoff": 238400, "listing_fee_pct": 0.03, "offered_buyer_broker_pct": 0.025},
  "offers": [{"id": "A", "buyer_agent": "J. Morales", "buyer_brokerage": "Palmetto Coast Realty",
              "price": 432000, "financing": "fha", "down_pct": 0.035, "seller_concessions": 12000}]
}
```

## Contents

- Top Level: dates, the CMA handoff, sample data
- listing: the home, the value range, taxes, HOA, flood, and `costs` (this deal's own numbers)
- seller: payoff, fees, deadline, priority
- offers[]: price and financing, approval and funds, deposit and concessions, the contract form and riders, periods and
  dates, the title box, negotiation history
- Offer Names
- Agent Overrides (per Offer)
- Value Range and Costs
- Offers Over Time

## Top Level

| Field | Default |
|---|---|
| `analysis_date` | today (also the assumed acceptance date for timelines) |
| `listing`, `offers` | required |
| `seller` | `{}` |
| `cma` | optional: a `cma-handoff v1` record pasted in, instead of passing `--cma`. Besides the value range it can carry the subject's `annual_tax`, `hoa_monthly`, `flood_zone` and `roof_year`, used where the listing doesn't say. A handoff for another address is flagged (high) |
| `ranking_reason` | optional: the terms reason for the pick, in one or two sentences (price, terms, financing, contingencies, timing; never the buyer), when the seller saw a buyer letter or picks an offer the ranking doesn't put first (`fair-housing.md`). Printed on the report as Terms Reason and in `summary.terms_reason` |
| `sample` | `true` only for demo data (prints SAMPLE DATA) |

The agent's name, brokerage and brand colors come from the agent's profile (`--profile`), not from this file.

## listing

| Field | Default if Missing | Impact |
|---|---|---|
| `address` | — | — |
| `state`, `county` | state read from the address ("…, FL 32750"). Neither: an offer on an FR/BAR contract means Florida (its costs, labeled Assumed); otherwise national estimates, never Florida's. Either way it's listed as an assumption | high |
| `list_price` | **required** | — |
| `beds`, `baths`, `sqft`, `year_built` | shown as "—". Without `year_built` the lead-based paint check can't run; when riders were read from an FR/BAR package it's asked for (med). Take it from the tax record or MLS | — |
| `built_before_1978` | `true` or `false` from the seller's property disclosure ("Was the Property built before 1978?") when the year isn't known: it runs the lead-based paint check, so the year isn't asked | asked with `year_built` | — |
| `roof_year` | no roof penalty in scoring | med (insurance) |
| `hoa_monthly` | unknown → HOA estoppel still charged, listed as an assumption; `0` = no HOA | low |
| `hoa_approval_required` | false | low |
| `flood_zone` | not scored | low |
| `cma_low`, `cma_high` (`cma_mid` optional: the CMA's midpoint or median adjusted comp price) | from `--cma`; else both = list price, appraisal risk measured vs. list. A range given here (not by `--cma`) comes back as `value_range_confirm`, the one line the reply uses to confirm it | **high** |
| `annual_tax` | market fallback rate × list price (Florida 1.8%); no rate → proration left out | low / med |
| `current_tax_bill_paid` | `true` once the seller paid this year's bill; else false, and asked for Nov and Dec closings | med |
| `property_type` | `single_family`, `condo`, `townhouse`, `multifamily`, `land`. `condo` adds the condo rider, FHA/VA project approval and rescission checks (`condo.md`). Missing: Miami-Dade's surtax is left out and flagged | med in Miami-Dade |
| `flood_disclosure` | `true` once the seller's flood disclosure (Florida: s. 689.302) has been given to the buyer; else flagged for the listing side where the market requires it | — |
| `costs` | market values; see below | — |

### costs (This Deal's Own Numbers, Optional)

Use when the agent has a title company quote, you looked up the state's transfer tax, or the county differs from the market default. Each one wins over the built-in values and estimates.

| Field | Meaning |
|---|---|
| `title_fees` | seller's title company charges: a number (a quote) or `{"settlement_fee": 700, ...}` |
| `transfer_tax_rate`, `transfer_tax_payer` | deed transfer tax as a share of price; `seller`, `buyer` or `split` |
| `title_payer` | who customarily pays the owner's title policy: `seller` or `buyer`. It also wins over an offer's FR/BAR `title_by`, so set it only when the agent says so |
| `title_estimate_pct` | owner's title premium as a share of price, when there's no rate table |
| `hoa_estoppel_fee` | HOA / condo estoppel letter |
| `tax_paid` | `arrears` (seller credits the buyer from Jan 1) or `advance` |
| `insurance_rate`, `utilities_monthly` | for the holding-cost estimate |
| `inspection_credit_reserve_pct` | typical post-inspection credit, for the downside case |

## seller

| Field | Default if Missing | Impact |
|---|---|---|
| `name` | "Seller" | — |
| `payoff` | 0; nets labeled **before payoff** | **high** |
| `listing_fee_pct` | 2.5% assumed for the listing side (default commission, 5% total); when the listing broker pays the buyer's broker, 5% in total on one line | med |
| `offered_buyer_broker_pct` | none: no flag for high buyer-broker asks; offers that don't say assume 2.5% | med |
| `holding_monthly` | tax/12 + insurance + HOA + utilities + 4.5% interest on payoff (market rates) | low |
| `deadline` | none; timeline scored on speed | med |
| `priority` | `balanced`; or `price`, `certainty`, `speed` (changes the ranking penalty) | med |
| `priority_note` | shown instead of the priority word | — |

## offers[]

| Field | Values | Default if Missing | Impact |
|---|---|---|---|
| `id` | "A", "B", …: an internal key, next letter for each new offer | "A" | — |
| `label` | the offer's name in the report, when the agent wants something other than the default (see Offer Names) | agent and brokerage | — |
| `status` | `active` `backup` `declined` `expired` `accepted` | `active` | — |
| `expires` | `YYYY-MM-DD HH:MM`: when the offer lapses (the time for acceptance). Before `analysis_date`: a Blocking issue (lapsed). When the form gives a date but no time (a CO-3 counter's "2 days after delivery"), give the date alone: it's read as the end of that day and listed as an assumption. Never invent a time | — | med when the time is missing |
| `expires_estimated` | `true` when `expires` is counted from the signature date because the delivery date isn't known (a counter "2 days after delivery"): a passed date is then a High issue and a question, not Blocking | false | — |
| `prior_counters` | earlier counters on this offer, oldest first: `[{"by": "seller", "price": 629000, "inspection_days": 10, "note": "Counter 1"}, {"by": "buyer", ...}]`. Terms: `price`, `inspection_days`, `loan_approval_days`, `deposit`, `seller_concessions`, `appraisal_gap`, `closing_date`. The engine never counters above the seller's last price or asks for weaker terms than the seller's last counter, and raises a High issue for terms of that counter the live offer doesn't carry. When a buyer's counter is live, put the original offer first as `{"by": "buyer", "note": "Original offer", ...}` with the terms the buyer's counter changed: a change no seller counter addressed (a later closing date) is raised as a Med issue | none | — |
| `received` | `YYYY-MM-DD HH:MM`, for the record (not scored) | — | — |
| `buyer` | name(s) on the contract; shown once, as contract identification | not shown | — |
| `buyer_agent`, `buyer_brokerage` | the buyer's agent and their brokerage, as on the contract | name falls back to price and financing | — |
| `lender` | text | — | — |
| `price` | number | **required** | — |
| `financing` | `cash` `conventional` `fha` `va` `usda` | conventional | high |
| `down_pct` | 0–1 | from `loan_amount` and `price` when both are given; else FHA .035, VA/USDA 0, conventional .10 | med |
| `approval` | `pof_verified` `full_uw` `du_approved` `preapproval` `prequal` `none` | preapproval (financed) | med |
| `approval_expires` | the expiration date on the pre-approval letter (`YYYY-MM-DD`). Before closing: a Med issue. Text that isn't a date ("30 days from issue") is recorded as an assumption, not checked | none | low |
| `proof_of_funds` | $ the buyer's proof of funds verifies (bank letter or statement). Below the down payment plus any appraisal gap the buyer covers, it's a High issue | none | — |
| `approval_max_price`, `approval_max_loan` | the caps printed on the pre-approval letter. A price (or loan) above them is a High issue, and a counter above the price cap asks for an updated letter | none | — |
| `lender_called` | bool | false → approval score capped at 3 | — |
| `deposit` | total escrow $ | unknown → scored 3, and always in `to_confirm` | med |
| `seller_concessions` | $; `0` when the contract or offer you read has no seller-paid closing costs or concessions | 0 | **high** |
| `buyer_broker_pct` or `buyer_broker_amount` | | seller's offered %, else 2.5% assumed | **high** when the seller offered, med when assumed |
| `home_warranty` | $ seller pays | 0 | — |
| `contract_form` | `as_is` `standard` (FR/BAR), or the form's name for any other contract | Florida: `as_is`, flagged as an assumption; elsewhere `other` | **high** in Florida |
| `form_revision`, `form_revision_source` | FR/BAR revision as printed ("FloridaRealtors/FloridaBar-ASIS-7x Rev. 2/26"). `form_revision_source`: `"footer"` when you read it from the form's footer; leave it out when it came from anywhere else, and record the revision as given | none; a revision other than the verified one adds a chat note, quoting "the footer reads" only for `"footer"` | — |
| `repair_limits` | Standard only (alone or with Rider L): `{general, wdo, permit}` in dollars or as a share of price | 1.5% each (Para. 9(a)) | — |
| `inspection_walkaway` | Other contracts only: `true` when the buyer may cancel for any reason in the period, `false` for a repair or objection process only. A paid or free termination period (a Texas option period, a due-diligence period) goes in `inspection_days`; set this only when the agent confirmed the contract's terms, else leave it out so the assumption is recorded. Its fee goes in `other_terms` | assumed `true` and flagged | **high** |
| `inspection_days` | days | FR/BAR: 15 (Para. 12(a), and Riders K and L, when blank); any other contract: 10. An assumed period is never countered and is always in `to_confirm` | med |
| `loan_approval_days` | days | 30 (financed) | low |
| `appraisal_contingency` | days to the end of the buyer's appraisal notice, `true` or `false`. Rider F: the rider's date plus 3 days. FR/BAR with no Rider F, E or AGA-1: leave it out (Para. 8(b) makes the appraisal part of Loan Approval) | Rider F attached: its default (10 days before closing, plus 3); FR/BAR financed with no appraisal rider: the loan approval period, no assumption; otherwise 21 days if financed | med |
| `appraisal_gap` | $ the buyer covers (FHA/VA: recorded, credited 0) | 0 | — |
| `appraisal_form` | FR/BAR: `aga` when the gap is on the Appraisal Gap Addendum (AGA-1); also read from its name in `riders` or `addenda`. The window becomes AGA-1's (valuation + 3 days + renegotiation), and a cash offer carries appraisal risk | Rider F by letter; else the terms above | — |
| `aga_valuation_days`, `aga_renegotiate_days` | AGA-1 blanks | 30, 3 | — |
| `gap_funds` | financed waiver only: $ documented beyond down payment and closing costs | 0 when waived | med |
| `sale_contingency_days`, `kickout` | days, bool; Rider X in `riders` sets `kickout` | 0, false | — |
| `buyer_broker_paid_by` | `listing_broker` when the listing broker pays the buyer's broker from its own fee (Rider GG signed by the Seller's Broker, or the listing agreement says so): no buyer-broker line in the seller's net (the Seller's Target too), no buyer-broker row in the Terms Review, and an assumed listing fee becomes the market's total (5%) on one line. Listed as an assumption for the agent to confirm. Set `seller.listing_fee_pct` to the total fee in the listing agreement | `seller` | med |
| `buyer_broker_form` | FR/BAR: `FF` when the buyer's broker is paid as a seller credit (Rider FF, also read from `riders`), which counts toward the loan program's concession limit; `GG` or blank for a separate compensation agreement | GG | — |
| `insurance_days`, `mold_days`, `drywall_days`, `rezoning_days`, `attorney_days` (Rider Z: to the buyer's attorney-approval date, a walk-away until then) | days from the Effective Date for a rider's cancel window when the rider's date or days are filled in (`frbar-riders.md`) | each rider's default; Z and R have none and are flagged | — |
| `closing_date` or `closing_days` | date, or days from `analysis_date` | 45 financed / 30 cash | med |
| `title_by` | the Para. 9(c) box, who designates the closing agent: `seller` (i), `buyer` (ii), `buyer_regional` (iii, the Miami-Dade/Broward regional provision; the seller still pays the title search up to `title_search_cap`, $200 if blank, and the lien search). The box also decides which title searches are in the seller's net (`seller-costs.md`). Missing: local custom, listed as an assumption. FR/BAR Para. 9(c): that party also pays the owner's policy ((i) `seller`; (ii) and (iii) `buyer`), so the net follows the contract unless `listing.costs.title_payer` is set | the local custom | — |
| `addenda` | names of the attached addenda, as printed ("Appraisal Gap Addendum (AGA-1)", "Counter Offer (CO-3)"): the AGA-1 name sets `appraisal_form: aga` | none | — |
| `riders` | CR-7 letters or names, the whole list as the contract's rider checkboxes show it ("K", "FHA/VA Financing"); `[]` when none is checked. Leave it out when you haven't seen the rider list (an offer summary). Rider K or L on the Standard form changes the inspection terms; I, K, L on AS IS stop the review (RESERVED) | none. Rider checks run only when listed. On an HOA or condo property, an FR/BAR offer whose list wasn't read (left out, or only Rider U, which a rent-back already implies) gets an assumption asking about the HOA or condo rider; a read list without it is a High issue | med |
| `rent_back_days`, `rent_back_monthly` | Rider U: days the seller stays after closing and the monthly rent the seller pays. On FR/BAR a rent-back is Rider U, so its agreement window counts whether or not "U" is in `riders` | not in the net; flagged when Rider U is attached. `0` rent is a free rent-back, in the net at $0 | med |
| `drywall_waived` | Rider M: `true` when the buyer waived the drywall inspection, so its cancel window isn't counted | false | — |
| `seller_financing` | Rider C: the note amount the seller carries (paid over time, not cash at closing) | 0 | — |
| `assessment_payoff` | Rider EE or the CDD addendum: an assessment balance the seller agrees to pay at closing | 0; flagged when Rider EE is attached | — |
| `loan_amount` | $ from the financing paragraph | none; checked against the down payment when given | — |
| `balance_to_close` | $ the balance due at closing (FR/BAR Para. 2(e)) of the live terms. With the deposit and loan amount it must add up to the price; a counter that changed the price without restating them is raised (`loan_amount`) | none; not checked | — |
| `escalation` | `{cap, increment, proof}`; the offer is scored at the price it reaches against the other offers | none | — |
| `personal_property`, `occupancy`, `other_terms` | text | — | — |
| `insurance_quote` | `true` (a quote in hand, scored), `false` (none yet), or `"planned"` (the buyer's agent says one is coming: noted, not scored until it's in hand) | unknown | — |
| `agent_track` | `strong` `average` `weak` | scored 3 | — |
| `agent_note` | text for the scorecard | — | — |

### Offer Names

Reports name each offer the way listing agents talk about it, by the buyer's side: the agent's surname and brokerage, "Morales · Palmetto Coast Realty" (in sentences, "the Morales (Palmetto Coast Realty) offer"). Without an agent or brokerage, price and financing: "$432K FHA". Two offers that would share a name get the price and financing added. Never name an offer by the buyer (fair housing); the buyer's name appears only in the Buyer / Agent row of the terms table. If the agent asks for a different name, set `label` (a short name, without the word "offer").

A single-offer review carries the name too (under the headline and in the PDF filename, "8104-Shoal-Creek-Blvd-Whitfield-Lakeshore-Homes-Offer-Review.pdf"), so reviews of different offers on one listing never share a file name. The `id` letter never shows in a single-offer review. In a comparison it appears only where space is tight (chart points, contingency timeline, risk flags), always with a key.

### Agent Overrides (per Offer)

- `scores`: `{"appraisal": {"score": 2, "why": "Appraisers here run low"}, "agent": 5}`. Keys: `financing` `approval` `appraisal` `contingency` `deposit` `timeline` `property` `agent`. Marked "Agent" in the report.
- `counter`: any computed term (`price`, `seller_concessions`, `appraisal_gap`, `deposit`, `inspection_days`, `home_warranty`, `buyer_broker_pct`, `closing_date`), or the whole table as `rows: [[term, offered, counter, why], …]`. The counter net and certainty recompute from the terms, so keep rows and terms consistent.
- `recommendation`: `ACCEPT` / `COUNTER` / `BACKUP` / `DECLINE`.
- `checklist`: `{"signed": "Yes", "deposit": {"status": "Yes", "note": "Wire confirmed 9/24"}}`. Keys: `signed` `lender` `deposit` `riders` `insurance` `bb` `net`, and `flood` (the seller's flood disclosure, where the market requires one; `listing.flood_disclosure: true` ticks it). Values `Yes` `No` `Pending` `N/A`.
- `flags`: extra flags `[{"sev": "High", "issue": "…", "fix": "…"}]`.
- `contract_issues`: what reading the contract found, per `contract-check.md`: `[{"sev": "Blocking", "issue": "…", "fix": "…", "request": "…", "check": "signed", "topic": "expired"}]`. `topic` (optional) names the engine check the issue covers (`contract-check.md` lists them); the engine then drops its own flag for it and keeps yours at the higher of the two levels. Without `topic`, the issue's words are matched. `sev` is `Blocking` `High` `Med` `Low`. A **Blocking** issue takes the offer out of the recommendation and the ranking until it's fixed; remove it from the file once the corrected contract arrives. `request` goes to the buyer's agent questions (leave it out when the fix is on the listing side); `check` puts the issue on that checklist line (`signed`, `riders`, `terms`).

## Value Range and Costs

The value range sets where appraisal risk starts. Use the CMA, in this order:

1. A seller CMA's `.cma.json` from earlier in this conversation (`saved-files.md`): pass it with `--cma`. Its low, high and midpoint become the appraisal range, and its subject facts (tax bill, HOA dues, flood zone, roof year) fill what the listing doesn't say. A buyer-side CMA, or one for another address, is flagged high: confirm it before relying on it.
2. Any other CMA (the agent's own attached CMA, a PDF from an earlier conversation, another tool's report, notes, a pasted range): read the low and high, put them in `listing.cma_low` / `cma_high`, and confirm them in one line of the reply (`value_range_confirm`: "Using your CMA's $415,000–$428,000 range.") without waiting for an answer.
3. Nothing: leave them out. Appraisal risk is measured against list price, the answer is Preliminary, and a price over list is never countered down (the counter asks for gap coverage instead).

Market costs come from the listing's state and county (`local-costs.md`): Florida closing costs, title rates and tax proration are built in; elsewhere national estimates are labeled Estimate, never Florida's numbers. Outside Florida, look up the state's transfer tax from a trusted source and put it in `listing.costs`. Without terms, commission is 5% total. `seller-costs.md` explains each line and takes a title company quote.

## Offers Over Time

- **New offer:** append it (next letter as `id`); the mode switches to multi on its own.
- **Buyer counters back:** the buyer's counter becomes the offer's terms (only what would govern if signed), and the seller's counter goes in `prior_counters`, after the original offer's changed terms (`by: "buyer"`). The engine never counters above the seller's last price or asks for less than the seller's last terms, flags terms the buyer's counter dropped, and flags terms it changed that the seller never countered. Record the counter's loan amount and balance to close as the form now reads them.
- **Counter rejected, offer expired or withdrawn:** `status` `declined` / `expired`. It leaves the ranking but stays in the file.
- **A buyer agrees to back up:** `status: "backup"`. **Counter accepted:** `status: "accepted"`, and offer a contract timeline for the deadlines.
- **A later conversation:** the file doesn't carry over; rebuild it from the offers the agent uploads again.
