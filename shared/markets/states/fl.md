---
profile: market
schema: 1
layer: state                          # built-in layer: used for Florida properties only
name: Florida
state: FL
as_of: 2025

closing_costs:
  deed_transfer_tax_rate: 0.007       # documentary stamp tax on the deed, share of price
  deed_transfer_tax_payer: seller
  owner_title:
    payer: seller                     # who customarily pays the owner's title policy: seller | buyer
    rate_tiers:                       # promulgated rate, per $1,000 of price, applied tier by tier
      - {up_to: 100000, per_1000: 5.75}
      - {up_to: 1000000, per_1000: 5.00}
      - {up_to: 5000000, per_1000: 2.50}
      - {up_to: 10000000, per_1000: 2.25}
      - {up_to: null, per_1000: 2.00}
  settlement_fee: 645                 # title settlement and search; replace with the title company's quote
  hoa_estoppel_fee: 299               # when the property has an HOA or condo association
  buyer_closing_cost_pct: 0.03        # buyer's closing costs when no estimate is given
  listing_fee_pct: 0.03               # listing brokerage fee when the seller's agreement isn't given

property_tax:
  paid: arrears                       # arrears: seller credits buyer from Jan 1 to closing
  reassessed_on_sale: true            # capped assessments reset for the buyer
  fallback_rate: 0.018                # annual tax as share of price when no bill is available
  primary_residence_exemptions:       # Florida homestead
    - {amount: 25000, levies: all}
    - {amount: 25000, levies: non_school}
  exemption_filing_deadline: March 1 of the year after closing
  millage:                            # per $1,000 of taxable value; verify every year
    - {district: Seminole County (unincorporated), year: 2025, school: 5.2490, total: 13.6790}
    - {district: City of Altamonte Springs, year: 2025, school: 5.2490, total: 17.5683}

holding_costs:
  insurance_rate: 0.007               # annual homeowner's insurance as share of price, for holding-cost estimates
  utilities_monthly: 250

contract:
  forms: [FR/BAR AS IS, FR/BAR Standard]
  day_count: calendar                 # Day 1 is the day after the Effective Date
  short_period_days: 5                # periods this long or shorter skip weekends and holidays
  end_time: "23:59"
  weekend_holiday_rollover: next_business_day
  rollover_time: "17:00"
  before_closing_rollover: previous_business_day
  holidays: us_federal
  inspection_credit_reserve_pct: 0.007  # typical post-inspection renegotiation on AS IS contracts

cma:                                  # calibrated on Central Florida (Seminole County) sales
  radius_miles: 1
  lookback_months: 6
  typical_range_width: 25000
  adjustments:
    living_area_per_sqft: 75          # for differences under about 300 sq ft
    pool: 25000
    full_renovation_vs_dated: [40000, 45000]
    full_vs_partial_renovation: 30000
    documented_recent_systems: -5000
    lot_or_water_premium: [-10000, -5000]
    market_shift_per_quarter: [0.01, 0.02]  # when the data shows softening; 0 for sales in the last ~6 weeks

county_overrides:
  Miami-Dade:
    closing_costs:
      deed_transfer_tax_rate: 0.006   # single-family homes
      owner_title: {payer: buyer}
  Broward:
    closing_costs:
      owner_title: {payer: buyer}
  Sarasota:
    closing_costs:
      owner_title: {payer: buyer}
---

# Market profile layer: Florida

Built-in state defaults. Skills use them only for Florida properties. For any other state, values come from the user's own market profile or are asked for. MLS formats are a separate layer (`../mls/`), because an MLS can span states and a state can have several MLSs.

## Notes

- Closing costs are estimates for comparing options, not a settlement statement.
- Who pays the owner's title policy varies by county. Seller in most of Florida, buyer in parts of South and Southwest Florida. Confirm with the title company for counties not listed.
- Property tax for the buyer is based on the purchase price, not the seller's bill. The estimate assumes the appraiser values the home at the purchase price, so it often runs high. Non-ad valorem assessments are excluded. Warn about the first-year escrow jump.
- HOA estoppel fees are capped by statute; associations with delinquencies can charge more.
- FIRPTA is not computed. If the seller is a foreign person, flag 15% withholding and refer to the title company or a CPA.
- CMA adjustment defaults were calibrated on Central Florida sales. Other Florida areas should set their own in a market profile.
- Contract dates follow the FR/BAR definitions. Verify against the form version on the executed contract.
- Insurance: don't quote premiums. Name the drivers (roof age, wiring and plumbing era, wind mitigation, pool, flood zone) and tell the buyer to get a quote after the 4-point and wind-mitigation inspections.
