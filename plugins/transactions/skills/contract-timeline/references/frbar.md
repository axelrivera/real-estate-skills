# FR/BAR contracts (Florida)

For the FR/BAR AS IS and Standard Residential Contracts. Set `"form_family": "frbar"` and `"contract_form": "as_is"` or `"standard"`; the script builds the deadline list from the fields below. Rules and paragraph numbers follow ASIS-7x Rev. 2/26, the Standard form (FloridaRealtors/FloridaBar-7x Rev. 2/26) and the CR-7 riders (condominium rider CR-7x Rev. 05/2026). Both forms share the time rules, title default and paragraph numbers except Para. 12 (inspection and repair) and 9(a) (repair limits, Standard only). Numbers can shift between versions, so confirm against the form footer.

## Where the dates are

| Field | Where to look | Blank = form default |
|---|---|---|
| `effective_date` | Para. 3(b): when the last party signed or initialed **and delivered** the final offer or counteroffer | No default (ask) |
| `deposit_days`, `deposit_amount_str` | Para. 2(a) | 3 days |
| `additional_deposit_days`, `additional_deposit_amount_str` | Para. 2(b). A blank amount means no additional deposit: leave both out | 10 days, only when an amount is written |
| `financing`, `loan_application_days`, `loan_approval_days` | Para. 8 | 5 days, 30 days |
| `closing_date`, `closing_time` | Para. 4 (extensions in Para. 5). The form has no closing time; use the one the parties or title company set | No default; time 10:00 AM (agent note) |
| `possession_*` | Para. 6 | at closing |
| `title_by`, `title_evidence_days_before` | Para. 9(c) | seller; 15 days before closing, or 5 when cash |
| `title_commitment_received` | Date the buyer got the title commitment; starts the 5-day title defect notice (Standard A(ii)) | On event |
| `survey_days_before`, `survey_received` | Para. 9(d); the buyer's survey defect notice is due 5 days after receipt, no later than closing (Standard B) | 5 days; on event |
| `seller_has_survey` | Para. 9(d): the seller furnishes an existing survey within 5 days | No row unless true |
| `inspection_days` | Para. 12(a). AS IS: the buyer's right to cancel. Standard: no right to cancel; the deadline for repair, WDO and permit notices | 15 days |
| `repair_notice_delivered`, `repair_estimates_received`, `open_permits` | Standard only, Para. 12(b)-(d): the seller's estimates are due 10 days after the buyer's notice; the repair-limit election 5 days after the last estimate; open permits closed 5 days before closing. Repair limits are in Para. 9(a) (1.5% of price each for general repairs, WDO and permits if blank) | On event; 5 days |
| `walkthrough_days_before` | AS IS Para. 12(b), Standard Para. 12(e): the day before closing or closing day | 1 day |
| `riders` | Names of attached riders | No default |
| `appraisal_days` | Appraisal Contingency rider only. The FHA/VA rider has no appraisal period (its protection runs to closing; the script adds a note) | 21 days |
| `insurance_days` | Homeowners'/Flood Insurance rider | = inspection period |
| `sale_contingency_days` | Sale of Buyer's Property rider | 30 days |
| `year_built`, `lead_paint_days`, `lbp_waived` | Pre-1978 homes: Lead-Based Paint rider; no row when the buyer waived the risk assessment | 10 days |
| `flood_zone`, `flood_elevation_days` | Para. 10(d): the buyer may cancel if the home is in a Special Flood Hazard Area (zones starting A or V) below minimum elevation or can't get flood insurance | 20 days |
| `hoa`, `hoa_docs_received`, `hoa_disclosure_before_contract` | HOA rider (CR-7 B), s. 720.401: when the disclosure summary came after signing, the buyer may cancel within 3 days after receiving it, until closing | 3 calendar days after receipt |
| `condo`, `condo_docs_received`, `condo_docs_before_contract`, `developer_sale` | Condominium rider (CR-7x A), s. 718.503: the buyer may cancel within 7 days excluding weekends and holidays after signing and receiving the documents (including the milestone inspection summary and SIRS), until closing; 15 days when the seller is the developer | 7 business days after receipt |
| `association_approval`, `association_apply_days`, `association_approval_days_before` | Condominium / HOA rider: the seller starts approval within 5 days; approval is due 5 days before closing | 5 days; 5 days |
| `insurance_bound_days_before`, `cd_days_before` | Lender, not the contract | 7 days, 3 business days |

A term the contract leaves blank takes the form default; a term you can't find in the document you were given (a partial copy, a summary) is not a blank: ask for the page or note it as an assumption. Every blank you fill with a default goes in `agent_notes` ("Inspection period blank: used the 15-day form default"), not in `flags`, which print on the client's report.

## Checks before running

- Handwritten changes are initialed by both parties.
- No two documents disagree on a date. If they do, use the latest executed one and flag it.
- Riders: the names in `riders` decide which rider deadlines appear. The script matches these words anywhere in a rider's name (any case): `appraisal` (Appraisal Contingency rider), `fha` or `va` (the FHA/VA appraisal note), `insurance` (insurance rider), `association` (HOA), `condominium` (condo), `sale of buyer` (sale contingency). Write the rider names as printed, e.g. "Homeowners' Association", "FHA/VA Financing".

## Time rules (built in for Florida)

- Calendar days, where the property is located; Day 1 is the day after the Effective Date. There is no short-period rule: a 3-day deposit period counts weekends (Standard F).
- The form sets no time of day: a period runs to the end of its last day.
- Any period or date that ends on a Saturday, Sunday or national legal holiday (5 U.S.C. 6103(a), including observed days) extends to the next business day. That includes dates counted back from closing and the Closing Date itself.
- Closing Disclosure: 3 business days before closing (TRID).

Verify these against the form version on the contract. If they differ, put the difference in the deal file's `rules`.
