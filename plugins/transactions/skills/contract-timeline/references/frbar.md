# FR/BAR contracts (Florida)

For the FR/BAR AS IS and Standard Residential Contracts. Set `"form_family": "frbar"` and `"contract_form": "as_is"` or `"standard"`; the script builds the deadline list from the fields below. Paragraph numbers follow the AS IS form and can shift between versions, so confirm against the form footer.

## Where the dates are

| Field | Where to look | Blank = form default |
|---|---|---|
| `effective_date` | Signature blocks and the last initials or date on the final counteroffer | — (ask) |
| `deposit_days`, `deposit_amount_str` | Para. 2(a) | 3 days |
| `additional_deposit_days`, `additional_deposit_amount_str` | Para. 2(b). A blank amount means no additional deposit: leave both out | 10 days, only when an amount is written |
| `financing`, `loan_application_days`, `loan_approval_days` | Para. 8 | 5 days, 30 days |
| `closing_date`, `closing_time` | Para. 4 (extensions in Para. 5). The form has no closing time; use the one the parties or title company set | — ; time 10:00 AM (agent note) |
| `possession_*` | Para. 6 | at closing |
| `title_by`, `title_evidence_days_before`, `survey_days_before` | Para. 9 | seller, 5 days, 5 days |
| `inspection_days` | Para. 12 | 15 days |
| `walkthrough_days_before` | Para. 13 | 1 day |
| `riders` | Names of attached riders | — |
| `appraisal_days` | Appraisal Contingency or FHA/VA rider | 21 days |
| `insurance_days` | Homeowners'/Flood Insurance rider | = inspection period |
| `sale_contingency_days` | Sale of Buyer's Property rider | 30 days |
| `year_built`, `lead_paint_days` | Pre-1978 homes: Lead-Based Paint disclosure | 10 days |
| `hoa`, `condo`, `hoa_docs_received`, `condo_docs_received`, `doc_review_days` | HOA / Condominium riders | 3 days after receipt |
| `insurance_bound_days_before`, `cd_days_before` | Lender, not the contract | 7 days, 3 business days |

A term the contract leaves blank takes the form default; a term you can't find in the document you were given (a partial copy, a summary) is not a blank: ask for the page or note it as an assumption. Every blank you fill with a default goes in `agent_notes` ("Inspection period blank: used the 15-day form default"), not in `flags`, which print on the client's report.

## Checks before running

- Handwritten changes are initialed by both parties.
- No two documents disagree on a date. If they do, use the latest executed one and flag it.
- Riders: the names in `riders` decide which rider deadlines appear. The script matches these words anywhere in a rider's name (any case): `appraisal`, `fha` or `va` (appraisal deadline), `insurance` (insurance rider), `association` (HOA), `condominium` (condo), `sale of buyer` (sale contingency). Write the rider names as printed, e.g. "Homeowners' Association", "FHA/VA Financing".

## Time rules (built in for Florida)

- Calendar days; Day 1 is the day after the Effective Date.
- Periods of 5 days or less skip Saturdays, Sundays and national legal holidays.
- A period ending on a weekend or holiday extends to 5:00 PM the next business day; otherwise it ends at 11:59 PM.
- Dates counted back from closing move earlier when they land on a weekend or holiday (conservative; confirm the contract language).
- Closing Disclosure: 3 business days before closing (TRID).

Verify these against the form version on the contract. If they differ, put the difference in the deal file's `rules`.
