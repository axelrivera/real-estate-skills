---
profile: market
schema: 1
layer: state                          # built-in layer: used for Florida properties only
name: Florida
state: FL
as_of: 2026
counties: [Alachua, Baker, Bay, Bradford, Brevard, Broward, Calhoun, Charlotte, Citrus, Clay, Collier, Columbia, DeSoto, Dixie, Duval, Escambia, Flagler, Franklin, Gadsden, Gilchrist, Glades, Gulf, Hamilton, Hardee, Hendry, Hernando, Highlands, Hillsborough, Holmes, Indian River, Jackson, Jefferson, Lafayette, Lake, Lee, Leon, Levy, Liberty, Madison, Manatee, Marion, Martin, Miami-Dade, Monroe, Nassau, Okaloosa, Okeechobee, Orange, Osceola, Palm Beach, Pasco, Pinellas, Polk, Putnam, St. Johns, St. Lucie, Santa Rosa, Sarasota, Seminole, Sumter, Suwannee, Taylor, Union, Volusia, Wakulla, Walton, Washington]  # all 67; a county not in this list gets a spelling note

closing_costs:
  deed_transfer_tax_rate: 0.007       # documentary stamp tax on the deed, share of price
  deed_transfer_tax_payer: seller
  deed_transfer_tax_label: Documentary Stamp Tax on the Deed
  owner_title:
    payer: seller                     # who customarily pays the owner's title policy: seller | buyer
    rate_tiers:                       # promulgated rate, per $1,000 of price, applied tier by tier
      - {up_to: 100000, per_1000: 5.75}
      - {up_to: 1000000, per_1000: 5.00}
      - {up_to: 5000000, per_1000: 2.50}
      - {up_to: 10000000, per_1000: 2.25}
      - {up_to: null, per_1000: 2.00}
  seller_title_fees:                  # seller's title company charges; replace with the title company's quote
    settlement_fee: 700               # running the closing; commonly $450–$950, higher in Central Florida
    title_search: 250                 # $150–$500
    municipal_lien_search: 125        # $100–$125
    recording: 70                     # seller-side recording (e.g. mortgage release)
  hoa_estoppel_fee: 299               # when the property has an HOA or condo association
  buyer_closing_cost_pct: 0.025       # buyer's closing costs when no estimate is given, before the loan taxes in buyer_costs

# brokerage: none built in. Commissions are negotiable and not set by law: they come from the agent's own market
# profile (their standard terms) or the listing agreement and offer for each deal.

