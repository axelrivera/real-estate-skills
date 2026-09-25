# Seller Costs: Where Each Number Comes From

Each cost line in the net sheet comes from the first of: the listing file (this deal's numbers, including what you looked up), the built-in state layer (Florida only), the national estimates (`local-costs.md`). The report's fine print names the source of each one ("this listing", "Florida default", "national estimate"). Commissions are negotiable and not set by law; without terms, 5% total is assumed.

| Line | Florida Built-In | Outside Florida |
|---|---|---|
| Listing Brokerage | the listing file, else 2.5% assumed (medium) | same |
| Buyer-Broker Pay | offer's % ("Requested"), else the seller's offered %, else 2.5% ("Assumed") | same |
| Deed Transfer Tax | documentary stamps 0.70%, seller pays; Miami-Dade 0.60% plus the 0.45% surtax on every type but single-family (`listing.property_type`) | the state's rate you looked up (`costs.transfer_tax_rate`), else 0.4% national estimate, labeled |
| Owner's Title Policy | promulgated rate, seller pays in most counties; buyer pays in Miami-Dade, Broward, Sarasota and Collier | 0.5% of price, seller pays, labeled Estimate |
| Title Company Fees | $1,145 itemized: settlement $700, title search $250, municipal lien search $125, recording $70. Miami-Dade and Broward (FR/BAR 9(c)(iii)): title search capped at $200. Sarasota and Collier (9(c)(ii)): the buyer pays the title and lien searches | $1,200, labeled Estimate |
| HOA Estoppel | $299 (charged when the HOA is unknown or dues > 0) | $250, labeled Estimate |
| Tax Proration | tax bill, else 1.8% of list price; paid in arrears, prorated through the day before closing allowing the 4% early-payment discount (FR/BAR Standard K). Unpaid bill: the seller credits the buyer from Jan 1. Paid (`listing.current_tax_bill_paid`, asked for November and December closings): the buyer credits the seller to Dec 31 | tax bill, else 1.1% of list price (national estimate); arrears |
| Holding Costs | insurance 0.7%/yr + HOA + $250 utilities + 4.5% interest on the payoff, per month (tax is in the proration, never counted twice) | insurance 0.5%/yr + HOA + $250 utilities + interest (national estimates) |
| Inspection Credit (Downside Only) | about 0.7% of price when the buyer has an inspection period | left out, flagged |

## When the Agent Has Better Numbers

- **Title company quote:** `listing.costs.title_fees` (one number, or itemized).
- **Different county custom or rate:** `transfer_tax_rate`, `title_payer`.
- **Listing agreement:** `seller.listing_fee_pct`; the seller's offered buyer-broker pay: `seller.offered_buyer_broker_pct`.

## Not Computed

- **FIRPTA:** if the seller is a foreign person, flag 15% withholding (exceptions apply) and refer to the title company or a CPA.
- **Special assessments, liens, HOA delinquencies:** the title search and estoppel letter decide these.

These are estimates for comparing offers, not a settlement statement. The report says so.
