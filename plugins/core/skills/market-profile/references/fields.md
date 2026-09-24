# Market Profile Fields

Every setting the skills read, what it means, and the format.

For the owner's title policy the agent's own number wins: the title company's `quote`, then a promulgated `rate_tiers` table, then `estimate_pct`. Where the table is promulgated (Florida), it's also the legal premium, so a quote below it gets a warning to check the quote. Rates are decimals (0.007 = 0.7%). Money is whole dollars. The built-in Florida values are good worked examples: they're in this skill's folder at `scripts/_shared/markets/states/fl.md` (read-only; the agent's profile overrides them).

## Identity

| Field | Meaning |
|---|---|
| `name` | What the agent calls this market ("Seminole County", "Austin metro") |
| `state` | Two-letter code or full name. The only required field |
| `area` | Counties or cities it covers (free text). One profile can cover several counties: put what differs by county in `county_overrides` |
| `mls` | MLS name ("Stellar", "ACTRIS"). Built in: Stellar |

## closing_costs

| Field | Meaning |
|---|---|
| `deed_transfer_tax_rate` | State or local tax on the deed, share of price. FL: 0.007. `0` where there is none (Texas): then no payer is needed |
| `deed_transfer_tax_payer` | `seller`, `buyer` or `split` by custom |
| `deed_transfer_tax_label` | Local name for the tax, in Title Case since it shows as a row name on net sheets ("Documentary Stamp Tax on the Deed") |
| `owner_title.payer` | Who customarily pays the owner's title policy: `seller` or `buyer` |
| `owner_title.rate_tiers` | Promulgated rate table: list of `{up_to, per_1000}`, last `up_to: null` |
| `owner_title.quote` | `{price, premium}`: one title company quote, e.g. `{price: 400000, premium: 2400}`. Used as a share of price at other prices |
| `owner_title.estimate_pct` | A rough share of price, when there's no table or quote |
| `seller_title_fees` | Seller's title company charges by name, e.g. `settlement_fee`, `title_search`, `municipal_lien_search`, `recording`. Names are free-form; every amount is added up. Fees merge one by one with the built-in ones (source `mixed`): a quote naming only the settlement fee keeps the built-in search, lien search and recording. Set a built-in fee to `0` to drop it (an all-inclusive quote). For a split escrow or settlement fee, store the seller's share |
| `hoa_estoppel_fee` | HOA or condo status letter fee |
| `buyer_closing_cost_pct` | Buyer's closing costs when no estimate is given, share of price |

## brokerage

| Field | Meaning |
|---|---|
| `listing_fee_pct` | The agent's standard listing brokerage fee: the listing side only. Nothing is built in; skills mark it "Standard Terms" until a listing agreement replaces it |
| `buyer_broker_fee_pct` | The buyer's brokerage pay the agent's sellers usually offer (negotiated per deal), added on top of the listing fee in net sheets |

## property_tax

| Field | Meaning |
|---|---|
| `paid` | `arrears` (seller credits buyer for the year so far) or `advance` |
| `reassessed_on_sale` | `true` when the buyer's bill resets to the price |
| `fallback_rate` | Annual tax as share of price when there's no bill or millage. Outside built-in markets this is enough; millage is optional |
| `primary_residence_exemptions` | List of `{amount, levies}` or `{percent, levies}`, optionally with `above` (the exemption covers only value above that amount; Florida's indexed second exemption starts at $50,000) and `year` (percent of value, `0.20` = 20%). `levies`: `all`, `non_school` (all but school) or `school` (school only). Example for Texas (confirm the current amount): `{amount: 140000, levies: school}` plus any local `{percent: 0.20, levies: non_school}` |
| `millage` | List of `{county, district, code, year, school, total}` per $1,000 of taxable value. Rates quoted per $100 (Texas) × 10 = mills: $2.10 per $100 is 21 mills |
| `millage_sources` | `{county: url}` for the millage figures |

## holding_costs

| Field | Meaning |
|---|---|
| `insurance_rate` | Seller's annual homeowner's insurance, share of price, for holding-cost estimates (offer reviews) |
| `utilities_monthly` | Monthly utilities while listed |

## buyer_costs

| Field | Meaning |
|---|---|
| `insurance_rate` | A buyer's new homeowner's policy, share of price per year, for payment estimates when there's no quote |
| `loan_taxes` | Taxes on a financed buyer's loan, `[{label, rate}]` on the loan amount (Florida: note stamps 0.0035, intangible tax 0.002). Added on top of `buyer_closing_cost_pct`, so set that share without them |

Holding and buyer insurance are optional: without them the offer skills use a national planning estimate and say so.

## contract

| Field | Meaning |
|---|---|
| `forms` | Contract forms in use ("TREC 20-18", "FR/BAR AS IS") |
| `day_count` | `calendar` or `business` |
| `short_period_days` | Periods this long or shorter skip weekends and holidays (0 if none) |
| `end_time` | When a day ends, `"23:59"` or `"17:00"` |
| `weekend_holiday_rollover` | `next_business_day` or `none` |
| `rollover_time` | Time on the next business day when a period rolls over |
| `before_closing_rollover` | For dates counted back from closing: `previous_business_day` or `none` |
| `holidays` | `us_federal` or a list of dates |
| `inspection_credit_reserve_pct` | Typical post-inspection credit, share of price |
| `typical_deposit_pct` | A strong earnest money / escrow deposit on a financed offer, share of price (Florida 0.03). Offer reviews counter below it; without it, 1% |

## cma

| Field | Meaning |
|---|---|
| `radius_miles`, `lookback_months` | Default comp search |
| `typical_range_width` | Typical width of the value range, dollars |
| `adjustments` | `living_area_per_sqft`, `pool`, `full_renovation_vs_dated`, `full_vs_partial_renovation`, `documented_recent_systems`, `lot_or_water_premium`, `market_shift_per_quarter`. A `[low, high]` pair is a range |

## mls_format

Only needed when the agent's MLS isn't built in and they'll upload MLS files.

| Field | Meaning |
|---|---|
| `cma_export_columns` | Map from the skills' names (`close_price`, `living_area`, `days_on_market`, …; see the Stellar layer for the full list) to the column headers in the agent's MLS export |
| `history_codes` | Status codes in the listing history and what they mean |

## fair_housing

| Field | Meaning |
|---|---|
| `extra_protected_classes` | State and local protected classes beyond the federal list, as a list ("age", "marital status", "source of income", "military status"). Every skill avoids wording about them, like the federal classes. Only what the agent confirms or a cited law or ordinance says; Florida and Texas state law add none, but cities and counties can. Can go in `county_overrides` when one county differs |

## offer_norms

What a clean offer looks like locally. The seller's offer review rates each offer against these and drafts its counter from the same numbers; without them it uses national planning norms and says so.

| Field | Meaning |
|---|---|
| `deposit_pct` | A strong escrow deposit on a financed offer, share of price (Florida 0.03; Texas earnest money is often 0.01). Cash offers are held to at least 0.05 |
| `concessions_pct` | Seller-paid costs above this share of price are worth countering (Florida 0.015) |
| `inspection_days` | A competitive inspection or option period (Florida 7) |
| `loan_approval_days` | A competitive loan approval period (Florida 21) |

## flood and condo

Built in for Florida; set them for another state only from a cited statute or program rule.

| Field | Meaning |
|---|---|
| `flood.citizens_requirement` | `{statute, schedule: [{from, min_replacement_cost}]}`: a state insurer's flood requirement by date and dwelling replacement cost (0 = every policy). Buyer payments cite it instead of saying flood insurance "isn't required" |
| `flood.seller_disclosure` | `{statute, asks}`: a seller flood disclosure due at or before the contract. Offer reviews flag it until it's given |
| `condo.rescission`, `condo.sirs_milestone`, `condo.hoa_rescission` | One sentence each on the buyer's cancellation rights; offer reviews quote them for a condo |

## county_overrides

`{County name: {any of the sections above}}` for local exceptions, e.g. a county where the buyer pays for title. A value of `ask` means the custom varies within the county (Monroe's title payer): the skills treat it as unknown and ask. The agent's values, general or per county, always win over the built-in county customs.
