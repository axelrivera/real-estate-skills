# Costs: The Net Sheet and Buyer Payments

## Net Sheet

compute.py runs each strategy's expected sale price through the shared seller-net calculator. Every local value comes from the home's location, as `local-costs.md` describes: this listing's own numbers in `costs` first, then the built-in Florida layer and its county customs, then national estimates labeled Estimate. The same report works in any state and never uses Florida's numbers elsewhere.

| Line | Where it comes from |
|---|---|
| Listing brokerage, buyer's agent compensation | `costs.listing_fee_pct` / `costs.buyer_broker_fee_pct` in report.json when the agent gave terms (fractions of price: `0.025` means 2.5%; `0` when the seller won't offer buyer's agent compensation). Otherwise 2.5% each (5% total), labeled "Assumed" on the line and marked on page 1 and the deck's net slide. Every net that shows brokerage says "Commissions are negotiable and not set by law." |
| Deed transfer tax | `costs.transfer_tax_rate` (with `transfer_tax_payer` and `transfer_tax_label`) when you looked it up from a trusted source; else the market's rate, payer and name (Florida: documentary stamp tax on the deed, 0.70%, seller pays; Miami-Dade single-family 0.60% by county override); else the national estimate, 0.4%, labeled Estimate |
| Owner's title insurance | Only where the seller customarily pays. Florida: the promulgated rate tiers; the buyer pays in Miami-Dade, Broward, Sarasota and some others (county overrides). Elsewhere 0.5% of price, labeled Estimate, until `costs.title_estimate_pct` or `title_payer` says otherwise |
| Title company fees | The market's itemized seller fees (Florida: settlement $700, title search $250, municipal lien search $125, recording $70 = $1,145). The note names them. Elsewhere $1,200, labeled Estimate. A title company quote for this sale goes in `costs.title_fees` |
| HOA estoppel or association documents | When `costs.hoa` (or `subject.hoa`) is true: the market's fee and name (Florida: HOA Estoppel Letter, $299; elsewhere HOA Documents, an estimate, whatever the state calls them: a resale certificate in Texas). Use the same name in the report's prose |
| Seller credit | Each strategy's `seller_credit` |
| Other | `costs.other`: `[{label, amount}]` (survey, repairs already agreed, a home warranty) |
| Mortgage payoff | `costs.mortgage_payoff`, from the payoff statement or a figure the seller or agent gives (a verbal "about $210,000" goes here too, labeled "Your Estimate"; ask for the statement): the last row becomes "Estimated Cash at Closing". A monthly statement's balance goes in `mortgage_balance` with `mortgage_rate` |

**Estimates.** Outside the built-in market, estimated lines say "Estimate" and a note under the table lists them; `assumptions` names them for your reply. The report isn't marked Preliminary for estimates. When the agent sends a quote or terms, put them in `costs` and render again. A value with no estimate at all (rare) is left out, named in a "Preliminary" note, and marks the report Preliminary.

**Tax proration.** With `costs.annual_tax` and `costs.expected_closing_date` (or a `closing_date` per pricing option), the table adds the proration line, by the one rule in `local-costs.md` (Property Tax at Closing): Florida taxes are paid in arrears, so the seller credits the buyer from January 1 through the day before closing, allowing the 4% early-payment discount. For a closing on or after November 1 the bill is assumed unpaid (the line says so) unless the agent says the seller paid it: then set `costs.current_tax_bill_paid` to true and the buyer credits the seller for the rest of the year instead. Never guess that it's paid. Without a bill or a closing date the table notes the proration isn't included.

**Holding costs.** With each option's `time` (or `months_to_contract`), the table adds holding costs until closing: HOA, insurance, utilities, and loan interest on the payoff at `costs.mortgage_rate` when given, else 4.5% a year, assumed; the note under the table states the rate and the payoff it's on. No payoff given: no loan interest, and the note says so (ask for the payoff when it matters). Property tax is in the proration, never counted twice; when the proration is left out, the note says tax isn't included. **Miami-Dade:** give `subject.property_type`; every type but single-family owes the 0.45% surtax.

**Not in the table** (write them in `pricing.net_note`): repairs after inspection, and any carrying costs the holding-cost rows don't cover. If the seller is a foreign person, flag FIRPTA withholding and refer them to the title company or a CPA; it isn't computed.

## Buyer Payments

The table shows the seller how each list price turns into a typical buyer's monthly payment, and the effect of every $10,000.

- `buyer_payment.rate`: the latest Freddie Mac weekly 30-year average; say which week in `note`.
- `loan_type` (default conventional) and `down_pct` (fraction, default 0.05): mortgage insurance comes from the shared lending estimates.
- Taxes are estimated at each list price: name the taxing `district` (a name, or the property report's `Tax Area` code, such as "01") and compute.py finds the built-in millage (seven Central Florida counties), or give `school_mills` and `total_mills`. `homestead` (default true) applies the market's primary-residence exemptions (Florida: $25,000 off all levies plus the indexed second exemption, $26,411 for 2026, off non-school levies). Without millage, the market's fallback rate is used and flagged (1.1% of price as a national estimate outside Florida).
- `insurance_annual` is a placeholder; say so in `note`.
