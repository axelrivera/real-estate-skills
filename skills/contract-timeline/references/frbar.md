# FR/BAR Deal File Fields (Florida)

For the FR/BAR AS IS and Standard contracts. Set `"form_family": "frbar"` and `"contract_form": "as_is"` or `"standard"`; the script builds the deadline list from the fields below. What each paragraph, rider and addendum means is in `frbar-contract.md`, `frbar-riders.md` and `frbar-addenda.md`; this file says where each date goes in the deal file. Record `form_revision` from the footer: a revision other than the one the rules were checked against adds an agent note to confirm.

## Contents

- Contract Fields
- Rider Fields
- Checks Before Running
- Time Rules

## Contract Fields

| Field | Where to Look | Blank = Form Default |
|---|---|---|
| `effective_date` | Para. 3(b): when the last party signed or initialed **and delivered** the final offer or counteroffer | No default (ask) |
| `deposit_days`, `deposit_amount_str` | Para. 2(a) | 3 days |
| `additional_deposit_days`, `additional_deposit_amount_str` | Para. 2(b). A blank amount means no additional deposit: leave both out | 10 days, only when an amount is written |
| `financing`, `loan_application_days`, `loan_approval_days` | Para. 8 | 5 days, 30 days |
| `closing_date`, `closing_time` | Para. 4 (extensions in Para. 5). The form has no closing time; use the one the parties or title company set | No default; time 10:00 AM (agent note) |
| `possession_*` | Para. 6 | At closing |
| `title_by`, `title_evidence_days_before` | Para. 9(c). Who designates the title agent is a checkbox with no default: ask | 15 days before closing, or 5 when cash |
| `title_commitment_received` | Date the buyer got the title commitment; starts the 5-day title defect notice (Standard A(ii)) | On event |
| `title_defect_notice` | Date the buyer delivered a title defect notice; starts the seller's 30-day cure period (Standard A(ii)) | On event |
| `survey_days_before`, `survey_received` | Para. 9(d); the buyer's survey defect notice is due 5 days after receipt, no later than closing (Standard B) | 5 days; on event |
| `seller_has_survey` | Para. 9(d): the seller furnishes an existing survey within 5 days | No row unless true |
| `inspection_days` | Para. 12(a). AS IS: the buyer's right to cancel. Standard: no right to cancel; the deadline for repair, WDO and permit notices. With Rider K or L, the rider's period (15 days if blank) | 15 days |
| `repair_notice_delivered`, `repair_estimates_received`, `open_permits` | Standard only (alone or with Rider L), Para. 12(b)-(d): the seller's estimates are due 10 days after the buyer's notice; the repair-limit election 5 days after the last estimate; open permits closed 5 days before closing | On event; 5 days |
| `walkthrough_days_before` | AS IS Para. 12(b), Standard Para. 12(e), Rider K Para. 3: the day before closing or closing day | 1 day |
| `flood_zone`, `flood_elevation_days` | Para. 10(d): the buyer may cancel if the home is in a Special Flood Hazard Area (zones starting A or V) below minimum elevation or can't get flood insurance | 20 days |
| `tenants` | Para. 6(b) checked (tenant-occupied): tenant estoppel letters or a seller's affidavit 10 days before closing (Standard D) | No row unless true |
| `fincen_report` | Standard I(iii): an entity or trust buyer without institutional financing; both parties give the closing agent the FinCEN information the day before closing | No row unless true |
| `insurance_bound_days_before`, `cd_days_before` | Lender, not the contract | 7 days, 3 business days |
| `riders` | Para. 19: the rider letters or names as printed ("K", "FHA/VA Financing"). The script reads them by letter | No default |

## Rider Fields

Only for riders listed in `riders`. Defaults are each rider's own "if left blank" value; a rider date with no default stays pending until the agent gives it.

