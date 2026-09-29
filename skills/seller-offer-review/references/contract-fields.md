# Where Offer Fields Live in the Contract

## FR/BAR Contracts (Florida)

For the Florida Realtors/Florida Bar **AS IS** and **Standard** residential contracts, fully supported. Paragraph numbers are from the verified revisions in `frbar-contract.md`; record the footer in `form_revision`. Read the whole document: riders, addenda and additional terms override the printed paragraphs (Standard R). What each rider does to the seller's net and certainty is in `frbar-riders.md`; addenda (counteroffer, escalation, appraisal gap, CDD, co-op, compensation) are in `frbar-addenda.md`.

| Field | Where to Look |
|---|---|
| `buyer`, `buyer_agent` | Para. 1 (parties); signature page and broker block at the end |
| `price` | Para. 2 (purchase price) |
| `deposit` | Para. 2(a) initial + 2(b) additional deposit, added together. Note the escrow agent and due dates |
| `financing`, `down_pct`, `loan_amount` | Para. 2(c) financing amount and Para. 8 (type, LTV / loan amount). Rider E → `fha` / `va`. Para. 8(a) cash checked → `cash` |
| `loan_approval_days` | Para. 8(b) (30 days when blank) |
| `closing_date` | Para. 4 (Rider G moves it to 45 days after short sale approval) |
| `expires` | Para. 3 (time for acceptance) |
| `occupancy` | Para. 6; Riders T and U |
| `personal_property` | Para. 1 (items included / excluded) |
| `seller_concessions`, `home_warranty`, `title_by` | Para. 9 and additional terms. Seller-paid closing costs are often a dollar amount or % in additional terms. Para. 9(c) (who designates the title agent) has no default: ask |
| `contract_form` | Read the form's title: "AS IS Residential Contract for Sale and Purchase" is `as_is` (Para. 12: the buyer may cancel for any reason); "Residential Contract for Sale and Purchase" is `standard` (no walk-away; the seller pays repairs up to the repair limits). Never guess: the two run different math. The Florida Realtors CRSP and any non-FR/BAR form are other contracts (below) |
| `inspection_days` | Para. 12(a) (15 days when blank); with Rider K or L on the Standard form, the rider's period |
| `repair_limits` | Standard only, Para. 9(a): the General Repair, WDO and Permit Limits (1.5% of price each if blank). Rider K deletes them; Rider L keeps them |
| `buyer_broker_pct` | Rider FF (credit to the buyer), Rider GG (separate compensation agreement), or additional terms. Ask if it's not in the offer |
| `appraisal_contingency`, `appraisal_gap`, `appraisal_form` | Rider F (appraisal due by its date, 10 days before closing if blank, then 3 days for notice); Rider E (FHA/VA amendatory clause: protection to closing, can't be waived, a gap clause is intent only); the Appraisal Gap Addendum (AGA-1, conventional or cash only: set `appraisal_form: aga`, its Gap Amount in `appraisal_gap` and any filled periods in `aga_valuation_days` / `aga_renegotiate_days`) or additional terms for gap language |
| `gap_funds` | Financed offer that waives the appraisal: the buyer's documented cash beyond the down payment and closing costs (proof of funds). The waiver is credited only up to it |
| `sale_contingency_days`, `kickout` | Rider V (a sale date, no default: count days from the analysis date to that date plus 3) and Rider X |
| `escalation` | Escalation Addendum (EAC-1) or additional terms: `cap`, `increment`, and `proof` (EAC-1: a redacted copy of the competing offer) |
| `rent_back_days`, `rent_back_monthly` | Rider U |
| `seller_financing` | Rider C (note amount) |
| `assessment_payoff` | Rider EE or the CDD addendum, when the seller agrees to pay off the balance |
| `attorney_days` | Rider Z's date, as days from the Effective Date |
| `riders` | Para. 19 checklist: record the letters of every checked and attached rider |
| `approval`, `lender` | The separate pre-approval letter or proof of funds: "DU Approve/Eligible", "LP Accept", "conditionally approved", "underwritten" |

## Other Contracts

Any contract that isn't FR/BAR is read on a best-effort basis: read `other-contracts.md` for how to find each term by what it does, what to record, and the chat disclaimer. The fields are the same; only where they sit changes. Set `contract_form` to the form's name, never `standard`, and set `inspection_walkaway` from the contract's own words.

## Extraction Tips

- Scanned pages: read them directly.
- Handwritten or initialed changes override typed text. Point out anything illegible instead of guessing.
- Skip buyer letters, photos and personal details (fair housing).
- If the contract and the agent's description disagree, use the contract and point out the difference.
