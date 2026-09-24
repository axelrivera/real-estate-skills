# How Counters Are Proposed

The engine drafts a counter from the rules below. The benchmarks (deposit, concessions, inspection, loan approval) are the market's `offer_norms`, the same ones the Terms Review shows (Florida: 3%, 1.5%, 7 days, 21 days); without them, national planning norms are used (1%, 3%, 10 days, 30 days) and flagged. Each rule adds a row (term, offered, counter, why) only when it applies. The goal is a better net **and** less risk, not simply a higher price. Review the draft for realism before answering.

1. **Price above value with an unfunded appraisal gap** (financed, price > CMA high, gap < price − CMA high) → counter at CMA high. A price the appraisal won't support is a renegotiation waiting to happen. This can lower the paper net, so the report compares the counter with both the as-offered and the downside net; the honest comparison is the downside.
2. **Price below list** → meet partway (rounded up to $1,000). With a CMA and a price under the CMA low, counter at list.
3. **Appraisal gap:** financed (not FHA or VA), and the counter price is above the CMA high → ask the buyer to cover the difference, rounded up to $1,000.
4. **Concessions above the norm** (Florida 1.5% of price) → counter at half.
5. **Buyer-broker pay above what the seller agreed to offer** → counter to the agreed %.
6. **Deposit under the norm** (Florida 3%) → the norm on the counter price for financed offers, at least 5% for cash.
7. **Inspection period over the norm** (Florida 7 days) → the norm, paired with the seller sharing the insurance inspection reports up front (Florida: 4-point and wind-mitigation).
8. **Sale-of-home contingency** → cap at 21 days with a 72-hour kick-out.
9. **Pre-qual or no approval** → full pre-approval within 3 days.
10. **Seller-paid home warranty** → buyer pays. A cheap give-back if the buyer pushes.
11. **Closing after the seller's deadline** → move to the deadline. A weekend date moves to the prior Friday.
12. **Buyer chose title** where the seller customarily pays the owner's policy → seller's title company.

## One Live Contract at a Time

Never recommend two live counters or a backup request while the primary deal isn't fully signed: two acceptances can mean two binding contracts. Offer the backup position only after the primary contract is fully signed, on the Back-Up Contract rider. Two live counters only with a multiple counter-offer form that makes each counter subject to the seller's final acceptance. Telling other buyers' agents about the seller's plans or the competing offers needs the seller's written authorization (NAR Standard of Practice 1-15).

## Appraisal Terms

Appraisal risk starts at the top of the CMA range. A price above it is countered back to it rather than asking for gap money the buyer may not have. FHA and VA offers are never asked for gap coverage: the rider lets the buyer walk if the appraisal is low, so a gap clause shows intent only. A financed offer that waives the appraisal is credited only up to the buyer's documented cash beyond the down payment and closing costs (`gap_funds`).

## Multiple Offers

Only the top-ranked offer gets a counter. The backup is offered a backup position (Back-Up Contract rider) only after the primary contract is fully signed, and gets its own counter only if the first deal falls through. The plan always says only one counter goes out at a time.

## Overrides

Different terms from the agent go in the offer's `counter` object: individual terms, or `rows` to replace the table. The net and the estimated counter certainty recompute from the terms, so check that rows and terms match.