| Rider | Fields | Blank = Rider Default |
|---|---|---|
| A Condominium | `condo`, `condo_docs_received`, `condo_docs_before_contract`, `developer_sale`; `rofr`, `rofr_days`; `association_approval`, `association_apply_days`, `association_approval_days_before` | Rescission 7 business days after receiving the documents (including the milestone summary and SIRS), until closing (s. 718.503). Rider A is the nondeveloper disclosure; a developer sale has a 15-day statutory window (`developer_sale`). ROFR documents 5 days; approval started in 5 days, due 5 days before closing |
| B HOA | `hoa`, `hoa_docs_received`, `hoa_disclosure_before_contract`; approval fields as for A | 3 calendar days after receiving the disclosure summary, until closing, only when it came after signing (s. 720.401) |
| E FHA/VA | No period: the appraisal protection runs to closing (the script adds a note) | None |
| F Appraisal Contingency | `appraisal_date` (the date written in the rider) | Appraisal due 10 days before closing; the buyer's low-appraisal notice 3 days after that date |
| G Short Sale | `short_sale_application_days`, `short_sale_approval_days` | Application forms 10 days; approval deadline 90 days after the Effective Date; the contract expires 30 days after that. Most other periods restart when the buyer receives the approval: once it's received, ask the agent for the dates and record them as `date_overrides` |
| H Homeowner's/Flood Insurance | `insurance_date` (the date written in the rider) | The earlier of 30 days after the Effective Date or 10 days before closing |
| I Mold (Standard only) | `mold_days` | 20 days |
| K As Is (Standard only) | `inspection_days` | 15 days; the inspection period becomes a right to cancel and the repair rows drop |
| L Right to Inspect (Standard only) | `inspection_days` | 15 days; a right to cancel plus the repair notices and windows |
| M Defective Drywall | `drywall_days`, `drywall_waived` | 15 days |
| N Coastal Construction Control Line | `cccl_requested` | Affidavit or survey by the Title Evidence Deadline |
| P Lead-Based Paint | `year_built`, `lead_paint_days`, `lbp_waived` | 10 days (the rider sets no start; the Effective Date is the safe reading) |
| R Rezoning | `rezoning_date` | No default (ask) |
| S Lease Purchase/Option | None | Separate agreement signed within 5 days or the contract ends |
| T Pre-Closing Occupancy | `pre_closing_agreement_days`, `possession_date` | Agreement 10 days after the Effective Date |
| U Post-Closing Occupancy | `post_closing_agreement_days_before`, `seller_occupancy_days` | Agreement 10 days before closing; move-out has no default (ask) |
| V Sale of Buyer's Property | `sale_contingency_date` (the date written in the rider) | No default (ask); the buyer may cancel within 3 days after it |
| W Back-Up Contract | `backup_notice_date` | No default (ask). Every Effective Date period restarts on the seller's notice: set `effective_date` to that notice date once it's delivered |
| X Kick-Out | `kickout_notice_received` | The buyer has 3 days after receiving the back-up contract copy |
| Y, Z Attorney Approval | `seller_attorney_date`, `buyer_attorney_date` | No default (ask) |
| DD Seasonal Rentals | `management_agreements_received` | Seller delivers agreements in 5 days; buyer review 5 days after receipt |
| GG Buyer's Broker Compensation | `compensation_agreement_days` | 3 days; the buyer may cancel within 3 days after that |

Addenda: an Extension Addendum (EA-4) or any amendment goes in `amendments` (`changes` for fields, `date_overrides` for specific dates). The Appraisal Gap (AGA-1), Escalation (EAC-1) and CDD (CDDA-2) addenda set no timeline row of their own beyond what `frbar-addenda.md` lists; add a `deadlines` entry for any date one of them creates.

A term the contract leaves blank takes the default; a term you can't find in the document you were given (a partial copy, a summary) is not a blank: ask for the page or note it as an assumption. Every default you use goes in `agent_notes`, not in `flags`, which print on the client's report.

## Checks Before Running

- Read `frbar-package-check.md`: riders checked vs. attached, RESERVED riders (I, K, L) on AS IS, K and L together.
- Handwritten changes are initialed by both parties.
- No two documents disagree on a date. If they do, use the latest executed one and flag it.

## Time Rules

Built in for Florida (Standard F of both forms):

- Calendar days, where the property is located; Day 1 is the day after the Effective Date. There is no short-period rule: a 3-day deposit period counts weekends.
- The form sets no time of day: a period runs to the end of its last day.
- Any period or date that ends on a Saturday, Sunday or national legal holiday (5 U.S.C. 6103(a), including observed days) extends to the next business day, including dates counted back from closing and the Closing Date itself.
- The condominium rescission windows count business days (Rider A). Closing Disclosure: 3 business days before closing (TRID).

Verify these against the form version on the contract. If they differ, put the difference in the deal file's `rules`.
