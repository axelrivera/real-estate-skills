# FR/BAR Deal File Fields (Florida)

For the FR/BAR AS IS and Standard contracts. Set `"form_family": "frbar"` and `"contract_form": "as_is"` or `"standard"`; the script builds the deadline list from the fields below. What each paragraph, rider and addendum means is in `frbar-contract.md`, `frbar-riders.md` and `frbar-addenda.md`; this file says where each date goes in the deal file. Record `form_revision` as printed in the footer, with `"form_revision_source": "footer"`; a revision you only have from a header, a summary or the agent is recorded as given, without the source. A revision other than the one the rules were checked against adds a chat note to confirm.

## Contents

- Contract Fields
- Rider Fields
  - Short Sales (Rider G)
- Checks Before Running
- Time Rules

## Contract Fields

| Field | Where to Look | Blank = Form Default |
|---|---|---|
| `effective_date`, `effective_date_source` | Para. 3(b): when the last party signed or initialed **and delivered** the final offer or counteroffer. The source cites Para. 3(b) and the signature or initial, also for a counter made on the contract (never the paragraph whose value was changed) | No default (ask) |
| `deposit_days`; `deposit_amount` (number) or `deposit_amount_str` (as written), either one | Para. 2(a) | 3 days |
| `additional_deposit_days`; `additional_deposit_amount` (number) or `additional_deposit_amount_str` (as written), either one | Para. 2(b). The row appears when either amount or the days are given; a blank amount means no additional deposit: leave them all out | 10 days, only when an amount is written |
| `financing`, `loan_application_days`, `loan_approval_days` | Para. 8 | 5 days, 30 days |
| `closing_date`, `closing_time` | Para. 4 (extensions in Para. 5). The form has no closing time; use the one the parties or title company set | No default; time 10:00 AM (agent note) |
| `possession_*` | Para. 6 | At closing |
| `title_by`, `title_evidence_days_before` | Para. 9(c). `title_by` is `"seller"` or `"buyer"`: the party who designates the closing agent and delivers the title evidence (the checkbox has no default: ask). Left out, the row shows the seller and the script adds an agent note | 15 days before closing, or 5 when cash |
| `title_commitment_received` | Date the buyer got the title commitment; starts the 5-day title defect notice (Standard A(ii)) | On event |
| `title_defect_notice` | Date the buyer delivered a title defect notice; starts the seller's 30-day cure period (Standard A(ii)) | On event |
| `survey_days_before`, `survey_received` | Para. 9(d); the buyer's survey defect notice is due 5 days after receipt, no later than closing (Standard B) | 5 days; on event |
| `seller_has_title_evidence` | Para. 9(c): the seller has an owner's title policy or other evidence of title and furnishes a copy within 5 days | No row unless true |
| `seller_has_survey` | Para. 9(d): the seller furnishes an existing survey within 5 days | No row unless true |
| `inspection_days` | Para. 12(a). AS IS: the buyer's right to cancel. Standard: no right to cancel; the deadline for repair, WDO and permit notices. With Rider K or L, the rider's period (15 days if blank) | 15 days |
| `repair_notice_delivered`, `repair_estimates_received`, `open_permits` | Standard only (alone or with Rider L), Para. 12(b)-(d): the seller's estimates are due 10 days after the buyer's notice; the repair-limit election 5 days after the last estimate; open permits closed 5 days before closing | On event; 5 days |
| `repair_limits` | Standard only (alone or with Rider L), Para. 9(a): each limit as written, `{"general": 6000, "wdo": 0.02, "permit": 2500}` (dollars, or a share of the price). Leave a blank limit out. The output's `repair_limits` gives each in dollars; a blank one adds the script's agent note with the amount | 1.5% of the price each |
| `walkthrough_days_before` | AS IS Para. 12(b), Standard Para. 12(e), Rider K Para. 3: the day before closing or closing day | 1 day |
| `flood_zone`, `flood_elevation_days` | Para. 10(d): the buyer may cancel if the home is in a Special Flood Hazard Area (zones starting A or V) below minimum elevation or can't get flood insurance. The row appears only when `flood_zone` starts with A or V or the days are written. Zone unknown: check the seller's flood disclosure (FD-2) or the seller's property disclosure. House (SPDR-4x 3(c), "Is any of the Property located in a special flood hazard area?"): "yes" means record an A zone, "no" means record `"flood_zone": "none"` (or the zone the documents give, such as "X"): the row stays out. Condo (SPDC-2 7(h)) asks about the association's property, not the unit: "no" means `"none"` (the building is association property, so it isn't in the area either); "yes" can mean only a parking lot or other common area, so record an A zone (the buyer's window shows) and add an agent note to confirm the building's zone and elevation (SPDC-2 4(d) on improvements below base flood elevation, 3(e) on lender-required flood insurance, or the elevation certificate). Still unknown: leave `flood_zone` out; the row stays out and the script's agent note asks, with the date the window would end | 20 days |
| `tenants`, `leases_received` | Para. 6(b) checked for a tenant (not for the seller's own stay after closing under Rider U): the seller discloses the lease terms and delivers copies within 5 days; the buyer may cancel within 5 days after receiving them (`leases_received`, pending until then); tenant estoppel letters or a seller's affidavit 10 days before closing (Standard D). With Rider U and no tenant, the script adds an agent note that the 6(b) windows aren't dated | No rows unless true |
| `fincen_report` | Standard I(iii): an entity or trust buyer without institutional financing; both parties give the closing agent the FinCEN information the day before closing | No row unless true |
| `insurance_bound_days_before`, `cd_days_before` | Lender, not the contract | 7 days, 3 business days |
| `riders` | Para. 19: the rider letters or names as printed ("K", "FHA/VA Financing"). The script reads them by letter | No default |

## Rider Fields

Only for riders listed in `riders`. Defaults are each rider's own "if left blank" value; a rider date with no default stays pending until the agent gives it.

| Rider | Fields | Blank = Rider Default |
|---|---|---|
| A Condominium | `condo`, `condo_docs_received`, `condo_docs_before_contract`, `developer_sale`; `rofr`, `rofr_days`; `association_approval` (true; `"unknown"` when the rider's "is / is not required" box is blank: the rows assume it's required, with a Check line and an agent note), `association_apply_days`, `association_approval_days_before` | Rescission 7 business days after receiving the documents (including the milestone summary and SIRS), until closing (s. 718.503). Rider A is the nondeveloper disclosure; a developer sale has a 15-day statutory window (`developer_sale`). ROFR documents 5 days; approval started in 5 days, due 5 days before closing |
| B HOA | `hoa`, `hoa_docs_received`, `hoa_disclosure_before_contract`; approval fields as for A | 3 calendar days after receiving the disclosure summary, until closing, only when it came after signing (s. 720.401) |
| E FHA/VA | `appraisal_received` (the buyer's receipt of the appraisal); `appraisal_repairs_notice_received` (the seller's notice that appraisal repairs exceed the Para. 2 cap), `seller_repair_election_received` | The appraisal protection runs to closing (the script adds a note). The buyer's election to proceed despite a low value is due 3 days after receiving the appraisal (Para. 5, a pending row until then); repairs over the cap: the seller's election 3 days after the notice, then the buyer's 3 days after that (Para. 3(b) or 4(b)) |
| F Appraisal Contingency | `appraisal_date` (the date written in the rider), or `appraisal_days` when a number of days after the Effective Date is written instead. Only with Rider F: set without it, the script adds an agent note (and with Rider E alone, no rows) | Appraisal due 10 days before closing; the buyer's low-appraisal notice 3 days after that date |
| G Short Sale | `short_sale_application_days`, `short_sale_approval_days`, `short_sale_approval_seller_received` (the seller's receipt of the approval), `short_sale_approval_received`, `short_sale_closing_days`, `short_sale_backup` (Para. 7: `"a"` no back-up offers, `"b"` back-ups allowed) | See Short Sales below. Para. 7: (a) if neither box is checked |
| H Homeowner's/Flood Insurance | `insurance_coverage`: which boxes are checked, `"homeowners"` ((a) only: homeowner's coverage including windstorm), `"flood"` ((b) only: NFIP or private flood coverage) or `"both"`. `insurance_date` (the (a) date written in the rider; when days are written instead of a date, `insurance_days`, counted after the Effective Date, or `insurance_days_before` once the agent confirms they count back from closing); `flood_insurance_date` for (b)'s date (with (b) alone, either field) | Each checked box: the earlier of 30 days after the Effective Date or 10 days before closing. One row per checked box; until `insurance_coverage` is recorded, one generic row ("homeowner's, flood, or both as checked") and an agent note asking which. The rider's blank is a date ("by ____"), and its default counts both ways, so days written in don't say which way they count: with `insurance_days`, the script's agent note gives the date counted back from closing too, and the date that is safe for the agent's side |
| I Mold (Standard only) | `mold_days` | 20 days |
| K As Is (Standard only) | `inspection_days` | 15 days; the inspection period becomes a right to cancel and the repair rows drop |
| L Right to Inspect (Standard only) | `inspection_days` | 15 days; a right to cancel plus the repair notices and windows |
| M Defective Drywall | `drywall_days`, `drywall_waived` | 15 days |
| N Coastal Construction Control Line | `cccl_requested` | Affidavit or survey by the Title Evidence Deadline |
| P Lead-Based Paint | `year_built` (always record it: an agent note asks when Rider P is attached without it, or when a home built before 1978 has no Rider P), `lead_paint_days`, `lbp_waived` (box (e) "Waived") | 10 days (the rider sets no start; the Effective Date is the safe reading). The row shows whenever Rider P is attached and not waived |
| R Rezoning | `rezoning_date` | No default (ask) |
| S Lease Purchase/Option | None | Separate agreement signed within 5 days or the contract ends |
| T Pre-Closing Occupancy | `pre_closing_agreement_days`, `possession_date` | Agreement 10 days after the Effective Date (critical: without it either party may cancel) |
| U Post-Closing Occupancy | `post_closing_agreement_days_before`, `seller_occupancy_days` | Agreement 10 days before closing (critical: without it either party may cancel); move-out has no default (ask). Para. 6(b) checked only for the seller's stay isn't a tenancy: leave `tenants` out (the script's agent note says why the 6(b) lease windows aren't dated). Rent and the cost split set no date: no field |
| V Sale of Buyer's Property | `sale_contingency_date` (the date written in the rider) | No default (ask); the buyer may cancel within 3 days after it |
| W Back-Up Contract | `backup_notice_date` | No default (ask). Every Effective Date period restarts on the seller's notice: set `effective_date` to that notice date once it's delivered |
| X Kick-Out | `kickout_notice_received` | The buyer has 3 days after receiving the back-up contract copy |
| Y, Z Attorney Approval | `seller_attorney_date`, `buyer_attorney_date` | No default (ask) |
| DD Seasonal Rentals | `management_agreements_received` | Seller delivers agreements in 5 days; buyer review 5 days after receipt |
| GG Buyer's Broker Compensation | `compensation_agreement_days` | 3 days; the buyer may cancel within 3 days after that. The 3 days count from the Time Period's end as extended past a weekend or holiday; when it rolled, the script adds an agent note with the reading from the unextended day. Its rows show on the report but are never the first deadline (a matter between the brokers) |

### Short Sales (Rider G)

Two phases. **Phase 1**, from the Effective Date: the initial deposit, the seller getting the application forms (Para. 2, 10 days if blank) and returning them completed (5 days after), the seller's copy of an approval it accepts to the buyer and the closing agent (Para. 1, 3 days after the seller receives it; pending until `short_sale_approval_seller_received`), the Short Sale Approval Deadline (Para. 4, 90 days if blank) and the contract expiring 30 days after it. Rider GG stays on the Effective Date too, as its own words say; the script adds an agent note that Para. 5 could be read to move it. **Phase 2**, from the buyer's receipt of the approval (Para. 5): every other period (additional deposit, loan application, inspection, loan approval, seller's termination, appraisal, insurance, rider periods) and the closing, `short_sale_closing_days` after it (Para. 6, 45 if blank).

- Until `short_sale_approval_received` (the date the buyer received the approval) is recorded, Phase 2 rows are pending ("10 days after short sale approval") and never dated from the Effective Date; the PDF and calendar work with the dated rows only. Record it in `contract` (or as an amendment's `changes`) and re-run: the rows get real dates, the approval deadline shows as done and the expiry row drops.
- A closing date written in Para. 4 is replaced by Para. 6 (riders control); the script ignores it and adds an agent note. A closing the parties later agree in writing goes in `date_overrides.closing`.
- The approval deadline is not a buyer contingency: after it either party may cancel, so it never reads as the end of the buyer's protections.

Addenda: an Extension Addendum (EA-4) or any amendment goes in `amendments` (`changes` for fields, `date_overrides` for specific dates). An extension that adds N days to a period: add N to that period's days in `changes` (the safe reading in `frbar-addenda.md`, EA-4); when the original end had rolled past a weekend or holiday, the script adds an agent note with the later reading (the N days added to the rolled end), so don't compute it by hand. The Appraisal Gap (AGA-1), Escalation (EAC-1) and CDD (CDDA-2) addenda set no timeline row of their own beyond what `frbar-addenda.md` lists; add a `deadlines` entry for any date one of them creates.

A term the contract leaves blank takes the default; a term you can't find in the document you were given (a partial copy, a summary) is not a blank: ask for the page or note it as an assumption. Every default you use goes in `agent_notes`, not in `flags`, which print on the client's report, except the ones the script reports itself: the deposit, additional deposit, loan application, loan approval and inspection (or Rider K or L) periods, title evidence, Rider F's appraisal date, Rider H's insurance date, the Standard form's repair limits, the closing time and `title_by` (`deal-file.md`, Script Notes, lists them all). Leave those blanks out of the deal file rather than writing the default in, so the script can say it used one.

## Checks Before Running

- Read `frbar-package-check.md`: riders checked vs. attached, RESERVED riders (I, K, L) on AS IS, K and L together.
- Handwritten changes are initialed by both parties.
- No two documents disagree on a date. If they do, use the latest executed one and flag it.

## Time Rules

Built in for Florida (Standard F of both forms):

- Calendar days, where the property is located; Day 1 is the day after the Effective Date. There is no short-period rule: a 3-day deposit period counts weekends.
- The form sets no time of day: a period runs to the end of its last day.
- Any period or date that ends on a Saturday, Sunday or national legal holiday (5 U.S.C. 6103(a), including observed days) extends to the next business day, including dates counted back from closing and the Closing Date itself. A date counted back from closing therefore moves later, closer to closing; the script adds a Check line with the business day before as the safe date.
- The condominium rescission windows count business days (Rider A). Closing Disclosure: 3 business days before closing (TRID).

Verify these against the form version on the contract. If they differ, put the difference in the deal file's `rules`.
