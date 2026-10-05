# Certainty Scorecard

The score estimates how likely an offer is to close on its terms. Seven criteria, each scored 1–5 by the rules below from facts in the offer, the contract and the property, never from opinion; nobody sets a score by hand. The weights add to 100; when a criterion isn't scored, the total is scaled to 100 over the criteria that were scored: total = round(100 × Σ(weight × score ÷ 5) ÷ Σ scored weights). **80+** strong, **60–79** workable, **under 60** weak.

| Criterion | Weight | Rule |
|---|---|---|
| Financing Type & Down Payment | 20 | cash 5 · conv ≥20% 4 · conv ≥5% 3 · conv <5% 2 · VA 3 (the Tidewater process gives notice and a chance to send sales before a low value is final) · FHA/USDA 2. The reason names the loan's terms, never the buyer |
| Approval / Funds Verified | 10 | POF verified or full UW 5 · DU/LP approved 4 · pre-approval 3 · pre-qual 2 · none 1. Financed and lender not called → capped at 3 |
| Appraisal Risk | 20 | cash without Rider F or AGA-1 (both apply to cash too), or no appraisal contingency on a conventional loan with documented funds, 5. Otherwise exposure = price − (CMA high + gap cover): price ≤ mid 5 · exposure ≤ 0 4 · ≤1% of price 3 · ≤2.5% 2 · more 1. Gap cover is the gap clause, except: FHA and VA 0 (the rider lets the buyer walk if the appraisal is low, so a waiver is ignored and a gap clause is intent only, and the protection runs to closing); a financed waiver, the buyer's documented cash beyond the down payment and closing costs (`gap_funds`) |
| Contingency Exposure | 20 | sale-of-home contingency 1, or 2 with a kick-out clause (Rider X: the seller keeps marketing). Otherwise the lower of: days until firm (the longest of the inspection, loan approval, appraisal and each rider's cancel window: Rider H insurance, I mold, M drywall, S, T and U agreements, DD rental review, GG compensation agreement, Z attorney approval) ≤7 5 · ≤14 4 · ≤30 3 · ≤45 2 · more 1; inspection period (the walk-away-for-any-reason window: AS IS, Standard with Rider K or L, or another contract's walk-away period) ≤7 5 · ≤10 4 · ≤14 3 · more 2. Days until firm count the inspection period only when it's a walk-away; the appraisal window is each form's own (Rider F: 10 days before closing plus 3; AGA-1: 30 + 3 + 3 days if blank, never past closing; FHA/VA: to closing; FAR/BAR with no appraisal rider: the loan approval period, Para. 8(b)), so on a long closing an AGA-1 offer is firm sooner than the same offer on Rider F; on the FAR/BAR Standard (alone or with Rider L) they run through the repair election (inspection + 10 + 5 days), since either party may terminate when repairs exceed a limit |
| Deposit Strength | 10 | ≥10% 5 · ≥3% 4 · ≥2% 3 · ≥1% 2 · less 1 |
| Fit with Seller's Timeline | 10 | with a deadline: ≥7 days early 5 · on time 4 · ≤7 days late 2 · later 1. Without: ≤30 days 5 · ≤45 4 · ≤60 3 · more 2 |
| Property-Condition / Insurance Risk | 10 | cash 5. Financed: start at 4; roof ≥14 yrs −1 (≥20 yrs −2); FHA/VA/USDA −1; flood zone A/V −1; buyer has an insurance quote in hand +1 (a planned quote isn't scored) (range 1–5) |

## Missing Facts

A criterion never scores a stand-in. When the offer leaves out a fact a criterion reads, the engine still uses a stand-in so the net sheet runs (an assumption, listed to confirm), but that criterion isn't scored: the scorecard shows it Not scored with no number, the total is scaled over the rest, and the assumption's note says once which criteria it left out.

| Fact Not Given | Not Scored |
|---|---|
| Financing type | Financing, Appraisal Risk, Property-Condition / Insurance Risk |
| Down payment (conventional) | Financing |
| Approval level | Approval / Funds Verified |
| Escrow deposit | Deposit Strength |
| Closing date | Fit with Seller's Timeline (and Contingency Exposure when the closing caps the windows) |
| Contract form (FAR/BAR market), or whether another contract's inspection period is a walk-away | Contingency Exposure |
| Another contract's inspection or loan approval period, the appraisal terms of a financed offer, a rider's date | Contingency Exposure (the appraisal terms also leave out Appraisal Risk) |

A FAR/BAR form's own blank (15-day inspection period, 30-day loan approval period, Rider F's dates) is a contract term, not a missing fact. A roof year or flood zone the listing doesn't give is no deduction: the property criterion counts the risks that are known.

## Downside Case

