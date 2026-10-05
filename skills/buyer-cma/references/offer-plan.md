# Offer Plan, Negotiating Points, Price vs. Credit

## The Offer Plan

One opening offer, a target and a walk-away. They're a negotiating plan for this buyer, not a value opinion, so keep them separate from the supported range.

- **Opening:** normally at or near the bottom of the supported range. Go lower only with strong leverage (long time on market, several cuts, vacant, failed contract), and never so low the listing agent won't counter. For a new listing, a home drawing multiple offers, or a buyer who can't lose this house, open near the middle of the range or at asking, and say why.
- **Target:** where the recent sale-to-list ratio and concession data suggest the home settles.
- **Walk-away:** generally at or below the median adjusted comp. Never above the top of the range unless the buyer explicitly accepts appraisal-gap risk, and say so if they do. This number protects first-time buyers from creeping up in a counteroffer.
- **Credit alternative:** when the buyer is cash-tight, a price-plus-credit option with about the same price minus credit as the opening offer. It must match one of the credit scenarios. The higher price raises the down payment and closing costs, so it saves less cash than the credit: the script says what it really saves (compute.py's `credit_alt.cash_saved`), never the credit amount as the cash saved.
- **Conditions:** what the plan assumes (the roof, a failed contract's cause, no competing offers…), so the buyer knows which answers would change it.

## The Rough Plan (Gut Check)

Before there's a supported range, compute.py's `rough` gives the gut check's numbers from the adjusted comps alone, all called rough in the reply:

- **Rough range:** the adjusted comps' span, lowest to highest adjusted value, rounded outward to $1,000.
- **Rough opening:** the median adjusted value minus half the range's normal width (the widest $5,000 step under about 6% of the median: $25,000 at $440,000), rounded down to $1,000. That's the bottom of a typical range centered on the median, where the full plan normally opens.
- **Rough walk-away:** the median adjusted value, rounded down to $1,000 (at or below the median, as above).
- **Rough target:** halfway between the two, to the nearest $1,000.

None goes above the asking price (`capped_at_asking` says when the median is higher). The rough plan leaves out leverage, the market's sale-to-list and the buyer's situation: say so in one line, and let the full report set the real plan.

## Negotiating Points

2–4 bullets after the ladder, each opening with a bold finding: room to negotiate, credits vs. price, appraisal risk. Frame them as analysis, not orders, and don't repeat the offer numbers.

## Price vs. Seller Credit

2–4 offers with about the same price minus credit, split differently between price and a credit toward the buyer's closing costs. They don't leave the seller exactly the same net: a higher price also raises the seller's percentage costs (listing fee, buyer-broker pay, transfer tax), and the report says so, so never write "the seller nets the same". Usually the opening offer with no credit, then +$5,000 and +$10,000 of price with the same added credit.

- `loan_type` and `down_pct` come from the buyer's financing answers. They set the seller-contribution limit: conventional 3% below 10% down, 6% from 10% to under 25%, 9% at 25% or more; FHA and USDA 6%; VA 4% in concessions.
- Use the lender's closing-cost estimate when you have it (`closing_costs`); otherwise compute.py uses the market's share of price plus the taxes on the loan, itemized on the loan amount (Florida: 2.5% of price plus the documentary stamp tax on the note, 0.35%, and the intangible tax, 0.2%; elsewhere the national 3% estimate), and the report labels it. `closing_cost_pct` replaces the share and drops the itemized loan taxes.
- compute.py flags any credit over the program limit or over the closing costs. Fix the scenario rather than leaving the flag: a credit above actual costs is simply lost.
- Optional `buydown`: the same credit spent on a temporary 2-1 rate buydown. The script prices it and says plainly when the credit doesn't cover it.
- `takeaway` explains the trade-off for this buyer in words: cash-tight vs. staying long term. The script says what each $5,000 of credit saves and costs a month.