property_tax:
  paid: arrears                       # arrears: seller credits buyer from Jan 1 to closing (until the seller pays the bill in Nov)
  early_payment_discount: 0.04        # 4% for November payment; FR/BAR Standard K prorates allowing the maximum discount
  reassessed_on_sale: true            # capped assessments reset for the buyer
  fallback_rate: 0.018                # annual tax as share of price when no bill is available
  primary_residence_exemptions:       # Florida homestead (s. 196.031; verified 2026-09-24, CORE-17)
    - {amount: 25000, levies: all}
    - {amount: 26411, above: 50000, levies: non_school, year: 2026}  # CPI-indexed each Jan 1; covers $50,000 to $76,411
  portability: true                   # a buyer leaving a Florida homestead can carry up to $500,000 of the capped difference
  exemption_filing_deadline: March 1 of the year after closing
  millage:                            # 2025 final (bills mailed Nov 2025), per $1,000 of taxable value; verify every year
                                      # total = all ad valorem levies for a typical parcel; excludes non-ad valorem assessments
    # Orange
    - {county: Orange, district: "Orange County (unincorporated, St. Johns WMD)", code: "11", year: 2025, school: 6.4490, total: 16.0858}
    - {county: Orange, district: "Orange County (unincorporated, South Florida WMD)", code: "10", year: 2025, school: 6.4490, total: 16.1366}
    - {county: Orange, district: "Orlando (St. Johns WMD)", code: "8/28/71/78", year: 2025, school: 6.4490, total: 18.0878}
    - {county: Orange, district: "Orlando (South Florida WMD)", code: "22/25/26/27/36/95", year: 2025, school: 6.4490, total: 18.1386}
    - {county: Orange, district: "Winter Park", code: "2/4/6", year: 2025, school: 6.4490, total: 15.3615}
    - {county: Orange, district: "Apopka", code: "5/11/65", year: 2025, school: 6.4490, total: 15.8754}
    - {county: Orange, district: "Ocoee", code: "65", year: 2025, school: 6.4490, total: 16.3878}
    - {county: Orange, district: "Winter Garden", code: "11/63/64/65", year: 2025, school: 6.4490, total: 16.2943}
    - {county: Orange, district: "Maitland", code: "6", year: 2025, school: 6.4490, total: 16.3055}
    - {county: Orange, district: "Windermere", code: "35", year: 2025, school: 6.4490, total: 15.2311}
    # Seminole
    - {county: Seminole, district: "Seminole County (unincorporated)", code: "01,02", year: 2025, school: 5.2490, total: 13.6790}
    - {county: Seminole, district: "Altamonte Springs", code: "A1", year: 2025, school: 5.2490, total: 17.5683}
    - {county: Seminole, district: "Casselberry", code: "C1,C2", year: 2025, school: 5.2490, total: 18.1808}
    - {county: Seminole, district: "Lake Mary", code: "M1", year: 2025, school: 5.2490, total: 14.3929}
    - {county: Seminole, district: "Longwood", code: "L1", year: 2025, school: 5.2490, total: 16.3034}
    - {county: Seminole, district: "Oviedo", code: "V1,V2,V5", year: 2025, school: 5.2490, total: 16.7784}
    - {county: Seminole, district: "Sanford", code: "S1,S3", year: 2025, school: 5.2490, total: 18.1284}
    - {county: Seminole, district: "Winter Springs", code: "W1,W2", year: 2025, school: 5.2490, total: 16.1883}
    # Osceola
    - {county: Osceola, district: "Osceola County (unincorporated)", code: "300", year: 2025, school: 5.3060, total: 13.8543}
    - {county: Osceola, district: "Kissimmee", code: "200", year: 2025, school: 5.3060, total: 17.4114}
    - {county: Osceola, district: "St. Cloud", code: "100", year: 2025, school: 5.3060, total: 17.8989}
    # Lake
    - {county: Lake, district: "Lake County (unincorporated, north)", code: "0001", year: 2025, school: 6.0850, total: 13.4482}
    - {county: Lake, district: "Lake County (unincorporated, south)", code: "0004", year: 2025, school: 6.0850, total: 13.0661}
    - {county: Lake, district: "Clermont", code: "000C", year: 2025, school: 6.0850, total: 16.6766}
    - {county: Lake, district: "Clermont (Wellness Way)", code: "WW0C", year: 2025, school: 6.0850, total: 17.1351}
    - {county: Lake, district: "Leesburg", code: "000L", year: 2025, school: 6.0850, total: 15.9477}
    - {county: Lake, district: "Eustis", code: "000E", year: 2025, school: 6.0850, total: 19.8623}
    - {county: Lake, district: "Tavares", code: "000T", year: 2025, school: 6.0850, total: 19.3042}
    - {county: Lake, district: "Mount Dora", code: "00MD", year: 2025, school: 6.0850, total: 18.7725}
    - {county: Lake, district: "Groveland", code: "00GR", year: 2025, school: 6.0850, total: 17.7866}
    - {county: Lake, district: "Minneola", code: "00MI", year: 2025, school: 6.0850, total: 17.5866}
    # Volusia
    - {county: Volusia, district: "Volusia County (unincorporated, west)", code: "100", year: 2025, school: 5.2790, total: 17.3640}
    - {county: Volusia, district: "Volusia County (unincorporated, northeast)", code: "200", year: 2025, school: 5.2790, total: 17.2995}
    - {county: Volusia, district: "Volusia County (unincorporated, southeast)", code: "600", year: 2025, school: 5.2790, total: 16.9077}
    - {county: Volusia, district: "Deltona", code: "016", year: 2025, school: 5.2790, total: 18.7448}
    - {county: Volusia, district: "DeLand", code: "012", year: 2025, school: 5.2790, total: 18.2289}
    - {county: Volusia, district: "Daytona Beach", code: "204", year: 2025, school: 5.2790, total: 18.0498}
    - {county: Volusia, district: "Ormond Beach", code: "201", year: 2025, school: 5.2790, total: 16.3635}
    - {county: Volusia, district: "Port Orange (Halifax hospital district)", code: "402", year: 2025, school: 5.2790, total: 17.1176}
    - {county: Volusia, district: "Port Orange (Southeast hospital district)", code: "602", year: 2025, school: 5.2790, total: 16.7258}
    - {county: Volusia, district: "New Smyrna Beach", code: "601", year: 2025, school: 5.2790, total: 16.3370}
    - {county: Volusia, district: "DeBary", code: "015", year: 2025, school: 5.2790, total: 15.6948}
    - {county: Volusia, district: "Orange City", code: "014", year: 2025, school: 5.2790, total: 19.2835}
    # Polk
    - {county: Polk, district: "Polk County (unincorporated)", code: "90", year: 2025, school: 5.2900, total: 12.9291}
    - {county: Polk, district: "Lakeland (in transit district)", code: "91510", year: 2025, school: 5.2900, total: 18.0402}
    - {county: Polk, district: "Lakeland (outside transit district)", code: "90510", year: 2025, school: 5.2900, total: 17.5402}
    - {county: Polk, district: "Winter Haven", code: "90410", year: 2025, school: 5.2900, total: 18.6979}
    - {county: Polk, district: "Haines City", code: "90420", year: 2025, school: 5.2900, total: 19.4474}
    - {county: Polk, district: "Davenport", code: "90430", year: 2025, school: 5.2900, total: 19.3579}
    - {county: Polk, district: "Bartow", code: "90310", year: 2025, school: 5.2900, total: 18.2159}
    - {county: Polk, district: "Auburndale", code: "90330", year: 2025, school: 5.2900, total: 16.3594}
    - {county: Polk, district: "Lake Wales", code: "90320", year: 2025, school: 5.2900, total: 20.1541}
    # Sumter
    - {county: Sumter, district: "The Villages (unincorporated Sumter)", year: 2025, school: 4.9120, total: 10.0315, note: "summed from published rates"}
    - {county: Sumter, district: "The Villages (inside Wildwood)", code: "2002V", year: 2025, school: 4.9120, total: 12.8602}
    - {county: Sumter, district: "Sumter County (unincorporated)", year: 2025, school: 4.9120, total: 10.8422}
    - {county: Sumter, district: "Wildwood (outside The Villages)", code: "2002", year: 2025, school: 4.9120, total: 13.6709, note: "summed from published rates"}
    - {county: Sumter, district: "Bushnell", code: "6006", year: 2025, school: 4.9120, total: 14.1483, note: "summed from published rates"}
  millage_sources:                    # property appraiser final millage sheets
    Orange: "https://ocpaimages.ocpafl.org/api/Content/GetContentDynamicFile?contentFileID=416846"
    Seminole: "https://files.scpafl.org/files/Public/MILLAGERATES/SeminoleCoMillageRates.pdf"
    Osceola: "https://www.property-appraiser.org/wp-content/uploads/2025/10/2025-Final-Millage-Rates.pdf"
    Lake: "https://www.lakecopropappr.com/pdfs/2025/Tax%20Roll/2025MillageSheet%20-%20ADA.pdf"
    Volusia: "https://vcpa.vcgov.org/files/historical/2025/final/finalmillagerates2025final.pdf"
    Polk: "https://www.polkflpa.gov/downloads/Files/finalmillage.pdf"
    Sumter: "https://www.sumterpa.com/tax-and-exemptions/tax-rates/"

