# Certainty Scorecard

The score estimates how likely an offer is to close on its terms. Eight criteria, each scored 1–5, weighted to a 0–100 total: **80+** strong, **60–79** workable, **under 60** weak. Auto-scores come from the contract fields; agent overrides (`scores` in the offer) always win and are marked in the report.

| Criterion | Weight | Auto Rule |
|---|---|---|
| Financing Type & Down Payment | 20 | cash 5 · conv ≥20% 4 · conv ≥5% 3 · conv <5% 2 · VA 3 (the Tidewater process gives notice and a chance to send sales before a low value is final) · FHA/USDA 2. The reason names the loan's terms, never the buyer |
| Approval / Funds Verified | 10 | POF verified or full UW 5 · DU/LP approved 4 · pre-approval 3 · pre-qual 2 · none 1. Financed and lender not called → capped at 3 |
| Appraisal Risk | 20 | cash, or no appraisal contingency on a conventional loan with documented funds, 5. Otherwise exposure = price − (CMA high + gap cover): price ≤ mid 5 · exposure ≤ 0 4 · ≤1% of price 3 · ≤2.5% 2 · more 1. Gap cover is the gap clause, except: FHA and VA 0 (the rider lets the buyer walk if the appraisal is low, so a waiver is ignored and a gap clause is intent only, and the protection runs to closing); a financed waiver, the buyer's documented cash beyond the down payment and closing costs (`gap_funds`) |
| Contingency Exposure | 15 | sale-of-home contingency 1. Otherwise the lower of: days until firm ≤7 5 · ≤14 4 · ≤30 3 · ≤45 2 · more 1; inspection period (the walk-away-for-any-reason window; AS IS and other contracts' option periods only) ≤7 5 · ≤10 4 · ≤14 3 · more 2. Days until firm count the inspection period only when it's a walk-away; on the FR/BAR Standard they run through the repair election (inspection + 10 + 5 days), since either party may terminate when repairs exceed a limit |
| Deposit Strength | 10 | ≥10% 5 · ≥3% 4 · ≥2% 3 · ≥1% 2 · less 1 · unknown 3 |
| Fit with Seller's Timeline | 10 | with a deadline: ≥7 days early 5 · on time 4 · ≤7 days late 2 · later 1. Without: ≤30 days 5 · ≤45 4 · ≤60 3 · more 2 |
| Property-Condition / Insurance Risk | 10 | cash 5. Financed: start at 4; roof ≥14 yrs −1 (≥20 yrs −2); FHA/VA/USDA −1; flood zone A/V −1; buyer has an insurance quote in hand +1 (a planned quote isn't scored) (range 1–5) |
| Buyer Agent Track Record | 5 | strong 5 · average 3 · weak 2 · not assessed 3 |

## Downside Case

The price if the appraisal lands at the CMA high, the top of the supported range (plus the gap cover above), minus the seller's repair cost for the contract's form: on FR/BAR AS IS, the market's typical post-inspection credit (Florida: about 0.7% of price); on the FR/BAR Standard, the General Repair Limit the seller owes (1.5% of price if blank); on another contract, the market's credit only when the agent's market profile sets one for their own contract (never Florida's AS IS figure). Cash offers keep their price. Without a figure, the downside leaves repairs out and says so.

## Ranking (Multiple Offers)

Risk-adjusted value = downside net − (100 − score)/100 × penalty × list price. Penalty by the seller's priority: price 5%, balanced 10%, speed 12%, certainty 15%.

- The top offer gets Accept or Counter. **Accept** when the score is 80+ and either the net is within 1% of the seller's target (a clean offer at list) or the counter would gain less than 0.5% of price: a strong offer isn't worth risking over a small gain. Same test in single mode.
- The second becomes **Backup** if its score is 60+.
- The rest are **Decline**, with a reason.

## When to Override

When the agent knows something the contract doesn't show: the lender call, the buyer agent's reliability, local appraisal behavior, an insurance quote already in hand, a seller who values something unusual. Always write a `why`; it prints in the scorecard.

## Escalation

An escalating offer is scored, netted and ranked at the price it would reach: the lower of its cap and the best competing active offer's base price plus its increment, never below its own base. Escalations don't chain (competing prices are base prices). The report shows "Escalates to $406,000 from $400,000 (cap $425,000)", and flags a missing cap, increment or proof requirement, and a cap above what the value range and gap cover support.
