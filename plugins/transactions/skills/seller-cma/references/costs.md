# Costs: the net sheet and buyer payments

## Net sheet

compute.py runs each strategy's expected sale price through the shared seller-net calculator. Every local value comes from the market profile (the built-in Florida layer and its county customs, then the agent's own market profile, which always wins), so the same report works in any state.

| Line | Where it comes from |
|---|---|
| Listing brokerage, buyer's agent compensation | `costs.listing_fee_pct` / `costs.buyer_broker_fee_pct` in report.json when the agent gave terms (fractions of price: `0.025` means 2.5%; `0` when the seller won't offer buyer's agent compensation). Otherwise the agent's standard terms from their market profile, labeled "Standard Terms" on the line and marked on page 1 and the deck's net slide. Nothing is built in, in Florida either; with neither, render.py builds no files. Every net that shows brokerage says "Commissions are negotiable and not set by law." |
| Deed transfer tax | The market's rate, payer and name (Florida: documentary stamp tax on the deed, 0.70%, seller pays; Miami-Dade single-family 0.60% by county override) |
| Owner's title insurance | Only where the seller customarily pays. Florida: the promulgated rate tiers; the buyer pays in Miami-Dade, Broward, Sarasota and some others (county overrides) |
| Title company fees | The market's itemized seller fees (Florida: settlement $700, title search $250, municipal lien search $125, recording $70 = $1,145). The note names them. A title company quote for this sale goes in `costs.title_fees`; a standing quote belongs in the agent's market profile |
| HOA estoppel letter | When `costs.hoa` (or `subject.hoa`) is true: the market's fee (Florida $299) |
| Seller credit | Each strategy's `seller_credit` |
| Other | `costs.other`: `[{label, amount}]` (survey, repairs already agreed, a home warranty) |
| Mortgage payoff | `costs.mortgage_payoff`, when the seller gave it: the last row becomes "Estimated Cash at Closing" |

**Missing values.** Outside the built-in market, anything the market profile doesn't have (transfer tax, title, fees) is left out of the table, named in a "Preliminary" note, returned in `warnings`, and the whole report is marked Preliminary (page-1 tag, footer, deck title slide). Ask the agent for the values, or suggest they save them in a market profile, then re-run. Never fill them with Florida's.

**Tax proration.** With `costs.annual_tax` and `costs.expected_closing_date` (or a `closing_date` per pricing option), the table adds the proration line: Florida taxes are paid in arrears, so the seller credits the buyer from January 1 through the day before closing, allowing the 4% early-payment discount; after the seller pays the bill (`costs.current_tax_bill_paid`, usually from November), the buyer credits the seller instead. Without them the table notes the proration isn't included. **Miami-Dade:** give `subject.property_type`; every type but single-family owes the 0.45% surtax.

**Not in the table** (write them in `pricing.net_note`): repairs after inspection, and carrying costs while the home is listed. If the seller is a foreign person, flag FIRPTA withholding and refer them to the title company or a CPA; it isn't computed.

## Buyer payments

The table shows the seller how each list price turns into a typical buyer's monthly payment, and the effect of every $10,000.

- `buyer_payment.rate`: the latest Freddie Mac weekly 30-year average; say which week in `note`.
- `loan_type` (default conventional) and `down_pct` (fraction, default 0.05): mortgage insurance comes from the shared lending estimates.
- Taxes are estimated at each list price: name the taxing `district` and compute.py finds the millage in the market profile (built in for seven Central Florida counties), or give `school_mills` and `total_mills`. `homestead` (default true) applies the market's primary-residence exemptions (Florida: $25,000 off all levies plus the indexed second exemption, $26,411 for 2026, off non-school levies). Without millage, the market's fallback rate is used and flagged; without either, there's no payment table and compute.py says what's missing.
- `insurance_annual` is a placeholder; say so in `note`.