holding_costs:
  insurance_rate: 0.007               # seller's annual homeowner's insurance as share of price, for holding-cost estimates
  utilities_monthly: 250

buyer_costs:
  insurance_rate: 0.009               # a buyer's new homeowner's policy, share of price, for payment estimates; a quote replaces it
  loan_taxes:                         # on the loan amount, paid by the buyer when the purchase is financed (CORE-16)
    - {label: Documentary Stamp Tax on the Note, rate: 0.0035}   # s. 201.08: $0.35 per $100
    - {label: Intangible Tax on the Mortgage, rate: 0.002}       # s. 199.133: 2 mills

flood:                                # verified 2026-09-24 (docs/audits/2026-09-23-verification.md, CMA-6)
  citizens_requirement:               # s. 627.351(6)(aa): Citizens personal residential policies must carry flood coverage,
    statute: "s. 627.351(6)(aa)"      # by dwelling replacement cost; HO-6 unit policies and policies without wind are exempt
    schedule:
      - {from: "2024-01-01", min_replacement_cost: 600000}
      - {from: "2025-01-01", min_replacement_cost: 500000}
      - {from: "2026-01-01", min_replacement_cost: 400000}
      - {from: "2027-01-01", min_replacement_cost: 0}
  seller_disclosure:                  # given at or before the contract is signed, residential sales
    statute: "s. 689.302"
    asks: "known flood damage during ownership, flood insurance claims (including NFIP), and federal flood assistance (including FEMA)"

