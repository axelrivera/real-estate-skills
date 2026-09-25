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
  "offers": [{"id": "A", "buyer_agent": "J. Morales", "buyer_brokerage": "Keller Williams",
              "price": 432000, "financing": "fha", "down_pct": 0.035, "seller_concessions": 12000}]
}
```

## Contents

- Top Level
- listing (and its costs)
- seller
- offers[] (Offer Names, Agent Overrides)

## Top Level

| Field | Default |
|---|---|
| `analysis_date` | today (also the assumed acceptance date for timelines) |
| `listing`, `offers` | required |
| `seller` | `{}` |
| `cma` | optional: a `cma-handoff v1` record pasted in, instead of passing `--cma` |
| `sample` | `true` only for demo data (prints SAMPLE DATA) |

The agent's name, brokerage and brand colors come from the agent's profile (`--profile`), not from this file.

## listing

| Field | Default if Missing | Impact |
|---|---|---|
| `address` | — | — |
| `state`, `county` | state read from the address ("…, FL 32750"); neither → Florida assumed | high |
| `list_price` | **required** | — |
| `beds`, `baths`, `sqft`, `year_built` | shown as "—" | — |
| `roof_year` | no roof penalty in scoring | med (insurance) |
| `hoa_monthly` | unknown → HOA estoppel still charged; `0` = no HOA | low |
| `hoa_approval_required` | false | low |
| `flood_zone` | not scored | low |
| `cma_low`, `cma_high` (`cma_mid` optional) | from `--cma`; else both = list price, appraisal risk measured vs. list | **high** |
| `annual_tax` | market fallback rate × list price (Florida 1.8%); no rate → proration left out | low / med |
| `costs` | market values; see below | — |

### costs (This Deal's Own Numbers, Optional)

Use when the agent has a title company quote, you looked up the state's transfer tax, or the county differs from the market default. Each one wins over the built-in values and estimates.

| Field | Meaning |
|---|---|
| `title_fees` | seller's title company charges: a number (a quote) or `{"settlement_fee": 700, ...}` |
| `transfer_tax_rate`, `transfer_tax_payer` | deed transfer tax as a share of price; `seller`, `buyer` or `split` |
| `title_payer` | who customarily pays the owner's title policy: `seller` or `buyer` |
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
| `listing.property_type` | `single_family`, `condo`, `townhouse`, `multifamily`, `land`. `condo` adds the condo rider, FHA/VA project approval and rescission checks (`condo.md`) | none: Miami-Dade's surtax is left out and flagged | med in Miami-Dade |
| `listing.flood_disclosure` | true once the seller's flood disclosure (Florida: s. 689.302) has been given to the buyer | not given: flagged for the listing side where the market requires it | — |
| `listing.current_tax_bill_paid` | `true` once the seller paid this year's bill | false; asked for Nov and Dec closings | med |
| `listing_fee_pct` | 2.5% assumed (5% total with the buyer's agent) | med |
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
| `expires` | `YYYY-MM-DD HH:MM`: when the offer lapses (the respond-by time) | — | — |
| `received` | `YYYY-MM-DD HH:MM`, for the record (not scored) | — | — |
| `buyer` | name(s) on the contract; shown once, as contract identification | not shown | — |
| `buyer_agent`, `buyer_brokerage` | the buyer's agent and their brokerage, as on the contract | name falls back to price and financing | — |
| `lender` | text | — | — |
| `price` | number | **required** | — |
| `financing` | `cash` `conventional` `fha` `va` `usda` | conventional | high |
| `down_pct` | 0–1 | FHA .035, VA/USDA 0, conventional .10 | med |
| `approval` | `pof_verified` `full_uw` `du_approved` `preapproval` `prequal` `none` | preapproval (financed) | med |
| `lender_called` | bool | false → approval score capped at 3 | — |
| `deposit` | total escrow $ | unknown → scored 3 | med |
| `seller_concessions` | $ | 0 | **high** |
| `buyer_broker_pct` or `buyer_broker_amount` | | seller's offered %, else 2.5% assumed | **high** when the seller offered, med when assumed |
| `home_warranty` | $ seller pays | 0 | — |
| `contract_form` | `as_is` `standard` (FR/BAR), or the form's name for any other contract | Florida: `as_is`, flagged as an assumption; elsewhere `other` | **high** in Florida |
| `repair_limits` | Standard only: `{general, wdo, permit}` in dollars or as a share of price | 1.5% each (Para. 9(a)) | — |
| `inspection_walkaway` | Other contracts only: `false` when the buyer can cancel just for listed defects | `true` (an option or due-diligence period) | — |
| `inspection_days` | days | 10 | med |
| `loan_approval_days` | days | 30 (financed) | low |
| `appraisal_contingency` | days, `true` or `false` | 21 days if financed | med |
| `appraisal_gap` | $ the buyer covers (FHA/VA: recorded, credited 0) | 0 | — |
| `gap_funds` | financed waiver only: $ documented beyond down payment and closing costs | 0 when waived | med |
| `sale_contingency_days`, `kickout` | days, bool | 0, false | — |
| `closing_date` or `closing_days` | date, or days from `analysis_date` | 45 financed / 30 cash | med |
| `title_by` | `seller` / `buyer` | the local custom | — |
| `riders` | list of names, as attached | none; rider checks run only when listed | — |
| `loan_amount` | $ from the financing paragraph | none; checked against the down payment when given | — |
| `escalation` | `{cap, increment, proof}`; the offer is scored at the price it reaches against the other offers | none | — |
| `personal_property`, `occupancy`, `other_terms` | text | — | — |
| `insurance_quote` | bool | unknown | — |
| `agent_track` | `strong` `average` `weak` | scored 3 | — |
| `agent_note` | text for the scorecard | — | — |

### Offer Names

Reports name each offer the way listing agents talk about it, by the buyer's side: the agent's surname and brokerage, "Morales · Keller Williams" (in sentences, "the Morales (Keller Williams) offer"). Without an agent or brokerage, price and financing: "$432K FHA". Two offers that would share a name get the price and financing added. Never name an offer by the buyer (fair housing); the buyer's name appears only in the Buyer / Agent row of the terms table. If the agent asks for a different name, set `label` (a short name, without the word "offer").

A single-offer review carries the name too (under the headline and in the PDF filename, "8104-Shoal-Creek-Blvd-Whitfield-Compass-Offer-Review.pdf"), so reviews of different offers on one listing never share a file name. The `id` letter never shows in a single-offer review. In a comparison it appears only where space is tight (chart points, contingency timeline, risk flags), always with a key.

### Agent Overrides (per Offer)

- `scores`: `{"appraisal": {"score": 2, "why": "Appraisers here run low"}, "agent": 5}`. Keys: `financing` `approval` `appraisal` `contingency` `deposit` `timeline` `property` `agent`. Marked "Agent" in the report.
- `counter`: any computed term (`price`, `seller_concessions`, `appraisal_gap`, `deposit`, `inspection_days`, `home_warranty`, `buyer_broker_pct`, `closing_date`), or the whole table as `rows: [[term, offered, counter, why], …]`. The counter net and certainty recompute from the terms, so keep rows and terms consistent.
- `recommendation`: `ACCEPT` / `COUNTER` / `BACKUP` / `DECLINE`.
- `checklist`: `{"signed": "Yes", "deposit": {"status": "Yes", "note": "Wire confirmed 9/24"}}`. Keys: `signed` `lender` `deposit` `riders` `insurance` `bb` `net`. Values `Yes` `No` `Pending` `N/A`.
- `flags`: extra flags `[{"sev": "High", "issue": "…", "fix": "…"}]`.
- `contract_issues`: what reading the contract found, per `contract-check.md`: `[{"sev": "Blocking", "issue": "…", "fix": "…", "request": "…", "check": "signed"}]`. `sev` is `Blocking` `High` `Med` `Low`. A **Blocking** issue takes the offer out of the recommendation and the ranking until it's fixed; remove it from the file once the corrected contract arrives. `request` goes to the buyer's agent questions (leave it out when the fix is on the listing side); `check` puts the issue on that checklist line (`signed`, `riders`, `terms`).
