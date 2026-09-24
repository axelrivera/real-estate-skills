# How the Offers Are Built

"Best offer" = the strongest outlook the buyer can reach **inside their limits** (max price, max payment, cash after the reserve floor, loan program caps), at the lowest cost that gets there. The shared engine scores every option exactly as the listing side would. The agent's `overrides` always win.

## Financing Is an Input

The builder never picks or changes the loan type; every option uses the same financing. Defaults when not given are in `buyer-file.md` and are flagged high.

## Competition Level

From the listing agent's statement when available; otherwise inferred from market heat and flagged. The listing agent's answer is the single most valuable input.

## Recommended Offer: Term Rules

| Term | Rule |
|---|---|
| Price | Anchor = the lower of list and the value point (median adjusted comp, else CMA midpoint). Only offer: ~2% under the anchor, not below CMA low. One competing: the anchor. Two–three: list, kept inside the range (up to CMA high). Cash or 4+: CMA high. Then capped at max price and max payment |
| Seller Concessions | Only offer: full estimated closing costs. One competing: at least half. Two or more: only what the buyer's cash can't cover after the reserve. Always ≤ program cap and ≤ closing costs |
| Appraisal Gap | Financed and price above the CMA high (the same risk line the listing side uses): cover the difference, limited by cash after the reserve. FHA/VA: the rider lets the buyer walk if the appraisal is low, so the clause shows intent; send proof of funds with it |
| Deposit | Financed 1% / 2% / 3% / 3% by competition level; cash 3% / 5% / 10% / 10% |
| Inspection | 10 days; 7 only with heavy competition and a home under ~25 years old |
| Loan Approval | 30 days; 21 for conventional in heavy competition |
| Closing | The lender's fastest reliable close (+10 days with no competition) |
| Home Warranty | Not requested from the seller |
| Buyer-Broker Pay | What the seller offers; otherwise the buyer-broker agreement %, flagged to confirm |
| Escalation | Only with heavy competition and 10%+ down or cash. The cap is the lowest of the max price, the CMA's walk-away, the payment limit, and the price whose gap above the CMA high the buyer can still fund with the reserve intact; the gap clause rises with the price up to that amount. The report says "inside the value range" only when the cap is, and says when the walk-away set the cap. Pre-approval and proof-of-funds amounts are at the cap. Never for low-down FHA/VA/USDA: price above value gets cut back by the appraisal. In a **highest-and-best** round, many listing agents want one flat number: ask the listing agent first, and if escalation isn't welcome, offer the cap as a flat price (it's inside every limit by construction) |

## Alternatives

- **Which one is recommended:** the rule-built offer, unless the stronger option reaches a better outlook against the expected competition while staying inside every limit (price, payment, reserve, program cap). Then the stronger terms become the recommendation. A cheaper option in the same band stays an alternative: the bands can't see above Strong.
- **Stronger:** a 3% deposit, plus gap coverage for the part of the price above the CMA high (never for FHA/VA, where it earns no listing-side credit), never beyond the buyer's actual cash. If it only helps by dipping below the reserve floor, it's labeled the buyer's call; if it doesn't change the outlook, the report says the extra cash isn't worth it. Not offered when the buyer can't afford the recommended offer.
- **Lower-cost:** the same rules one competition level lower, without escalation: what the buyer saves and what happens to the outlook. Dropped when it would be "Unlikely" against the expected competition (level 2+); not offered when competition is already "only offer".

## Outlook Bands

Competitiveness index = strength score + 5 points per 1% of list price the seller nets above a clean offer at list. Thresholds:

| Competition | Strong | Competitive | At Risk |
|---|---|---|---|
| Only Offer | 55 | 40 | 30 |
| One Competing | 65 | 55 | 45 |
| Two–three | 75 | 60 | 50 |
| Cash or 4+ | 85 | 72 | 60 |

Below "At Risk" is "Unlikely". These are starting judgments, not probabilities; tell the agent so when they ask for a percentage.

## Strength Score

The listing side's certainty scorecard, eight criteria weighted to 100: financing 20, approval 10, appraisal risk 20, contingency exposure 15, deposit 10, fit with the seller's timeline 10, property condition / insurance 10, buyer agent track record 5. The report's scorecard shows each option's scores and why.
