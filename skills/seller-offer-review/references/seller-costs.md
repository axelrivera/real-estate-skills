# Seller Costs: Where Each Number Comes From

Each cost line in the net sheet comes from the first of: the listing file (this deal's numbers, including what you looked up), the built-in state layer (Florida only), the national estimates (`local-costs.md`). The report's fine print names the source of each one ("this listing", "Florida default", "national estimate"). Commissions are negotiable and not set by law; without terms, 5% total is assumed.

| Line | Florida Built-In | Outside Florida |
|---|---|---|
| Listing Brokerage | the listing file, else 2.5% assumed (medium) | same |
| Buyer-Broker Pay | offer's % ("Requested"), else the seller's offered %, else 2.5% ("Assumed") | same |
| Deed Transfer Tax | documentary stamps 0.70%, seller pays; Miami-Dade 0.60% plus the 0.45% surtax on every type but single-family (`listing.property_type`) | the state's rate you looked up (`costs.transfer_tax_rate`), else 0.4% national estimate, labeled |
| Owner's Title Policy | promulgated rate, seller pays in most counties; buyer pays in Miami-Dade, Broward, Sarasota and Collier. On a FAR/BAR offer, the Para. 9(c) box (`title_by`) decides: the party who designates the Closing Agent pays, unless `costs.title_payer` is set. No box recorded: local custom, listed as an assumption | 0.5% of price, seller pays, an estimate named in the assumptions |
| Title Company Fees | $1,145 itemized: settlement $700, title search $250, municipal lien search $125, recording $70. On a FAR/BAR offer the 9(c) box decides the searches: (i) `seller`, the seller pays both; (ii) `buyer`, neither; (iii) `buyer_regional`, the title search up to $200 (or `title_search_cap`) plus the lien search. The settlement fee and recording stay the seller's under every box. Without a box, the county's custom: Miami-Dade and Broward (iii), Sarasota and Collier (ii), elsewhere (i) | $1,200, an estimate named in the assumptions |
| HOA Estoppel Letter | $299 (charged only with HOA dues > 0 or a condo; an unknown HOA isn't charged, and the review asks) | HOA Documents, $250, an estimate named in the assumptions |
| Tax Proration | tax bill, else 1.8% of list price (a medium-impact assumption: ask for the bill); paid in arrears, prorated through the day before closing allowing the 4% early-payment discount (FAR/BAR Standard K; the cost notes and the Estimated line say so). Unpaid bill: the seller credits the buyer from Jan 1; from November with no word on the bill, the line reads "Bill Assumed Unpaid". Paid (`listing.current_tax_bill_paid`, asked for November and December closings): the buyer credits the seller to Dec 31 | tax bill, else 1.1% of list price (national estimate); arrears |
| Holding Costs | insurance 0.7%/yr + HOA + $250 utilities + 4.5% interest on the payoff, per month (tax is in the proration, never counted twice) | insurance 0.5%/yr + HOA + $250 utilities + interest (national estimates) |
| Inspection Credit (Downside Only) | 0.7% of price, rounded to the nearest $500, when the buyer has an inspection period | left out, flagged |

## When the Agent Has Better Numbers

- **Title company quote:** `listing.costs.title_fees` (one number, or itemized).
- **Different county custom or rate:** `transfer_tax_rate`, `title_payer`.
- **Listing agreement:** `seller.listing_fee_pct`; the seller's offered buyer-broker pay: `seller.offered_buyer_broker_pct`. When the listing broker pays the buyer's broker from its own fee (Rider GG signed by the Seller's Broker), set the offer's `buyer_broker_paid_by: "listing_broker"` and `listing_fee_pct` to the total fee, so the net doesn't count it twice.

## Not Computed

- **FIRPTA:** if the seller is a foreign person, flag 15% withholding (exceptions apply) and refer to the title company or a CPA.
- **Special assessments, liens, HOA delinquencies:** the title search and estoppel letter decide these.

These are estimates for comparing offers, not a settlement statement. The report says so.
