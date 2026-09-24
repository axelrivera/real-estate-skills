# Where Offer Fields Live in the Contract

## FR/BAR Contracts (Florida)

For the Florida Realtors/Florida Bar **AS IS** and **Standard** residential contracts. Paragraph numbers can shift between form revisions, so confirm against the form version printed in the footer. Read the whole document: additional terms and riders often override the main paragraphs.

| Field | Where to Look |
|---|---|
| `buyer`, `buyer_agent` | Para. 1 (parties); signature page and broker block at the end |
| `price` | Para. 2 (purchase price) |
| `deposit` | Para. 2(a) initial + 2(b) additional deposit, added together. Note the escrow agent and due dates |
| `financing`, `down_pct` | Para. 2(c) financing amount and Para. 8 (type, LTV / loan amount). FHA/VA rider → `fha` / `va`. "Cash" checked → `cash` |
| `loan_approval_days` | Para. 8(b) (form default when blank) |
| `closing_date` | Para. 4 |
| `expires` | Para. 3 (time for acceptance) |
| `occupancy` | Para. 6 |
| `personal_property` | Para. 1 (items included / excluded) |
| `seller_concessions`, `home_warranty`, `title_by` | Para. 9 and additional terms. Seller-paid closing costs are often a dollar amount or % in additional terms |
| `inspection_days`, `contract_form` | Read the form's title: "AS IS Residential Contract for Sale and Purchase" is `as_is` (Para. 12: the buyer may cancel for any reason); "Residential Contract for Sale and Purchase" is `standard` (no walk-away; the seller pays repairs up to the repair limits). Never guess: the two run different math |
| `repair_limits` | Standard only, Para. 9(a): the General Repair, WDO and Permit Limits (1.5% of price each if blank) |
| `buyer_broker_pct` | Additional terms, a compensation addendum, or the buyer-broker agreement. Ask if it's not in the offer |
| `appraisal_days`, `appraisal_gap` | Appraisal Contingency rider; FHA/VA rider (amendatory clause: protection to closing, can't be waived, a gap clause is intent only); additional terms for gap language |
| `gap_funds` | Financed offer that waives the appraisal: the buyer's documented cash beyond the down payment and closing costs (proof of funds). The waiver is credited only up to it |
| `sale_contingency_days`, `kickout` | Sale of Buyer's Property rider and kick-out clause |
| `escalation` | Escalation addendum or additional terms: `cap`, `increment`, and `proof` (how a competing offer is proven, e.g. "redacted copy") |
| `riders` | Rider checklist near the end |
| `approval`, `lender` | The separate pre-approval letter or proof of funds: "DU Approve/Eligible", "LP Accept", "conditionally approved", "underwritten" |

## Other States' Contracts

The fields are the same everywhere; only where they sit changes. Read the contract's own headings rather than assuming FR/BAR paragraph numbers, and write the paragraph you used in your notes to the agent.

| Field | Usually Found Under |
|---|---|
| `price`, `deposit` | "Purchase price", "Earnest money" (TX, CO, GA), "Initial / additional deposit" |
| `financing`, `down_pct`, `loan_approval_days` | "Financing", "Third party financing addendum" (TX), "Loan contingency" (CA) |
| `inspection_days` | "Option period" (TX, walk-away for a fee), "Due diligence period" (NC, GA), "Inspection contingency" (CA and most others) |
| `appraisal_days`, `appraisal_gap` | "Appraisal contingency", an appraisal addendum, or the financing addendum |
| `closing_date`, `occupancy` | "Closing", "Possession" |
| `seller_concessions`, `home_warranty` | "Settlement / closing costs", "Seller contributions" |
| `title_by` | "Title policy", "Title insurance" (TX: the seller usually furnishes the owner's policy; confirm) |
| `sale_contingency_days`, `kickout` | Sale-of-other-property addendum |

Two cautions outside Florida:

- **Walk-away windows differ.** A Texas option period or North Carolina due-diligence period lets the buyer walk for any reason, like an AS IS inspection period. Put its length in `inspection_days` (it's the walk-away window the timeline and certainty use, not the loan or appraisal dates); leave `contract_form` as the form's name (not `standard`, which means the FR/BAR Standard and its repair limits), and set `inspection_walkaway: false` only when the buyer can cancel just for listed defects.
- **Costs and customs aren't built in.** Look up the state's transfer tax from a trusted source and put it in `listing.costs` (`local-costs.md`); the rest (title, fees) are national estimates, labeled Estimate, until the agent sends a settlement statement or the title company's quote.

## Extraction Tips

- Scanned pages: read them directly.
- Handwritten or initialed changes override typed text. Point out anything illegible instead of guessing.
- Skip buyer letters, photos and personal details (fair housing).
- If the contract and the agent's description disagree, use the contract and point out the difference.
