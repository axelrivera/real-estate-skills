# Offer Plan, Negotiating Points, Price vs. Credit

## The Offer Plan

One opening offer, a target and a walk-away. They're a negotiating plan for this buyer, not a value opinion, so keep them separate from the supported range.

- **Opening:** normally at or near the bottom of the supported range. Go lower only with strong leverage (long time on market, several cuts, vacant, failed contract), and never so low the listing agent won't counter. For a new listing, a home drawing multiple offers, or a buyer who can't lose this house, open near the middle of the range or at asking, and say why.
- **Target:** where the recent sale-to-list ratio and concession data suggest the home settles.
- **Walk-away:** generally at or below the median adjusted comp. Never above the top of the range unless the buyer explicitly accepts appraisal-gap risk, and say so if they do. This number protects first-time buyers from creeping up in a counteroffer.
- **Credit alternative:** when the buyer is cash-tight, a price-plus-credit option with about the same price minus credit as the opening offer. It must match one of the credit scenarios.
- **Conditions:** what the plan assumes (the roof, a failed contract's cause, no competing offers…), so the buyer knows which answers would change it.

## Negotiating Points

2–4 bullets after the ladder, each opening with a bold finding: room to negotiate, credits vs. price, appraisal risk. Frame them as analysis, not orders, and don't repeat the offer numbers.

## Price vs. Seller Credit

2–4 offers with about the same price minus credit, split differently between price and a credit toward the buyer's closing costs. They don't leave the seller exactly the same net: a higher price also raises the seller's percentage costs (listing fee, buyer-broker pay, transfer tax), and the report says so, so never write "the seller nets the same". Usually the opening offer with no credit, then +$5,000 and +$10,000 of price with the same added credit.

- `loan_type` and `down_pct` come from the buyer's financing answers. They set the seller-contribution limit: conventional 3% below 10% down, 6% from 10% to under 25%, 9% at 25% or more; FHA and USDA 6%; VA 4% in concessions.
- Use the lender's closing-cost estimate when you have it (`closing_costs`); otherwise the 3% placeholder, which the report labels.
- compute.py flags any credit over the program limit or over the closing costs. Fix the scenario rather than leaving the flag: a credit above actual costs is simply lost.
- Optional `buydown`: the same credit spent on a temporary 2-1 rate buydown. The script prices it and says plainly when the credit doesn't cover it.
- `after_paragraph` explains the trade-off for this buyer: cash-tight vs. staying long term.
