# Buyer File

One JSON file per property the buyer is pursuing. Only `property.list_price` is required; `buyer.cash_available` is strongly preferred. Everything else has a logged default (impact **high** marks the answer Preliminary).

```json
{
  "analysis_date": "2026-09-23",
  "property": {"address": "1532 Cypress Bend Dr, Casselberry, FL 32707", "list_price": 365000, "dom": 9},
  "competition": {"level": 2, "note": "Listing agent: 2 other offers expected", "deadline": "Fri Sep 25 · 5 PM"},
  "buyer": {"financing": "fha", "down_pct": 0.035, "max_price": 375000, "cash_available": 26000, "max_payment": 3200},
  "costs": {"rate": 6.4, "insurance_annual": 3400}
}
```

Fastest start: `--cma file.cma.json` (a buyer CMA's `cma-handoff v1`), or the handoff pasted into the file as `"cma": {...}`. It fills `property` facts (with the HOA dues, flood zone, roof year and the seller's tax bill when the CMA has them), `value` (low, high, midpoint, median adjusted), `market` stats and the tax the CMA computed for the buyer (`costs.total_mills`, `school_mills`, `homestead`), only where the file doesn't already say, so both reports show the same payment. A handoff for another address, or a seller-side one, is flagged high.

## Top Level

`costs` (the buyer's payment inputs, below) is a top-level block like `buyer`, not `property.costs`. `analysis_date` (default today; when the agent states today's date, use it and never question it against the computer's clock), `expected_effective_date` (`YYYY-MM-DD`: when the seller is expected to accept; closing, deposit and "days until firm" count from it, and the worksheet's Time for Acceptance defaults to it at 5:00 PM. Default: the day after the offer deadline in `worksheet.acceptance_deadline` or `competition.deadline`, else the day after `analysis_date`, moved to the next business day when that falls on a weekend or holiday (the same day as the default Time for Acceptance), listed as a low-impact assumption), `overrides`, `chosen_option`, `worksheet`, `cma`.

## property

`address`, `state`, `county` (state read from the address; neither → no built-in costs, flagged high. No county: taken from the city when a built-in tax district names it, flagged to confirm), `mls` (the MLS the listing is on; a CMA handoff's `market_profile.mls` fills it), `list_price` (required), `dom` (a CMA handoff's figure is moved forward by the days since its `as_of` date, noted in the assumptions), `price_cuts` (the number of cuts; a CMA handoff's figure fills it), `beds`, `baths`, `sqft`, `year_built`, `roof_year`, `hoa_monthly`, `hoa_frequency` (`monthly`, `quarterly`, `semiannual` or `annual`: how the association bills the dues, so Rider B shows the amount as billed, "$105 per quarter"; without it Rider B leaves the billed amount blank beside the monthly figure; a CMA handoff fills it), `flood_zone`, `annual_tax` (seller's bill, for the seller net sheet; without it the proration is an Estimate, labeled so on the net sheet: the buyer's millage or `tax_rate` applied to the list price, not the seller's actual bill, flagged), `seller_deadline` (if the listing agent shared one), `seller_flexible_close` (true when the listing agent or the listing's Realtor Remarks say the seller is flexible on the closing date: the `seller_timeline` reply line suggests asking which date helps the seller; chat only, never in the report), `type` (`condo`: the engine adds the condo rider, FHA/VA project approval and rescission checks; see `condo.md`), `cdd` (true when in a CDD or special district) and `cdd_annual` (the yearly assessment from the tax bill; added to the payment, flagged when missing), `short_sale`, `costs` (seller-side deal cost overrides, same keys as the listing side: `title_fees`, `transfer_tax_rate`, `title_payer`…; the buyer's rate, insurance and tax go in the top-level `costs`).

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
| `level` | 0 only offer · 1 one competing · 2 two–three · 3 cash or 4+ | inferred from market heat (hot → 2, normal → 1, soft or stale → 0), flagged |
| `note` | what the listing agent said | — |
| `deadline` | offers due ("2026-09-25 17:00" or "Fri Sep 25 · 5 PM"; the report prints both as "Fri Sep 25 · 5 PM"); the expected Effective Date is the day after. Enter a weekday alone as the agent said it ("Friday 5pm"): the script resolves it to the next one from `analysis_date` (today counts) and state that date in chat. When it lands more than 5 days out (today is the day after that weekday), the agent may have meant the one that just passed: the resolved date is a med assumption, listed in `to_confirm` right after the competition read, so the reply asks | — |
| `highest_and_best` | the listing agent called for highest and best; read from `note` when it says so ("highest and best"). With no escalation, `reply_lines` gets the flat-number reason (`flat_number`) | from `note` |
| `backup` | seller already has an accepted contract | — |

