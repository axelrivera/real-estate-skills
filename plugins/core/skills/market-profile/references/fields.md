# Market profile fields

Every setting the skills read, what it means, and the format. Rates are decimals (0.007 = 0.7%). Money is whole dollars. The built-in Florida values are in `scripts/_shared/markets/states/fl.md` and are good worked examples.

## Identity

| Field | Meaning |
|---|---|
| `name` | What the agent calls this market ("Seminole County", "Austin metro") |
| `state` | Two-letter code or full name. The only required field |
| `area` | Counties or cities it covers (free text) |
| `mls` | MLS name ("Stellar", "ACTRIS"). Built in: Stellar |

## closing_costs

| Field | Meaning |
|---|---|
| `deed_transfer_tax_rate` | State or local tax on the deed, share of price. FL: 0.007 |
| `deed_transfer_tax_payer` | `seller`, `buyer` or `split` by custom |
| `deed_transfer_tax_label` | Local name for the tax ("Documentary stamp tax on the deed") |
| `owner_title.payer` | Who customarily pays the owner's title policy: `seller` or `buyer` |
| `owner_title.rate_tiers` | Promulgated rate table: list of `{up_to, per_1000}`, last `up_to: null` |
| `owner_title.estimate_pct` | Use instead of `rate_tiers` where rates aren't promulgated: share of price |
| `seller_title_fees` | Seller's title company charges by name, e.g. `settlement_fee`, `title_search`, `municipal_lien_search`, `recording` |
| `hoa_estoppel_fee` | HOA or condo status letter fee |
| `buyer_closing_cost_pct` | Buyer's closing costs when no estimate is given, share of price |

## brokerage

| Field | Meaning |
|---|---|
| `listing_fee_pct` | Seller's listing brokerage default |
| `buyer_broker_fee_pct` | Buyer's brokerage default (negotiated per deal) |

## property_tax

| Field | Meaning |
|---|---|
| `paid` | `arrears` (seller credits buyer for the year so far) or `advance` |
| `reassessed_on_sale` | `true` when the buyer's bill resets to the price |
| `fallback_rate` | Annual tax as share of price when there's no bill or millage |
| `primary_residence_exemptions` | List of `{amount, levies}`; `levies` is `all` or `non_school` |
| `millage` | List of `{county, district, code, year, school, total}` per $1,000 of taxable value |
| `millage_sources` | `{county: url}` for the millage figures |

## holding_costs

| Field | Meaning |
|---|---|
| `insurance_rate` | Annual homeowner's insurance, share of price, for holding-cost estimates |
| `utilities_monthly` | Monthly utilities while listed |

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

## county_overrides

`{County name: {any of the sections above}}` for local exceptions, e.g. a county where the buyer pays for title.
