# How the offers are built

"Best offer" = the strongest outlook the buyer can reach **inside their limits** (max price, max payment, cash after the reserve floor, loan program caps), at the lowest cost that gets there. The shared engine scores every option exactly as the listing side would. The agent's `overrides` always win.

## Financing is an input

The builder never picks or changes the loan type; every option uses the same financing. Defaults when not given are in `buyer-file.md` and are flagged high.

## Competition level

From the listing agent's statement when available; otherwise inferred from market heat and flagged. The listing agent's answer is the single most valuable input.

## Recommended offer: term rules

| Term | Rule |
|---|---|
| Price | Anchor = the lower of list and the value point (median adjusted comp, else CMA midpoint). Only offer: ~2% under the anchor, not below CMA low. One competing: the anchor. Two–three: list, kept inside the range (up to CMA high). Cash or 4+: CMA high. Then capped at max price and max payment |
| Seller concessions | Only offer: full estimated closing costs. One competing: at least half. Two or more: only what the buyer's cash can't cover after the reserve. Always ≤ program cap and ≤ closing costs |
| Appraisal gap | Financed and price above the value midpoint: cover the difference, limited by cash after the reserve |
| Deposit | Financed 1% / 2% / 3% / 3% by competition level; cash 3% / 5% / 10% / 10% |
| Inspection | 10 days; 7 only with heavy competition and a home under ~25 years old |
| Loan approval | 30 days; 21 for conventional in heavy competition |
| Closing | The lender's fastest reliable close (+10 days with no competition) |
| Home warranty | Not requested from the seller |
| Buyer-broker pay | What the seller offers; otherwise the buyer-broker agreement %, flagged to confirm |
| Escalation | Only with heavy competition and 10%+ down or cash. The cap stays within CMA high + gap coverage, the max price, the payment limit, and a cash level that keeps the reserve at the cap. Never for low-down FHA/VA/USDA: price above value gets cut back by the appraisal |

## Alternatives

- **Stronger:** adds gap coverage (~0.55% of price) and a 3% deposit, never beyond the buyer's actual cash. If it only helps by dipping below the reserve floor, it's labeled the buyer's call; if it doesn't change the outlook, the report says the extra cash isn't worth it. Not offered when the buyer can't afford the recommended offer.
- **Lower-cost:** the same rules one competition level lower, without escalation: what the buyer saves and what happens to the outlook. Dropped when it would be "Unlikely" against the expected competition (level 2+); not offered when competition is already "only offer".

## Outlook bands

Competitiveness index = strength score + 5 points per 1% of list price the seller nets above a clean offer at list. Thresholds:

| Competition | Strong | Competitive | At risk |
|---|---|---|---|
| Only offer | 55 | 40 | 30 |
| One competing | 65 | 55 | 45 |
| Two–three | 75 | 60 | 50 |
| Cash or 4+ | 85 | 72 | 60 |

Below "At risk" is "Unlikely". These are starting judgments, not probabilities; tell the agent so when they ask for a percentage.

## Strength score

The listing side's certainty scorecard, eight criteria weighted to 100: financing 20, approval 10, appraisal risk 20, contingency exposure 15, deposit 10, fit with the seller's timeline 10, property condition / insurance 10, buyer agent track record 5. The report's scorecard shows each option's scores and why.
