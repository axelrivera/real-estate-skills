---
profile: market
schema: 1
layer: national                       # built-in estimates for any property; a state or MLS layer and the deal's own numbers win
name: National Estimates
as_of: 2026

# Planning estimates, not local rates. Every value used from here is labeled Estimate on reports, with a line saying
# what the agent can send to replace it. A section's key is filled only when no other layer has it, so an estimate
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
  buyer_closing_cost_pct: 0.03        # a buyer's closing costs, share of price

brokerage:                            # assumed 5% total until the deal says otherwise
  listing_fee_pct: 0.025
  buyer_broker_fee_pct: 0.025

property_tax:
  paid: arrears
  reassessed_on_sale: true
  fallback_rate: 0.011                # annual tax as share of price when the listing shows no tax bill

holding_costs:
  insurance_rate: 0.005
  utilities_monthly: 250

buyer_costs:
  insurance_rate: 0.006               # a buyer's new homeowner's policy, share of price per year
---

# Market Layer: National Estimates

Used for any property, below the state and MLS layers. Nothing here is a local rate: every value is shown as an estimate, and the deal's own numbers (a title quote, the state's transfer tax, the listing agreement's commission, the tax bill on the listing) replace it. Contract time rules are never estimated: they come from the contract.
