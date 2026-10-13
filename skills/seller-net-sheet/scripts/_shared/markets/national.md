---
profile: market
schema: 1
layer: national                       # built-in estimates for any property; a state or MLS layer and the deal's own numbers win
name: National Estimates
as_of: 2026

# Planning estimates, not local rates. Every value used from here is named once in a report's notes, never on its
# line, with a line saying what the agent can send to replace it. A section's key is filled only when no other layer has it, so an estimate
# never mixes into a state's own fee list.

# States with no state deed transfer tax (Arizona charges only a flat $2 affidavit fee). Best-practice assumption:
# none is charged, never the estimate below. A few cities and counties add their own (Washington County, Oregon),
# so reports say to verify. Checked 2026-09-24 against state revenue sources and the NCSL transfer-tax table.
no_state_transfer_tax: [AK, AZ, ID, IN, KS, LA, MS, MO, MT, ND, NM, OR, TX, UT, WY]

closing_costs:
  deed_transfer_tax_rate: 0.004       # a middle value across the states that tax deeds (0.1% to over 1%); never used
                                      # in a no_state_transfer_tax state; the skill looks up the state's rate first
  deed_transfer_tax_payer: seller
  deed_transfer_tax_label: Transfer Tax
  owner_title:
    payer: seller
    estimate_pct: 0.005               # owner's title policy, share of price
  seller_title_fees:
    settlement_and_title_fees: 1200   # settlement, search and recording, seller side
  hoa_estoppel_fee: 250
  hoa_estoppel_label: HOA Documents   # the association's payoff and status documents, a state-neutral name
                                      # (an estoppel letter in Florida, a resale certificate in Texas)
  buyer_closing_cost_pct: 0.03        # a buyer's closing costs, share of price

brokerage:                            # assumed 5% total until the deal says otherwise
  listing_fee_pct: 0.025
  buyer_broker_fee_pct: 0.025

# Each state's average effective property tax rate on owner-occupied homes (total real estate taxes paid / total home
# value), used as property_tax.fallback_rate for a property in that state when the listing shows no tax bill and no
# layer has a rate (source 'state_average'; a report's notes call it the state's average effective rate). Florida
# keeps its own built-in rate (states/fl.md). Puerto Rico isn't in the table, so it falls to the national rate below.
# Source: Tax Foundation, Facts & Figures 2025, Table 33, "Property Taxes Paid as a Percentage of Owner-Occupied
# Housing Value", calendar year 2023 (US Census Bureau, American Community Survey). Checked 2026-10-12.
state_property_tax_rates:
  AL: 0.0036
  AK: 0.0091
  AZ: 0.0044
  AR: 0.0053
  CA: 0.0070
  CO: 0.0050
  CT: 0.0148
  DE: 0.0050
  DC: 0.0061
  GA: 0.0077
  HI: 0.0032
  ID: 0.0048
  IL: 0.0183
  IN: 0.0077
  IA: 0.0123
  KS: 0.0119
  KY: 0.0073
  LA: 0.0055
  ME: 0.0094
  MD: 0.0090
  MA: 0.0097
  MI: 0.0115
  MN: 0.0099
  MS: 0.0058
  MO: 0.0088
  MT: 0.0060
  NE: 0.0143
  NV: 0.0049
  NH: 0.0141
  NJ: 0.0177
  NM: 0.0061
  NY: 0.0126
  NC: 0.0062
  ND: 0.0094
  OH: 0.0131
  OK: 0.0077
  OR: 0.0078
  PA: 0.0119
  RI: 0.0105
  SC: 0.0047
  SD: 0.0099
  TN: 0.0049
  TX: 0.0136
  UT: 0.0047
  VT: 0.0142
  VA: 0.0077
  WA: 0.0075
  WV: 0.0048
  WI: 0.0125
  WY: 0.0055

property_tax:
  paid: arrears
  reassessed_on_sale: true
  fallback_rate: 0.011                # annual tax as share of price when the listing shows no tax bill and the state
                                      # isn't known or isn't in state_property_tax_rates
                                      # due_date: MM-DD (none nationally): when a market's bill is due that year; a
                                      # closing after it assumes the bill paid (finance.tax_proration)

cma:
  adjustments_national:               # owner decision 2026-10-13: where no market rates are built in and no paired
                                      # sales or agent's rates are given, the CMAs scale these to the comps' median
                                      # sale price, so two runs on the same sales agree; named once in the notes
    living_area_ppsf_share: 0.33      # size: a third of the comps' median price per square foot
    condition_level_shares:           # each condition level over an original home, as a share of price (Florida's
      original: 0                     # dollar levels at about $440,000, as shares)
      cosmetic: 0.01
      baths_only: 0.02
      kitchen_only: 0.035
      kitchen_and_baths: 0.055
      full_renovation: 0.10
      new: 0.11
    lot_type_shares:                  # each lot type over a standard lot
      corner_or_oversized: 0.01
      view: 0.01
      canal: 0.02
      lake_or_open_water: 0.02
    recent_systems_share: 0.01        # documented recent systems other than the roof

holding_costs:
  insurance_rate: 0.005
  utilities_monthly: 250

buyer_costs:
  insurance_rate: 0.006               # a buyer's new homeowner's policy, share of price per year
---

# Market Layer: National Estimates

Used for any property, below the state and MLS layers. Nothing here is a local rate: every value is shown as an estimate (property tax with no bill uses the state's average effective rate from the table above, else 1.1%), and the deal's own numbers (a title quote, the state's transfer tax, the listing agreement's commission, the tax bill on the listing) replace it. Contract time rules are never estimated: they come from the contract.