condo:                                # FR/BAR CR-7x; ss. 718.503, 720.401 (verified 2026-09-24, TL-11)
  rescission: "the buyer may cancel within 7 days, excluding weekends and legal holidays, after the later of signing and receiving the association documents; the right ends at closing (s. 718.503)"
  sirs_milestone: "a separate 7-business-day right to void after receiving the milestone inspection summary and the structural integrity reserve study (SIRS)"
  hoa_rescission: "without the HOA disclosure summary before signing, the buyer may cancel within 3 days after receiving it; the right ends at closing (s. 720.401)"

contract:                             # FR/BAR ASIS-7 / CRSP Standard F (checked against ASIS-7x Rev. 2/26)
  forms: [FR/BAR AS IS, FR/BAR Standard]
  day_count: calendar                 # Day 1 is the day after the Effective Date
  short_period_days: 0                # none: current FR/BAR forms count every period in calendar days
  end_time: "23:59"                   # the form sets no time of day: a period runs to the end of its last day
  weekend_holiday_rollover: next_business_day
  rollover_time: "23:59"              # extends to the next business day, to the end of that day
  before_closing_rollover: next_business_day  # Standard F extends every period and date, including those counted back from closing
  before_closing_time: "23:59"
  closing_rollover: true              # a Closing Date on a weekend or holiday extends to the next business day
  holidays: us_federal
  inspection_credit_reserve_pct: 0.007  # typical post-inspection renegotiation on AS IS contracts
  typical_deposit_pct: 0.03           # a strong escrow deposit on a financed offer, share of price

