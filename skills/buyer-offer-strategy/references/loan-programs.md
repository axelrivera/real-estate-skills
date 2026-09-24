# Loan Program Rules

These apply to whatever financing the buyer and lender chose; the builder never picks the program. They're national agency guidelines as planning estimates: limits and fees change and lenders add overlays, so **the lender's numbers always win**. The same table drives every skill's payment math (shared finance module), so a change is made there, once.

| Program | Min Down | Upfront Fee (Financed) | Annual MI | Seller Concession Cap |
|---|---|---|---|---|
| FHA | 3.5% | 1.75% UFMIP | ~0.55% | 6% of price |
| VA | 0% | Funding fee: 2.15% under 5% down (3.3% on later use), 1.5% at 5%+, 1.25% at 10%+; waived when exempt (`va_later_use`, `va_exempt` in the buyer file) | none | 4% concessions (normal closing costs are separate) |
| USDA | 0% | 1% guarantee fee | 0.35% | 6% |
| Conventional | 3% | none | PMI estimate by down payment: 0.75% under 5%, 0.5% at 5%, 0.35% at 10%, 0.2% at 15%, none from 20% (varies by credit) | 3% under 10% down · 6% from 10% to under 25% · 9% at 25%+ (primary residence) |
| Cash | — | — | — | none |

The monthly payment adds principal and interest (30 years, upfront fee financed), mortgage insurance, property tax on the purchase price (the market's millage and homestead rules, or its fallback rate), homeowner's insurance and HOA dues.

Loan limits (2026, `scripts/_shared/markets/loan-limits.md`): the builder flags a conventional loan above the county's conforming limit (jumbo: different rates and down payment) and an FHA loan above the FHA floor, where the county's limit decides. Also confirm with the lender: credit-score minimums, whether concessions can cover prepaids, and the realistic closing timeline.

The builder never puts concessions above the program cap or above estimated closing costs, since the buyer can't receive the excess, and flags any option that does.

## Why Low-Down FHA/VA/USDA Offers Don't Escalate

A low down payment leaves little cash for a gap, and the appraisal sets the loan amount, so price above value gets cut back. These offers are priced no higher than the value range's midpoint when competition is heavy, and compete on terms and seller net (a clean offer, a strong deposit, a short inspection), not price.
