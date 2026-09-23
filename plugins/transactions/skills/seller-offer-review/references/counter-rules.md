# How counters are proposed

The engine drafts a counter from the rules below. Each rule adds a row (term, offered, counter, why) only when it applies. The goal is a better net **and** less risk, not simply a higher price. Review the draft for realism before answering.

1. **Price above value with an unfunded appraisal gap** (financed, price > CMA high, gap < price − CMA high) → counter at CMA high. A price the appraisal won't support is a renegotiation waiting to happen. This can lower the paper net, so the report compares the counter with both the as-offered and the downside net; the honest comparison is the downside.
2. **Price below list** → meet partway (rounded up to $1,000). With a CMA and a price under the CMA low, counter at list.
3. **Appraisal gap:** financed, and the counter price is above the CMA midpoint → ask the buyer to cover the difference, rounded up to $1,000.
4. **Concessions above 1.5% of price** → counter at half.
5. **Buyer-broker pay above what the seller agreed to offer** → counter to the agreed %.
6. **Deposit under 3%** → 3% of the counter price for financed offers, 5% for cash.
7. **Inspection period over 7 days** → 7 days, paired with the seller sharing the insurance inspection reports up front (Florida: 4-point and wind-mitigation).
8. **Sale-of-home contingency** → cap at 21 days with a 72-hour kick-out.
9. **Pre-qual or no approval** → full pre-approval within 3 days.
10. **Seller-paid home warranty** → buyer pays. A cheap give-back if the buyer pushes.
11. **Closing after the seller's deadline** → move to the deadline. A weekend date moves to the prior Friday.
12. **Buyer chose title** where the seller customarily pays the owner's policy → seller's title company.

## Fallback counter (cash-constrained buyers)

Added when the buyer is FHA, VA or USDA, or putting down less than 10%, and the main counter asks for new gap money. The fallback prices at the CMA midpoint (no gap needed), drops the gap request and splits the difference on concessions. It usually nets less on paper but is more likely to close at that number. Present it as "if the buyer can't fund a gap."

## Multiple offers

Only the top-ranked offer gets a counter. The backup is asked to sign a backup contract and gets its own counter only if the first deal falls through. The plan always says only one counter goes out at a time.

## Overrides

Different terms from the agent go in the offer's `counter` object: individual terms, or `rows` to replace the table. The net and the estimated counter certainty recompute from the terms, so check that rows and terms match.