The price if the appraisal lands at the CMA high, the top of the supported range (plus the gap cover above), minus the seller's repair cost for the contract's form: on FAR/BAR AS IS, the market's typical post-inspection credit (Florida: 0.7% of price, rounded to the nearest $500); on the FAR/BAR Standard, the General Repair Limit the seller owes (1.5% of price if blank, never rounded above it); on another contract, only a credit the agent gives for this listing (`listing.costs.inspection_credit_reserve_pct`; never Florida's AS IS figure). Cash offers keep their price. Without a figure, the downside leaves repairs out and says so.

## Ranking (Multiple Offers)

Risk-adjusted value = downside net − (100 − score)/100 × penalty × list price. Penalty by the seller's priority: price 5%, balanced 10%, speed 12%, certainty 15%.

- The top offer gets Accept or Counter. **Accept** when the score is 80+ and either the net is within 1% of the seller's target (a clean offer at list) or the counter would gain less than a small share of price: a strong offer isn't worth risking over a small gain. The share follows the seller's priority: certainty 1%, balanced and speed 0.5%, price 0.25%. An offer below 80 is also accepted when no counter rule applies; the report then says so without calling it strong. Same test in single mode.
- The second becomes **Backup** if its score is 60+.
- The rest are **Decline**, with a reason: a sale contingency, a pre-qualification only, or a closing past the seller's deadline; otherwise what ranks it lower. An offer that nets more as offered is declined for being less certain (both scores named) or for a lower downside net, never for "netting less".
- A backup keeps its own price in the plan ("offer a backup position"); its counter is drafted only if the first deal falls through.

## Changing a Score

Correct the fact the score reads: the lender call (`lender_called`), the approval level, the deposit, the dates and periods, an insurance quote in hand (`insurance_quote`), the listing's roof year or flood zone. What no field holds (local appraisal behavior, how responsive the buyer's agent is, what the seller values) goes in the reply as the agent's own read, never into the score. The retired `scores`, `agent_track` and `agent_note` fields stop the run.

## Escalation

An escalating offer is scored, netted and ranked at the price it would reach: the lower of its cap and the best competing active offer's base price plus its increment, never below its own base (a cap at or below the price does nothing, and is flagged). Escalations don't chain (competing prices are base prices). The report shows "Escalates to $406,000 from $400,000 (cap $425,000)", and flags a missing cap, increment or proof requirement, and a cap above what the value range and gap cover support.

## Walk-Away Date

Days until firm are counted from acceptance, since no Effective Date exists yet: the timeline assumes the analysis date is the Effective Date and says so. When the buyer's walk-away for any reason (AS IS, or Rider K or L on the Standard form) ends sooner than the other windows, the report adds that date as a note: after it, the buyer can cancel only under the loan, appraisal or rider terms. The date is always the end of the longest open window, AGA-1's included. On an AGA-1 offer whose appraisal window is the longest, the note gives the date the other windows end: after it the buyer can cancel only if the valuation plus the gap comes in below the price.

## Rider K on the Standard Form

When the agent asks how a Standard + Rider K offer compares with a plain Standard offer, explain both sides from `farbar-riders.md` (K). Run only the offer as written: the plain Standard side is described in words from these points, never from a second listing file or hand math. The reply is a comparison (about 450 words, SKILL.md Deliver), not a quick answer:

- **Rider K firms the deal sooner on condition.** The buyer may cancel for any reason until the inspection period ends (15 days if blank), then takes the property as is. A plain Standard offer has no walk-away, but its repair process runs past the inspection period: the seller's repair estimates (10 days) and the election (5 days), and either party may cancel when repairs exceed a limit. So condition risk ends at day N under Rider K and at about N + 15 on the plain Standard form.
- **The seller owes no repairs.** Rider K deletes the Para. 9(a) repair, WDO and permit limits (blank limits don't matter) and all of Paras. 11 (maintenance, replaced by an as-is maintenance duty) and 12 (inspection and repair, walk-through included); say both, so the downside uses the post-inspection credit estimate, not the General Repair Limit.
- **The score can match.** Days until firm take the longest window; when loan approval (30 days) is longer than both, Rider K and plain Standard score the same. Say so, and point to the walk-away note and the downside net, where they differ.
- **Rider K red flags to name** (the report's risk flags carry the escrow and permit items as a Low `rider_K_terms` flag): the Para. 9(a) 125% escrow (for repairs the seller can't finish before closing) isn't deleted and may not cover the as-is maintenance duty (ask); with Rider E (FHA/VA), its appraisal repair cap still binds the seller; there's no permit cooperation clause like the AS IS form's Para. 12(c); other riders' inspection clocks (M, P) still run; the buyer pays lender-required repairs, which can stall an FHA or VA loan; Rider K on the AS IS form is RESERVED (the review stops).
