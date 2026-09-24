# Buyer File

One JSON file per property the buyer is pursuing. Only `property.list_price` is required; `buyer.cash_available` is strongly preferred. Everything else has a logged default (impact **high** marks the answer Preliminary).

```json
{
  "analysis_date": "2026-09-23",
  "property": {"address": "1532 Cypress Bend Dr, Casselberry, FL 32707", "list_price": 365000, "dom": 9},
  "competition": {"level": 2, "note": "Listing agent: 2 other offers expected", "deadline": "Fri Sep 25 · 5 PM"},
  "buyer": {"financing": "fha", "down_pct": 0.035, "max_price": 375000, "cash_available": 26000, "max_payment": 3200}
}
```

Fastest start: `--cma file.cma.json` (a buyer CMA's `cma-handoff v1`), or the handoff pasted into the file as `"cma": {...}`. It fills `property` facts, `value` (low, high, midpoint, median adjusted) and `market` stats, only where the file doesn't already say.

## property

`address`, `state`, `county` (state read from the address; neither → Florida assumed, flagged high), `list_price` (required), `dom`, `price_cuts`, `beds`, `baths`, `sqft`, `year_built`, `roof_year`, `hoa_monthly`, `flood_zone`, `annual_tax` (seller's bill, for the seller net sheet), `seller_deadline` (if the listing agent shared one), `type` (`condo`: the engine adds the condo rider, FHA/VA project approval and rescission checks; see `condo.md`), `cdd` (true when in a CDD or special district) and `cdd_annual` (the yearly assessment from the tax bill; added to the payment, flagged when missing), `short_sale`, `costs` (deal cost overrides, same keys as the listing side: `title_fees`, `transfer_tax_rate`, `title_payer`…).

## value

| Field | Default | Impact |
|---|---|---|
| `cma_low`, `cma_high` | list price for both | **high** |
| `midpoint` | average of low and high | — |
| `median_adjusted` | midpoint; used as the price anchor when there's little competition | — |
| `source` | — | label only |

## market

`sale_to_list` (0–1), `months_supply`, `median_dom`, `share_with_seller_costs`, `typical_seller_paid`: the market read and page-1 context.

## competition

| Field | Meaning | Default |
|---|---|---|
| `level` | 0 only offer · 1 one competing · 2 two–three · 3 cash or 4+ | inferred from market heat (hot → 2, normal → 1, soft → 0), flagged |
| `note` | what the listing agent said | — |
| `deadline` | offers due | — |
| `backup` | seller already has an accepted contract | — |

Heat: hot if DOM is under half the median or sale-to-list is 99%+; soft if DOM is over 1.5× the median or the price was cut.

## listing_side

`buyer_broker_offered_pct` (what the seller offers; unknown → the buyer-broker agreement %, else the agent's standard terms from their market profile, else none, flagged; nothing is built in), `listing_fee_pct` (for the seller net sheet; unknown → the agent's standard terms from their market profile, else left out and flagged; nothing is built in).

## costs (Buyer's Payment)

`rate` (interest rate as a **percent**: `6.5` for 6.5%, like lenders quote it; default 6.5), `tax_rate` (optional: annual tax as a share of price, `0.0198`, when you have a plain rate rather than millage), `insurance_annual` (default: the market's buyer insurance rate × price, at least $2,500; Florida 0.9%, else a national 0.9% estimate), `total_mills`, `school_mills`, `homestead` (tax with the market's homestead exemptions; without millage, the market's fallback rate; neither → payment leaves tax out, flagged), `flood_insurance_annual` (a quote; without one the payment leaves flood out, labeled "Before Flood Insurance", and the assumptions say whether a lender or Citizens requires it: never 0).

## buyer

| Field | Default if Missing | Impact |
|---|---|---|
| `financing` | conventional, flagged to confirm; FHA/VA/USDA only when given | **high** |
| `down_pct` | conventional: 20% at the luxury threshold, 3% first-time buyer, else 5%; FHA 3.5%; VA/USDA 0% | med |
| `first_time_buyer` | false | — |
| `luxury_threshold` | $1,000,000 | — |
| `max_price` | higher of list and CMA high | **high** |
| `cash_available` | down payment + 4% of list | **high** |
| `reserve_floor` | $2,000 | med |
| `max_payment` | none | — |
| `closing_cost_pct` | market buyer closing costs + 0.5% prepaids (Florida 3.5%); cash: half the market figure; no market: 3.5% / 1.5% | low |
| `approval` | `preapproval` (`pof_verified` for cash). Values: `none`, `prequal`, `preapproval`, `full_uw` (DU/LP or underwriter approval), `pof_verified` (cash) | — |
| `lender_called` | false. True only when the agent says they talked to the lender: it prints "lender confirmed" on the worksheet | — |
| `insurance_quote` | false. True when the buyer already has a quote for this address; only a quote in hand is scored (a planned one is a to-do) | — |
| `va_later_use`, `va_exempt` | VA only: a later use of the benefit (higher funding fee under 5% down), or exempt from the fee | false |
| `lender_min_close_days` | 35 financed / 21 cash | — |
| `agent_track` | `average`: how a listing agent would rate the buyer's agent | — |
| `buyer_broker_agreement_pct` | none (flagged): the rate in the buyer's own broker agreement. When the seller pays less, the difference is a "Buyer's Broker Fee (Not Paid by Seller)" line in cash to close and counts in every limit | med |
| `needs_sale` | false (adds the sale-of-buyer's-property rider) | — |
| `checklist` | package checklist statuses: `contract` `riders` `terms` `pre_approval` `funds` `insurance` `agency` `bb` `wire` `lead` `inspector` `lender_close` | Pending |

## overrides

The agent's call on any recommended term: `price`, `seller_concessions`, `deposit`, `inspection_days`, `loan_approval_days`, `appraisal_gap`, `closing_days`, `home_warranty`, `buyer_broker_pct`, `escalation`. Marked "Agent" in the report; the stronger and lower-cost options are built from the overridden offer.

## chosen_option

`recommended` (default), `stronger` or `lower_cost`: drives the worksheet.

## worksheet

`buyer_names`, `escrow_agent`, `title_agent`, `legal_description`, `parcel_id`, `hoa_name`, `personal_property`, `acceptance_deadline`, `contract_form` (`as_is` / `standard`, Florida; the options are scored on this same form, AS IS when blank and flagged), `repair_limits` (Standard only), `contract_name` (the form's name outside Florida; a TREC form, or a Texas property with no name, gets the TREC rows and riders), `option_fee` (TREC). Missing names print as red blanks.