cma:                                  # calibrated on Central Florida (Seminole County) sales
  calibrated_for:                     # CMA-10: flat dollar rates fit these counties and prices; elsewhere the CMA warns
    counties: [Seminole, Orange, Osceola, Lake, Volusia]
    price_range: [300000, 700000]
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
  Miami-Dade:                          # FR/BAR 9(c)(iii) regional provision: buyer pays the owner's policy; the seller
    closing_costs:                    # pays the title search (up to $200 if blank), tax search and municipal lien search
      deed_transfer_tax_rate: 0.006
      deed_transfer_surtax: {rate: 0.0045, applies_unless: single_family, label: Miami-Dade Documentary Surtax}
      owner_title: {payer: buyer}
      seller_title_fees: {title_search: 200}
  Broward:                            # 9(c)(iii), as Miami-Dade
    closing_costs:
      owner_title: {payer: buyer}
      seller_title_fees: {title_search: 200}
  Sarasota:                           # 9(c)(ii): the buyer pays the owner's policy and Charges (title search) and the lien search
    closing_costs:
      owner_title: {payer: buyer}
      seller_title_fees: {title_search: 0, municipal_lien_search: 0}
  Collier:                            # 9(c)(ii), as Sarasota (verified 2026-09-24; see docs/audits/2026-09-23-verification.md)
    closing_costs:
      owner_title: {payer: buyer}
      seller_title_fees: {title_search: 0, municipal_lien_search: 0}
  Monroe:                             # split by area (Upper Keys buyer, Middle Keys seller, Lower Keys mixed): ask
    closing_costs:
      owner_title: {payer: ask}
---

# Market profile layer: Florida

Built-in state defaults. Skills use them only for Florida properties. For any other state, values come from the user's own market profile or are asked for. MLS formats are a separate layer (`../mls/`), because an MLS can span states and a state can have several MLSs.

## Notes

- Closing costs are estimates for comparing options, not a settlement statement.
- Seller title fee defaults (2026) are midpoints of ranges published by Florida title companies and closing cost guides; the title company's quote always wins.
- No brokerage defaults: commissions are negotiable and not set by law. Since 2024, buyer-broker pay is negotiated per deal and may be paid by the seller, the buyer, or split. Use the listing agreement and offer terms, or the agent's standard terms from their market profile.
- Who pays the owner's title policy varies by county (custom, not law). Seller in most of Florida; buyer in Miami-Dade, Broward, Sarasota and Collier; seller in Lee and Charlotte; Monroe varies by area, so the skills ask. Confirm with the title company for counties not listed.
- Millage (2025 final) covers the unincorporated area and main cities of Orange, Seminole, Osceola, Lake, Volusia, Polk and Sumter. Rates vary within a city and within unincorporated areas (water management district, fire, transit, hospital and special districts), so the right number comes from the parcel's tax district code on the property appraiser record. Orange's school rate (6.449) is from the school board's adoption, not the appraiser sheet. Sumter's Villages, Wildwood and Bushnell totals marked "summed" add up the published rates; there's no official aggregate. The Villages' CDD charges are non-ad valorem and can add over $2,000 a year.
- Property tax for the buyer is based on the purchase price, not the seller's bill. The estimate assumes the appraiser values the home at the purchase price, so it often runs high. Non-ad valorem assessments are excluded. Warn about the first-year escrow jump.
- HOA estoppel fees are capped by statute; associations with delinquencies can charge more.
- FIRPTA is not computed. If the seller is a foreign person, flag 15% withholding and refer to the title company or a CPA.
- CMA adjustment defaults were calibrated on Central Florida sales. Other Florida areas should set their own in a market profile.
- Contract dates follow the FR/BAR definitions. Verify against the form version on the executed contract.
- Flood: a lender requires flood insurance in a Special Flood Hazard Area (zones A and V). Outside one, Citizens still requires it on a policy at or above the replacement cost in `flood.citizens_requirement` for its year, and on every Citizens policy from January 1, 2027, so never write that flood insurance "isn't required". The seller gives the s. 689.302 flood disclosure at or before signing.
- Condos: the rescission and SIRS rights in `condo` are the buyer's; deliver the association documents early so the clock starts.
- Insurance: don't quote premiums. Name the drivers (roof age, wiring and plumbing era, wind mitigation, pool, flood zone) and tell the buyer to get a quote after the 4-point and wind-mitigation inspections.
