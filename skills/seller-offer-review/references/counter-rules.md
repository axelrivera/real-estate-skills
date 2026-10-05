# How Counters Are Proposed

The engine drafts a counter from the rules below. The benchmarks (deposit, concessions, inspection, loan approval) are the market's `offer_norms`, the same ones the Terms Review shows (Florida: 3%, 1.5%, 7 days, 21 days); without them, national planning norms are used (1%, 3%, 10 days, 30 days) and flagged. Each rule adds a row (term, offered, counter, why) only when it applies. The goal is a better net **and** less risk, not simply a higher price. Review the draft for realism before answering.

1. **Price above value with an unfunded appraisal gap** (an appraisal contingency, price > CMA high, gap < price − CMA high) → counter at CMA high. A price the appraisal won't support is a renegotiation waiting to happen. This can lower the paper net, so the report compares the counter with both the as-offered and the downside net; the honest comparison is the downside. **Only with a CMA:** without one, list price only stands in for the value, so the price is never countered down; rule 3 asks for gap coverage and the row says a CMA would firm up the value.
2. **Price below list** → meet partway (rounded up to $1,000). With a CMA and a price under the CMA low, counter at list.
3. **Appraisal gap:** an appraisal contingency (not FHA or VA, whose rider lets the buyer walk), and the counter price is above the CMA high (list price without a CMA) → ask the buyer to cover the difference, rounded up to $1,000.
4. **Concessions above the norm** (Florida 1.5% of price) → counter at half.
5. **Buyer-broker pay above what the seller agreed to offer** → counter to the agreed %.
6. **Deposit under the norm** (Florida 3%) → the norm on the counter price for financed offers, at least 5% for cash.
7. **Inspection period over the norm** (Florida 7 days) → the norm. The row offers the seller's insurance inspection reports up front (Florida: 4-point and wind-mitigation) only when the listing file says the seller has them (`listing.insurance_reports`); never promise reports the buyer is ordering. Only when the offer states the period: an assumed one (the form's blank default) gets no row; a Low flag asks the agent to confirm the days instead. The counter never changes a term nobody gave.
8. **Sale-of-home contingency** → cap at 21 days with a 72-hour kick-out.
9. **Pre-qual or no approval** → full pre-approval within 3 days. **Counter price above the pre-approval letter's cap** (`approval_max_price`) → an updated letter at the counter price within 3 days.
10. **Seller-paid home warranty** → buyer pays. A cheap give-back if the buyer pushes.
11. **Closing after the seller's deadline** → move to the deadline. A weekend date moves to the prior Friday.
12. **Buyer chose title** where the seller customarily pays the owner's policy → seller's title company. Not on FAR/BAR: under Para. 9(c) the buyer who designates the Closing Agent also pays the owner's policy, so the seller is better off as offered.
13. **AGA-1 periods running to or past closing** (the `aga_window_at_closing` or `aga_window_past_closing` flag) → a valuation period that ends them with loan approval on a financed offer, else before closing: the row the flag's fix names, so the counter and the flag agree. A blank valuation period is the form's 30 days, so the row shows "30 days (blank)".
14. **Time for Acceptance** → every counter (and the reference counter for a lapsed offer) sets one: two days after the review, on a weekday, 5:00 PM; when that is the offer's own deadline exactly, the next weekday, so the row never reads as no change. Change it to what the seller wants.

## Negotiation History

When the seller has already countered (`prior_counters`), the draft builds on the seller's last counter instead of starting over:

- **Price** never goes above the seller's last counter price, which is the ceiling even when it's above list. Below it, meet partway between the offer and that price (rounded up to $1,000, never above it). An offer above it with an unfunded gap is countered back to the seller's last price, never below it (rule 1 doesn't cut under the seller's own counter); rule 3 asks for gap coverage above the value range.
- **Terms the seller already asked for** (inspection and loan approval days, deposit, concessions, gap coverage, closing date) are restated as the seller last countered them when the offer is weaker, with the why "Restates the seller's last counter". The draft doesn't go back to a harder ask than the seller's last counter: that retracts a concession and stalls the deal. Terms the offer already meets get no row.
- If the agent's own counter goes above the seller's last price or asks for less than the seller's last terms, its rows read "Set by the seller": say why in chat.

A buyer's counter that drops a term the seller countered (under FAR/BAR CO-3 only what a counter restates carries) is raised as a High issue (`counter_chain`), and the draft restates the term.

A term the buyer's counter changed that no seller counter addressed (`buyer_changes`, a later closing date) gets its own row: "accept it, or restate" the earlier term, so the seller decides it instead of accepting it silently; the net assumes it's accepted. When the loan amount and balance to close still add up to an earlier price (`loan_amount`), the draft has a row restating them at the counter price.

## One Live Contract at a Time

Never recommend two live counters or a backup request while the primary deal isn't fully signed: two acceptances can mean two binding contracts. Offer the backup position only after the primary contract is fully signed, on the Back-Up Contract Rider (W). Two live counters only with a multiple counter-offer form that makes each counter subject to the seller's final acceptance. Telling other buyers' agents about the seller's plans or the competing offers needs the seller's written authorization (NAR Standard of Practice 1-15).

## Appraisal Terms

Appraisal risk starts at the top of the CMA range. With a CMA, a price above it is countered back to it rather than asking for gap money the buyer may not have; without one, the price stands and the counter asks for gap coverage. FHA and VA offers are never asked for gap coverage: the rider lets the buyer walk if the appraisal is low, so a gap clause shows intent only. A financed offer that waives the appraisal is credited only up to the buyer's documented cash beyond the down payment and closing costs (`gap_funds`).

## Multiple Offers

Only the top-ranked offer gets a counter. The backup is offered a backup position (Back-Up Contract Rider (W)) only after the primary contract is fully signed, and gets its own counter only if the first deal falls through. The plan always says only one counter or acceptance goes out at a time, an acceptance plan too.

A backup whose own time for acceptance ends before the counter to the top offer does would lapse before it can be used. The engine flags it (`backup_lapses`), shows its deadline under Respond By, and the plan's first step is to ask its agent to extend the time for acceptance past the counter's (or to answer it first). With a call for highest and best already out (`listing.highest_and_best_due`), nothing goes out before its deadline: the review is run again on the final offers, and another call isn't offered.

## Overrides

Different terms from the agent go in the offer's `counter.changes` (term → value; the terms are in `listing-file.md`, Agent Overrides). The engine writes every row from them, so the table, the net, the estimated counter certainty and the plan always agree: a term set to the offer's own value drops its row, and terms that follow the price (gap coverage, the deposit norm, the updated pre-approval) follow the agent's price. Never write rows by hand; a `rows` table stops the render.
