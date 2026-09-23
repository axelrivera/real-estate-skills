# Seller costs: where each number comes from

Each cost line in the net sheet comes from the first of: the listing file's `costs` block (this deal's quote), the agent's market profile, the built-in state layer (Florida only). The report's fine print names the source of each one ("Florida default", "your market profile", "this listing").

| Line | Florida built-in | Outside Florida without a profile |
|---|---|---|
| Listing brokerage | 2.5% when the listing agreement isn't given | left out, flagged high |
| Buyer-broker pay | offer's %, else the seller's offered %, else 2.5% | offer's or seller's %, else left out |
| Deed transfer tax | documentary stamps 0.70% (Miami-Dade 0.60% on single-family), seller pays | left out, flagged high |
| Owner's title policy | promulgated rate, seller pays in most counties; buyer pays in Miami-Dade, Broward, Sarasota | left out, flagged |
| Title company fees | $1,145 itemized: settlement $700, title search $250, municipal lien search $125, recording $70 | left out, flagged |
| HOA estoppel | $299 (charged when the HOA is unknown or dues > 0) | left out |
| Tax proration | tax bill, else 1.8% of list price; paid in arrears (seller credits Jan 1 → closing) | tax bill only; arrears assumed and flagged |
| Holding costs | tax + insurance 0.7%/yr + HOA + $250 utilities + 4.5% interest on the payoff, per month | tax + HOA + interest; insurance and utilities flagged |
| Inspection credit (downside only) | about 0.7% of price when the buyer has an inspection period | left out, flagged |

## When the agent has better numbers

- **Title company quote:** `listing.costs.title_fees` (one number, or itemized).
- **Different county custom or rate:** `transfer_tax_rate`, `title_payer`.
- **Listing agreement:** `seller.listing_fee_pct`; the seller's offered buyer-broker pay: `seller.offered_buyer_broker_pct`.
- **Recurring values for their market:** suggest saving them in a market profile (the `market-profile` skill does this) so every review uses them.

## Not computed

- **FIRPTA:** if the seller is a foreign person, flag 15% withholding (exceptions apply) and refer to the title company or a CPA.
- **Special assessments, liens, HOA delinquencies:** the title search and estoppel letter decide these.

These are estimates for comparing offers, not a settlement statement. The report says so.
