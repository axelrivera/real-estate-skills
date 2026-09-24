# Costs: The Net Sheet and Buyer Payments

## Net Sheet

compute.py runs each strategy's expected sale price through the shared seller-net calculator. Every local value comes from the home's location, as `local-costs.md` describes: this listing's own numbers in `costs` first, then the built-in Florida layer and its county customs, then national estimates labeled Estimate. The same report works in any state and never uses Florida's numbers elsewhere.

| Line | Where it comes from |
|---|---|
| Listing brokerage, buyer's agent compensation | `costs.listing_fee_pct` / `costs.buyer_broker_fee_pct` in report.json when the agent gave terms (fractions of price: `0.025` means 2.5%; `0` when the seller won't offer buyer's agent compensation). Otherwise 2.5% each (5% total), labeled "Assumed" on the line and marked on page 1 and the deck's net slide. Every net that shows brokerage says "Commissions are negotiable and not set by law." |
| Deed transfer tax | `costs.transfer_tax_rate` (with `transfer_tax_payer` and `transfer_tax_label`) when you looked it up from a trusted source; else the market's rate, payer and name (Florida: documentary stamp tax on the deed, 0.70%, seller pays; Miami-Dade single-family 0.60% by county override); else the national estimate, 0.4%, labeled Estimate |
| Owner's title insurance | Only where the seller customarily pays. Florida: the promulgated rate tiers; the buyer pays in Miami-Dade, Broward, Sarasota and some others (county overrides). Elsewhere 0.5% of price, labeled Estimate, until `costs.title_estimate_pct` or `title_payer` says otherwise |
| Title company fees | The market's itemized seller fees (Florida: settlement $700, title search $250, municipal lien search $125, recording $70 = $1,145). The note names them. Elsewhere $1,200, labeled Estimate. A title company quote for this sale goes in `costs.title_fees` |
| HOA estoppel letter | When `costs.hoa` (or `subject.hoa`) is true: the market's fee (Florida $299) |
| Seller credit | Each strategy's `seller_credit` |
| Other | `costs.other`: `[{label, amount}]` (survey, repairs already agreed, a home warranty) |
| Mortgage payoff | `costs.mortgage_payoff`, when the seller gave it: the last row becomes "Estimated Cash at Closing" |

**Estimates.** Outside the built-in market, estimated lines say "Estimate" and a note under the table lists them; `assumptions` names them for your reply. The report isn't marked Preliminary for estimates. When the agent sends a quote or terms, put them in `costs` and render again. A value with no estimate at all (rare) is left out, named in a "Preliminary" note, and marks the report Preliminary.

**Tax proration.** With `costs.annual_tax` and `costs.expected_closing_date` (or a `closing_date` per pricing option), the table adds the proration line: Florida taxes are paid in arrears, so the seller credits the buyer from January 1 through the day before closing, allowing the 4% early-payment discount; after the seller pays the bill (`costs.current_tax_bill_paid`, usually from November), the buyer credits the seller instead. Without them the table notes the proration isn't included. **Miami-Dade:** give `subject.property_type`; every type but single-family owes the 0.45% surtax.

**Not in the table** (write them in `pricing.net_note`): repairs after inspection, and carrying costs while the home is listed. If the seller is a foreign person, flag FIRPTA withholding and refer them to the title company or a CPA; it isn't computed.

## Buyer Payments

The table shows the seller how each list price turns into a typical buyer's monthly payment, and the effect of every $10,000.

- `buyer_payment.rate`: the latest Freddie Mac weekly 30-year average; say which week in `note`.
- `loan_type` (default conventional) and `down_pct` (fraction, default 0.05): mortgage insurance comes from the shared lending estimates.
- Taxes are estimated at each list price: name the taxing `district` and compute.py finds the built-in millage (seven Central Florida counties), or give `school_mills` and `total_mills`. `homestead` (default true) applies the market's primary-residence exemptions (Florida: $25,000 off all levies plus the indexed second exemption, $26,411 for 2026, off non-school levies). Without millage, the market's fallback rate is used and flagged (1.1% of price as a national estimate outside Florida).
- `insurance_annual` is a placeholder; say so in `note`.