Heat (for inferring the competition): hot if DOM is under half the median or sale-to-list is 99%+; soft if DOM is over 1.5× the median or the price was cut. With under 3 months of supply (`market.months_supply`) the market is never called soft: a price cut alone reads normal, and long days on market read stale (this listing's own read, inferred as no competing offers). The Market Read reads the market and this listing apart, in one plain sentence: "Tight market, stale listing" with "Market tight (1.4 months of supply, sales at 96.4% of original list price); this home stale (78 days on market vs. a 23-day median, 2 price cuts), so the leverage comes from this home's price, not the market." (tight under 3 months of supply, balanced 3 to 6, soft over 6, the buyer CMA's own measure). A CMA handoff's ratio is against the original list price and is labeled Sale to Original List.

## listing_side

`buyer_broker_offered_pct` (what the seller offers; unknown → the buyer-broker agreement %, else the 2.5% default), `listing_fee_pct` (for the seller net sheet; unknown → the 2.5% default, 5% total with the buyer's agent; a default gets no label).

## costs (Buyer's Payment)

Top level, next to `buyer`. `rate` (interest rate as a **percent**: `6.5` for 6.5%, like lenders quote it; the lender's quote, else the latest Freddie Mac weekly 30-year average looked up at run time, a conventional-loan rate: with FHA, VA or USDA the assumptions say so and ask for the lender's quote for that program; 6.5 only as the offline fallback, said in the assumptions), `rate_source` (only with a looked-up rate: its source and week, "Freddie Mac weekly 30-year average, week of Sep 24, 2026"; the assumptions and a payment-capped price reason name it. Leave it out for the lender's quote: a quoted rate is not an assumption), `tax_rate` (optional: annual tax as a share of price, `0.0198`, when you have a plain rate rather than millage; used as is, so the payment assumes no homestead exemption unless the rate already includes one, and the assumptions say so), `insurance_annual` (default: with a buyer CMA handoff, the premium its payment used, so both reports show the same insurance and payment at the same price; otherwise the shared estimate the buyer CMA uses, the market's buyer insurance rate × price (the CMA's target price when an older handoff carries no premium, else list price) × an age factor (1.25 built before 2002, 1.5 before 1980), at least the market's floor (Florida 0.9% and $3,500; national 0.6% and $2,500); `insurance_rate` (a share of price for this home) replaces the market's rate; a figure the agent gives that isn't a quote for this address goes here with `buyer.insurance_quote: false`, and the assumptions list it as an estimate), `total_mills`, `school_mills`, `homestead` (tax with the market's homestead exemptions, default true and listed as an assumption: a second home or rental pays more), `district` (the taxing district's name or the property record's tax-area code, looked up in the built-in millage like the CMA skills). Without millage or a district, the built-in district matching the address's city is used (flagged: confirm the parcel is inside city limits; a city in two districts, like Orlando, uses the higher millage); else the market's fallback rate, with the reason no district matched; neither → payment leaves tax out, flagged. `flood_insurance_annual` (a quote; without one the payment leaves flood out, labeled "Before Flood Insurance", and the assumptions say whether a lender or Citizens requires it: never 0). When `buyer.max_payment` sets the price, an estimated rate (looked up or assumed) and an estimated premium are **high** impact: they move the price, so the answer is Preliminary and its line names them first.

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
| `closing_cost_pct` | the shared rule the buyer CMA uses, so both give the same cash to close: market buyer closing costs + 0.5% prepaids (national 3% + 0.5%); cash: half the market figure. The market's loan taxes (Florida: documentary stamps on the note and intangible tax) are added on top, and the report says "of price plus loan taxes". A value given here is the all-in share, used as is | low |
| `approval` | `preapproval` (`pof_verified` for cash). Values: `none`, `prequal`, `preapproval`, `du_approved` (pre-approval with an automated DU/LP approval), `full_uw` (underwriter approval), `pof_verified` (cash) | — |
| `lender_called` | false. True only when the agent says they talked to the lender about the financing: scored as verified approval; the worksheet's closing note says the financing was confirmed, not the date | — |
| `lender_confirmed_timeline` | false. True only when the lender confirmed it can close on the planned timeline: the closing note says so and the checklist's "Lender confirms a N-day close" box is ticked | — |
| `insurance_quote` | false, unless `costs.insurance_annual` is given: a premium entered there counts as a quote in hand (set `false` when that number is only an estimate). True when the buyer already has a quote for this address; `"planned"` only when the agent says one is coming. Only a quote in hand is scored; a planned one is a to-do | — |
| `va_later_use`, `va_exempt` | VA only: a later use of the benefit (higher funding fee under 5% down), or exempt from the fee | false |
| `lender_min_close_days` | 35 financed / 21 cash | — |
| `agent_track` | `average`: how a listing agent would rate the buyer's agent | — |
| `buyer_broker_agreement_pct` | none (flagged): the rate in the buyer's own broker agreement. When the seller pays less, the difference is a "Buyer's Broker Fee (Not Paid by Seller)" line in cash to close and counts in every limit | med |
| `needs_sale` | false (adds the sale-of-buyer's-property rider and a kick-out clause; the options are scored with both) | — |
| `sale_contingency_days` | 21 when `needs_sale` (flagged): days until the buyer's sale must close | med |
| `buyer_broker_form` | FAR/BAR: `GG` (a separate compensation agreement, the default) or `FF` (a seller credit to the buyer, which comes out of the loan program's concession limit) | — |
| `checklist` | package checklist statuses: `contract` `riders` `terms` `pre_approval` `funds` `insurance` `agency` `bb` `wire` `lead` `inspector` `lender_close` | Pending |

## overrides

The agent's call on any recommended term: `price`, `seller_concessions`, `deposit`, `inspection_days`, `loan_approval_days`, `appraisal_gap`, `closing_days`, `home_warranty`, `buyer_broker_pct`, `escalation`. Marked "Agent" in the report; the stronger and lower-cost options are built from the overridden offer.

## chosen_option

`recommended` (default), `stronger` or `lower_cost`: drives the worksheet.

## worksheet

`buyer_names`, `escrow_agent`, `title_agent`, `legal_description`, `parcel_id` (both copied exactly from the property report or tax record, never invented; a buyer CMA handoff fills them), `hoa_name`, `personal_property`, `acceptance_deadline` (the Time for Acceptance; default the expected Effective Date at 5:00 PM, moved to the next business day when that falls on a weekend or holiday, past the offers-due deadline), `contract_form` (`as_is` / `standard`, Florida; the options are scored on this same form, AS IS when blank and flagged), `repair_limits` (Standard only), `contract_name` (the form's name for any contract that isn't FAR/BAR; read on a best-effort basis). Missing names print as red blanks.
