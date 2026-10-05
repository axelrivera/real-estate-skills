# Offer Plan, Negotiating Points, Price vs. Credit

## The Offer Plan

One opening offer, a target and a walk-away. They're a negotiating plan for this buyer, not a value opinion, so keep them separate from the supported range. **You pick the posture; the script sets the numbers** from it, the range, the median adjusted value and the asking price, so the same comps and the same posture always give the same plan.

### Pick the Posture

`offer_plan.posture` is one of four. compute.py suggests one from the data (`rough.posture` at the comps stage, `offer_plan.posture_suggested` in the full run); keep it, or pick another and say why in `posture_reason` (required then; words only, about this buyer and this home). Left out, the plan uses the suggested one.

| Posture | When | Suggested when |
|---|---|---|
| `leverage` | The seller has reason to negotiate: long on the market, several cuts, a failed contract | A failed contract since the last sale, 2 or more price cuts, or days on market at least twice the market's recent median |
| `standard` | The usual case: open where the comps give firm support | Otherwise |
| `competitive` | A new listing likely to draw other offers | 14 days or fewer on the market, under 3 months of supply |
| `must_win` | The buyer can't lose this house (a lease ending, the one floor plan they want) | Never: it's the buyer's situation, so it's your call, with a reason |

How much the buyer wants the house, their timing and their cash move the posture; the data only suggests it.

### The Numbers, by Rule

Each step is rounded to $1,000 (half up), and none goes above the asking price:

| Posture | Opening | Walk-Away |
|---|---|---|
| `leverage` | Range low minus a quarter of the range's normal width | Median adjusted value |
| `standard` | Range low | Median adjusted value |
| `competitive` | Range middle | Range high |
| `must_win` | Asking, capped at the range high | Range high |

- **Target:** asking times the recent sale-to-original-list ratio, kept between the opening and the walk-away (halfway between them when the export has no ratio). The target range is the target give or take $2,500, inside the same ends.
- **Walk-away** never goes above the range's high from the rule: above the range only through `plan_override`, when the buyer explicitly accepts appraisal-gap risk (say so; the `walk_away_above_range` warning reminds you).
- **Each step's reason** in the report is the script's, from what set it (the range's bottom, the median, asking when it capped the step). Say what is particular to this home in `posture_reason` or `conditions`, never by retyping a number.
- **The agent's own numbers:** `plan_override {opening, target_low, target_high, walk_away, reason}` with only the steps the agent chose. The report marks them as the agent's with the reason; the rest stay the rule's (the target is re-set between the agent's ends). The steps must still run low to high.
- **Credit alternative:** when the buyer is cash-tight, `credit_alt {credit}`: the opening plus that credit, so price minus credit stays the opening. It must match a credit offer. The higher price raises the down payment and closing costs, so it saves less cash than the credit: the script says what it really saves (compute.py's `credit_alt.cash_saved`), never the credit amount as the cash saved.
- **Conditions:** what the plan assumes (the roof, a failed contract's cause, no competing offers…), so the buyer knows which answers would change it.

## The Rough Plan (Gut Check)

Before the report, compute.py's `rough` gives the gut check's numbers, all called rough in the reply:

- **Rough range:** the adjusted comps' span, lowest to highest adjusted value, rounded outward to $1,000.
- **Rough opening, target and walk-away:** the plan above with the suggested posture (`rough.posture`) on the supported range, so the quick answer and the full report agree when the report keeps that posture.

None goes above the asking price (`capped_at_asking` says when asking set the walk-away). The rough plan leaves out the buyer's situation: say so in one line when it could change the posture, and let the full report set the real plan.

## Negotiating Points

2–4 bullets after the ladder, each opening with a bold finding: room to negotiate, credits vs. price, appraisal risk. Frame them as analysis, not orders, and don't repeat the offer numbers.

## Price vs. Seller Credit

2–4 offers with the same price minus credit (the opening offer), split differently between price and a credit toward the buyer's closing costs: `scenarios` lists only each offer's `credit`, and the script prices it at the opening plus that credit. They don't leave the seller exactly the same net: a higher price also raises the seller's percentage costs (listing fee, buyer-broker pay, transfer tax), and the report says so, so never write "the seller nets the same". Left out, `scenarios` is the opening with no credit, then $5,000 and $10,000 of credit.

- `loan_type` and `down_pct` come from the buyer's financing answers. They set the seller-contribution limit: conventional 3% below 10% down, 6% from 10% to under 25%, 9% at 25% or more; FHA and USDA 6%; VA 4% in concessions.
- Use the lender's closing-cost estimate when you have it (`closing_costs`); otherwise compute.py uses the market's share of price plus the taxes on the loan, itemized on the loan amount (Florida: 2.5% of price plus the documentary stamp tax on the note, 0.35%, and the intangible tax, 0.2%; elsewhere the national 3% estimate), and the report labels it. `closing_cost_pct` replaces the share and drops the itemized loan taxes.
- compute.py flags any credit over the program limit or over the closing costs. Fix the scenario rather than leaving the flag: a credit above actual costs is simply lost.
- Optional `buydown`: the same credit spent on a temporary 2-1 rate buydown. The script prices it and says plainly when the credit doesn't cover it.
- `takeaway` explains the trade-off for this buyer in words: cash-tight vs. staying long term. The script says what each $5,000 of credit saves and costs a month.
