# Where Offer Fields Live in the Contract

## FAR/BAR Contracts (Florida)

For the Florida Realtors/Florida Bar **AS IS** and **Standard** residential contracts, fully supported. Paragraph numbers are from the verified revisions in `farbar-contract.md`; record the footer in `form_revision`. Read the whole document: riders, addenda and additional terms override the printed paragraphs (Standard R). What each rider does to the seller's net and certainty is in `farbar-riders.md`; addenda (counteroffer, escalation, appraisal gap, CDD, co-op, compensation) are in `farbar-addenda.md`.

| Field | Where to Look |
|---|---|
| `buyer`, `buyer_agent` | Para. 1 (parties); signature page and broker block at the end |
| `price` | Para. 2 (purchase price) |
| `deposit` | Para. 2(a) initial + 2(b) additional deposit, added together. Note the escrow agent and due dates |
| `financing`, `loan_amount` | Para. 2(c) financing amount and Para. 8 (type, LTV / loan amount). Rider E → `fha` / `va`. Para. 8(a) cash checked → `cash` |
| `balance_to_close` | Para. 2(e), the balance due at closing, as the live terms read (a counter that changed the price may have left it unchanged) |
| `loan_approval_days` | Para. 8(b) (30 days when blank) |
| `closing_date` | Para. 4 (Rider G moves it to 45 days after short sale approval) |
| `expires` | Para. 3 (time for acceptance). A counteroffer's own acceptance date; when it's blank and the time runs from delivery ("2 days after delivery") and the delivery date isn't known, count from the signature date and set `expires_estimated: true`. No time on the form: give the date alone (read as the end of that day) |
| `prior_counters` | Earlier counteroffers (CO-3), oldest first, with `by` and the terms each states. When a buyer's counter is live, first the original offer (`by: "buyer"`) with the terms the buyer's counter changed. The live offer's fields are the terms that would govern if signed: a counter carries only what it restates, and anything else stays as in the original offer |
| `occupancy` | Para. 6; Riders T and U |
| `personal_property` | Para. 1 (items included / excluded) |
| `seller_concessions`, `home_warranty` | Para. 9 and additional terms (Para. 20). Seller-paid closing costs are often a dollar amount or % in additional terms. None anywhere in the document: record `0` |
| `title_by` | Para. 9(c): (i) checked → `seller` (the seller designates the Closing Agent and pays the owner's policy); (ii) → `buyer` (the buyer designates and pays it); (iii) Miami-Dade/Broward → `buyer` (the buyer pays the owner's policy; the seller's title search, up to $200 if blank, goes in `listing.costs.title_fees` with the other title charges). The engine charges the owner's policy to that party. No box checked has no default: ask |
| `contract_form` | Read the form's title: "AS IS Residential Contract for Sale and Purchase" is `as_is` (Para. 12: the buyer may cancel for any reason); "Residential Contract for Sale and Purchase" is `standard` (no walk-away; the seller pays repairs up to the repair limits). Never guess: the two run different math. The Florida Realtors CRSP and any non-FAR/BAR form are other contracts (below) |
| `inspection_days` | Para. 12(a) (15 days when blank); with Rider K or L on the Standard form, the rider's period |
| `repair_limits` | Standard only, Para. 9(a): the General Repair, WDO and Permit Limits (1.5% of price each if blank). Rider K deletes them; Rider L keeps them |
| `buyer_broker_pct` | Rider FF (credit to the buyer), Rider GG (separate compensation agreement), or additional terms. Under Rider GG take it only from the signed compensation agreement; without it the review asks for the agreement (the amount) |
| `buyer_broker_paid_by` | Rider GG's signer box (Para. 19): Seller's Broker checked (an agreement between the Seller's Broker and the Buyer's Broker) → always `listing_broker` (the listing broker pays from its own fee under the listing agreement; the review lists it to confirm). Seller checked → leave it out |
| `appraisal_contingency`, `appraisal_gap`, `appraisal_form` | No appraisal rider or addendum on a financed offer: leave `appraisal_contingency` out; Para. 8(b)(2) makes the lender's appraisal part of Loan Approval, and the engine uses the loan approval period. Rider F (appraisal due by its date, 10 days before closing if blank, then 3 days for notice); Rider E (FHA/VA amendatory clause: protection to closing, can't be waived, a gap clause is intent only); the Appraisal Gap Addendum (AGA-1, conventional or cash only: set `appraisal_form: aga`, its Gap Amount in `appraisal_gap` and any filled periods in `aga_valuation_days` / `aga_renegotiate_days`) or additional terms for gap language |
| `gap_funds` | Financed offer that waives the appraisal: the buyer's documented cash beyond the down payment and closing costs (proof of funds). The waiver is credited only up to it |
| `sale_contingency_days`, `kickout` | Rider V (a sale date, no default: count days from the analysis date to that date plus 3) and Rider X |
| `escalation` | Escalation Addendum (EAC-1) or additional terms: `cap`, `increment`, `proof` (EAC-1: a redacted copy of the competing offer), `paid_in_cash` (EAC-1's checked box: (a) cash at closing `true`, (b) financed `false`) and `proof_of_funds` (the amount of a proof of funds attached to the addendum) |
| `rent_back_days`, `rent_back_monthly` | Rider U |
| `seller_financing` | Rider C (note amount) |
| `assessment_payoff` | Rider EE or the CDD addendum, when the seller agrees to pay off the balance |
| `attorney_days` | Rider Z's date, as days from the Effective Date |
| `riders` | Para. 19 checklist: record the letters of every checked and attached rider |
| `addenda` | Para. 19 "Other" and the attached addenda, by name as printed ("Appraisal Gap Addendum (AGA-1)", "Counter Offer (CO-3)") |
| `approval`, `lender` | The separate pre-approval letter or proof of funds: "DU Approve/Eligible", "LP Accept", "conditionally approved", "underwritten" |
| `approval_max_price`, `approval_max_loan` | The pre-approval letter's purchase price and loan amount caps |
| `down_pct` | Leave it out when `loan_amount` is given: the engine derives it from the loan amount and price |

## Other Contracts

Any contract that isn't FAR/BAR is read on a best-effort basis: read `other-contracts.md` for how to find each term by what it does, what to record, and the chat disclaimer. The fields are the same; only where they sit changes. Set `contract_form` to the form's name, never `standard`, and set `inspection_walkaway` from the contract's own words.

## Extraction Tips

- Scanned pages: read them directly.
- Handwritten or initialed changes override typed text. Point out anything illegible instead of guessing.
- Skip buyer letters, photos and personal details (fair housing).
- If the contract and the agent's description disagree, use the contract and point out the difference.
