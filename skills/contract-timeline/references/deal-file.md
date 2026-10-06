# Deal File

The JSON record of an executed contract. `scripts/timeline.py` computes the dates from it and `scripts/render.py` builds the PDF. It's a working file in the temporary folder, never handed to the agent (`saved-files.md`). Within a conversation, amendments are added to it; in a later one, rebuild it from the executed package and add each amendment to `amendments` in signing order.

```json
{
  "side": "buyer",
  "client": "Name on the report",
  "state": "FL",
  "county": "Seminole",
  "contract": { },
  "deadlines": [ ],
  "amendments": [ ],
  "completed": {"deposit": "2026-09-26"},
  "report_date": "2026-09-26",
  "agent_notes": ["for the agent only: defaults used, readings to confirm; never printed"],
  "rules": { }
}
```

`time_zone` (optional: `ET`, `CT`, `MT`, `MST` for Arizona, `PT`, `AKT`, `HT`, `AT`, or an IANA name such as `America/Chicago`). Left out, the script uses the state's zone, and the county's where a state spans two (Florida's western Panhandle is Central time and prints "CT" after each time); when the county doesn't settle it (Gulf County, Florida, or a county the script doesn't list), it uses the zone most of the state uses and an agent note asks to confirm it. Set it when the agent confirms. The calendar's timed events always carry the zone. `state` (required: ask for it, never assume Florida) and `county` pick the market's time rules (built in for Florida). Those rules cover only the market's own forms (in Florida, FAR/BAR AS IS and Standard); any other contract, such as a builder's form, takes its time rules from its own definitions in `rules`. `rules` also overrides the market's rules for this contract (see below).

`completed` (optional): deadlines already met, by deadline key (the keys in the script output), with the date each was done. An escrow receipt in the package is the deposit done. Done is for something performed (a deposit, a document signed and delivered), never for the end of a contingency or cancel window (a row with `contingency`): that stays open until its date, and the script refuses a done date before it. The one window the script closes itself: a signed compensation agreement is `compensation_agreement` done (the date it was signed; set `contract.compensation_agreement_delivered: true` only when the package or the agent shows it delivered, and the row's note then says "signed and delivered", else "signed"), and since Rider GG's cancel right arises only if the agreement isn't signed, Compensation Contingency Ends then shows done too (`voided`), without its star, off page 1 and the calendar, and stays in the Deadline Details table with the reason. The one exception is a window ended early in writing (a signed waiver, written loan approval delivered to the seller): list its key in `ended_in_writing` (optional list) and its `completed` date is accepted. A done row shows "Done Sep 26" on the report and in the output (`done`, `done_display`), never counts as the first deadline, and gets no calendar event. `report_date` (optional, `YYYY-MM-DD`): the report's Prepared date, the system date if left out. When the agent states today's date ("Today is September 26"), set it to that date. A deadline before it that isn't in `completed` shows "Past, Confirm" (`past`, `past_display`), is never the first deadline and gets no calendar event; the script lists it in an agent note.

`what_if` (optional): `true` for a hypothetical timeline (a future Effective Date the agent didn't call executed), a quick question included. The PDF and the calendar say What-If, and the script leaves out its note asking to confirm the Effective Date. `sample` is for the plugin's own samples (prints SAMPLE DATA); leave it out. A deal file the agent uploads is the working file: if it has `"sample": true`, render it anyway (SAMPLE DATA shows) and ask in the same reply whether it's a real deal; for a real one, remove the flag and re-render.

`agent_notes` go only to the agent in chat; nothing you write prints as a note on the PDF. Its "Check:" lines come only from the script's own keys, in the script's words (the output's `flags`), so a sentence on the client's report never states a date the timeline doesn't compute. A deal file from an earlier version may still carry `flags`: each becomes an agent note (dropped when keyed to a Check line the script raised). An agent note is a string, or `{"key": "...", "text": "..."}`. Notes are matched by key, never by wording: keyed to a script note or Check line (`money_mismatch`, `default:title`, from `note_keys` or `flag_keys`), or to a deadline a script note is wholly about (a blank rider date, an extension reading), the script keeps its own note and drops yours (listed in `merged_agent_notes`). Keyed to a row, your note merges with the row: one line that starts with the row's label and date ("Buyer's Broker Compensation Agreement Signed (Mon Sep 28): ..."), listed in `joined_agent_notes`; pass that line on as the question about that date, and don't add the date again. Without a key it's passed on as written (the same words twice are said once).

## contract

| Field | Notes |
|---|---|
| `form_family` | `farbar` for FAR/BAR AS IS or Standard; anything else is treated as another contract |
| `form` | Form name as printed, for other contracts ("Sample Residential Purchase Agreement") |
| `form_revision`, `form_revision_source` | FAR/BAR: the revision as printed ("FloridaRealtors/FloridaBar-ASIS-7x Rev. 2/26"). `form_revision_source`: `"footer"` when you read it from the form's footer; leave it out when it came from anywhere else (a header, a summary, the agent), and record the revision as given, never made into a footer string. A revision other than the verified one adds a chat note, quoting "the footer reads" only for `"footer"` |
| `effective_date` | **Required.** `YYYY-MM-DD`. The date the last party signed or initialed and delivered the final counter or acceptance |
| `effective_date_source` | The evidence: whose signature or initials on which document ("Second seller's signature on the acceptance", "Buyer's initials on Counteroffer #2"), with no date or time in it (the script refuses a figure, a document's own number aside). It prints on the client's report: never name the e-signature platform (the script drops a name such as Dotloop or DocuSign) |
| `effective_date_signed` | Optional: that signature's or initials' stamp, `YYYY-MM-DD HH:MM` (with two or more signers, the last one's, never the first). The report prints it after the source. It can't be after `effective_date` (a later delivery makes it earlier) |
| `effective_date_delivered` | Optional: `false` when the package shows signing times but no delivery (the script's agent note asks for the delivery date, so don't write your own); `true` when the delivery is shown or the agent confirmed it. Leave it out for a contract whose Effective Date is the last signature alone |
| `acceptance_deadline` | Optional, `YYYY-MM-DD HH:MM` (or the date alone): the time for acceptance as written (FAR/BAR Para. 3(a); for a counteroffer, its own time or 2 days after the day it was delivered). With `effective_date_delivered: false` and the last signature on that day or later, the delivery note names it and asks the agent to confirm delivery; don't write your own |
| `blanks` | Optional list of contract fields seen blank on the signed copy (`["title_evidence_days_before"]`). A form default then reads "blank" in its agent note; a field left out of the deal file but not listed here reads "not given" (a partial copy or text extract may simply not show it). Accepted names: every period and rider date `farbar.md` lists with an "if left blank" default or as a blank (`deposit_days`, `additional_deposit_days`, `loan_application_days`, `loan_approval_days`, `inspection_days`, `title_evidence_days_before`, `flood_elevation_days`, `appraisal_date`, `appraisal_days`, `insurance_date`, `flood_insurance_date`, `association_apply_days`, `association_approval_days_before`, `rofr_days`, `mold_days`, `drywall_days`, `short_sale_application_days`, `short_sale_approval_days`, `short_sale_closing_days`, `pre_closing_agreement_days`, `post_closing_agreement_days_before`, `seller_occupancy_days`, `compensation_agreement_days`, `sale_contingency_date`, `backup_notice_date`, `rezoning_date`, `seller_attorney_date`, `buyer_attorney_date`). Any other name adds a warning (`blanks_unknown`): fix it or remove it. Terms the forms print as fixed (the survey's 5 days, the walk-through, Rider P's 10 days) are never blanks. Blank repair limits are recorded in `repair_limits` (`farbar.md`) |
| `closing_date`, `closing_time` | Date (needed for the report and for dates counted back from closing; a quick question can go without); time `HH:MM`. Leave the time out when the contract doesn't state one: 10:00 AM is used and an agent note says so. With a short sale rider (FAR/BAR Rider G) the closing counts from the approval instead (`farbar.md`) |
| `closing_source`, `possession_source` | Optional: the paragraph cited for the closing and possession rows, when it isn't Para. 4 / Para. 6 (FAR/BAR) or "Contract" |
| `closing_if_missed`, `possession_if_missed` | Other contracts only: what the contract says happens if closing or possession is missed, in its words. Left out, the cell stays empty (FAR/BAR rows carry the form's own wording) |
| `occupancy` | Optional: `owner`, `vacant` or `tenant`, who occupies the home now (the seller's disclosure or the listing). With Rider U, `owner` or `vacant` settles that Para. 6(b) wasn't checked for a tenant, so no note asks |
| `year_built`, `built_before_1978` | The year built; when the documents answer only "built before 1978?" without a year, `built_before_1978` (`true` or `false`) instead. Either one drives the Rider P checks; the two can't disagree |
| `property`, `buyer`, `seller`, `price`, `escrow_agent` | For the report. `price` is a number (412000) |
| `deposit_amount`, `additional_deposit_amount`, `loan_amount`, `other_amount`, `balance_to_close` | Optional, numbers: Para. 2 (FAR/BAR) or the contract's price breakdown, from the last counteroffer or amendment. Each deposit can be given as the number or as the words written (`deposit_amount_str` / `additional_deposit_amount_str`, "$11,000"), either one: the deposit rows and the money check use whichever is there (with both, the rows quote the words and the money check uses the number). With every part known, an agent note when they don't add up to `price`; without the balance, when the known parts pass it |
| `counter_chain` | Optional list, one line per counteroffer in order, naming the terms each set ("CO #3: price $432,500, closing Nov 20, loan approval 25 days"). A working record for re-runs; nothing prints it |
| `preapproval_amount`, `preapproval_price` | Optional, numbers from the pre-approval letter: the loan amount it approves, and the purchase price it covers when it states one. An agent note when either is below the deal's `loan_amount` or `price` |
| `financing` | `cash`, `conventional`, `fha`, `va`, `usda` |
| `preapproval_expires` | The expiration date on the buyer's pre-approval letter when the package has one. Before closing: an agent note to ask the lender. A short sale with no closing date yet: compared with the approval deadline plus the closing days |
| `possession_date`, `possession_time`, `possession_note` | Only if possession differs from closing |
| `date_overrides` | `{deadline key: "YYYY-MM-DD HH:MM"}` for deadlines the contract states as a specific date. With a time it's kept as given; a date alone (`"YYYY-MM-DD"`) ends at the contract's end of day and extends past a weekend or holiday like any period. A `closing` override also moves every date counted back from closing |

FAR/BAR contracts also use the fields in `farbar.md` (deposit days, inspection days, riders, rider dates).

**Terms that set no date or check** have no field: Rider H's premium cap, Rider F's minimum value, Rider E's repair cap, Rider U's rent and cost split, Rider A's Para. 9 boxes, the SIRS receipt when it came with the condo documents. Read them from the contract text; mention one in `agent_notes` only with a question to ask (a blank, a figure that looks wrong). A field is added only where a date or a check uses it.

## deadlines

Required for contracts that aren't FAR/BAR; optional extras for FAR/BAR. One entry per deadline:

```json
{"key": "due_diligence", "label": "Due Diligence Period Ends", "short": "Due Diligence",
 "basis": "after", "days": 7, "party": "Buyer", "critical": true, "contingency": true,
 "source": "Para. 7", "action": "Deliver notice of termination before the deadline if not proceeding",
 "if_missed": "Right to terminate for any reason ends"}
```

| Field | Notes |
|---|---|
| `key` | Short id, unique, and not one of the script's own keys (used by amendments, overrides and `completed`) |
| `label`, `short` | Full name; short name for the timeline strip. Both in Title Case ("Due Diligence Period Ends", "Due Diligence") |
| `basis` | `after` (days after the Effective Date), `before` (days before closing), `date` (with `"date": "YYYY-MM-DD HH:MM"`), `event` (runs from `received`, when recorded) |
| `days` | Required for `after`, `before` and `event` |
| `business` | `true` when the contract counts this period in business days |
| `time` | Any basis: when this deadline ends, `"17:00"`, when it differs from the contract's end of day (a period the contract says ends at 5:00 PM on its last day). `"closing"` means by the closing time: with `basis: before` and `days: 0` it's due "by Closing" on closing day and sorts before the closing (a Para. 20 promise such as carpets cleaned before closing); `"closing"` works only with `before` and `date` |
| `rollover` | Any basis: `false` when this deadline isn't extended past a weekend or holiday even though others are (read the paragraph's own words) |
| `event` | `true` for something done on a day rather than a deadline at a time (a final walk-through): it shows the date alone and is an all-day calendar item, like the FAR/BAR walk-through. A walk-through is one without it, unless the contract sets its `time`. A row due by the closing time (`time: "closing"`) is an all-day calendar item too, never a second event at the closing's hour |
| `receipt_date`, `what` | For an `after` period that runs from someone's receipt rather than the Effective Date (20 days after the title company receives the contract): the receipt date and what was received ("title company's receipt of the contract"). Without the date, ask for it |
| `party` | Required: `Buyer`, `Seller` or `Both`, from who the contract says acts. A duty the contract gives someone else (the escrow agent provides the title commitment) goes to the side whose duty it serves, with that person named in `action`: title work backs the seller's duty to convey title, so `Seller`. `Both` is only for a step both parties take (the closing, an agreement both sign) |
| `critical` | Missing it can cost a contract right or put the deposit at risk (another contract: a deadline the contract makes time-sensitive; the report's star legend says so, never the deposit) |
| `contingency` | It's a buyer protection that ends on this date (drives "your contingencies end") |
| `source`, `action`, `if_missed` | Paragraph, what to do, consequence, in the contract's words, with a party inside a sentence written "the buyer" / "the seller" ("written notice to the seller"); the script lowercases a bare "to Seller" for you. When the contract states no consequence, `if_missed` says so ("The agreement states no specific remedy"); never write one it doesn't state |

## rules

Only when the contract's time rules differ from the market's (or the market has none). Without market rules only `day_count` is required: leave out any rule the contract doesn't state or you haven't confirmed. For a quick question when the day count isn't known either, run once with `calendar` and once with `business` and give both dates (SKILL.md, Deliver); for a full timeline, ask. The script then uses the neutral reading (nothing skipped or moved, the federal holidays, no time of day), adds an agent note listing each open rule to confirm, and the report says only "Not stated in the contract". An open rule that changes no date here isn't asked: the end of day when every dated row has its own time, and the before-closing rollover when no date counted back from closing lands on a weekend or holiday. The output's `open_rules` lists the rules asked.

| Rule | Values |
|---|---|
| `day_count` | `calendar` or `business` |
| `short_period_days` | Periods this long or shorter skip weekends and holidays; `0` for none, which a contract that defines days as calendar days with no short-period exception states (record it; it isn't an open rule) |
| `end_time` | When a day ends, `"23:59"` |
| `weekend_holiday_rollover` | `next_business_day` or `none` |
| `rollover_time` | Time on the next business day; left out, the contract's `end_time` (a period moved past a weekend ends when the contract's days end) |
| `before_closing_rollover` | `previous_business_day`, `next_business_day` or `none` |
| `before_closing_time` | When a date counted back from closing ends, when it differs from `end_time` |
| `holidays` | `us_federal`; a list of extra holiday dates the contract adds (`["2026-11-27"]`); or, when the contract defines its own full list instead of the federal one, `{"base": "none", "dates": ["2026-11-26", "2026-11-27"]}` |

## amendments

In signing order. `changes` for contract fields, `date_overrides` for deadlines set to a specific date:

`name` (optional): the form or title as printed ("Extension Addendum (EA-4)", "Addendum No. 1"). Notes name the amendment by it; without it they say "the first amendment", never "Amendment 1", which an agent reads as a form's own number. An amendment that moves no date (a credit, a confirmed receipt) is still listed, with `"changes": {}`, so the history shows it. `description` says what it does in words, with no date, amount or day count ("Extend closing and loan approval"): the history prints each change with its values, and the script refuses a figure there (and in `possession_note`).

```json
{"date": "2026-10-20", "name": "Extension Addendum (EA-4)", "description": "Extend closing and loan approval",
 "changes": {"closing_date": "2026-11-06", "loan_approval_days": 37},
 "date_overrides": {"appraisal": "2026-10-23 17:00"}}
```

HOA or condo documents received, short sale approval received (`short_sale_approval_received`), a back-up contract delivered, or any other event a rider runs from: set the matching field in `contract` (FAR/BAR, listed in `farbar.md`), or `received` on the `event` deadline, and re-run. A receipt signed on its own form (a condo document receipt, RCD-8) that a later addendum restates goes in `contract` with the receipt's date, and the addendum is listed with `"changes": {}` (plus any real change it makes): in the addendum's `changes`, the row would read as dated by the addendum (`newly_dated`), not from the receipt. When the addendum gives a different receipt date, use the later signed document and flag the difference. The output's `moved` lists the rows whose date changed (with `was`): the closing first when it moved, then the rest in date order. `newly_dated` lists the rows the amendment dated for the first time.

## Script Notes

`timeline.py` adds these itself; don't add them to the deal file.

- **`flags`** (printed as "Check:" lines, each a sentence ending in a period, worded in `assets/labels.json`; one per key in `flag_keys`): loan approval within 5 days of closing or after it; a contingency that ends after closing; a closing on a weekend or holiday; the FHA/VA appraisal note (worded for the loan type); a date counted back from closing that fell on a weekend or holiday and extended closer to closing (with the business day before, to be safe); a blank association approval box; a short sale approval received after the approval deadline or after the contract expired; an extended period that ended on the reading used but runs past the report date on the other reading (EA-4).
- **`agent_notes`** (chat only, one line per key in `note_keys`): the form defaults used for periods the deal file doesn't give (initial and additional deposit, loan application, loan approval, the inspection or Rider K or L period, title evidence, the flood elevation window, Rider F appraisal and Rider H insurance dates, Rider A or B association approval and ROFR days, Rider G application, approval and closing days, Riders I and M periods, Rider T and U agreement deadlines, Rider GG's agreement days), each saying "blank" only for a field in `blanks`, else "not given"; the Standard form's blank repair limits, in dollars; the closing time when the contract states none (10:00 AM); who designates the closing agent when `title_by` is blank; the Rider G notes (Para. 4 closing replaced, approval not received, Rider GG's start, Para. 7 back-up offers); a pre-approval that expires before closing (or, on a short sale, before the latest closing the approval deadline allows); money that doesn't add up (deposits, loan and balance vs. the price) and a pre-approval below the loan amount or the price; Rider F fields without Rider F; a title evidence deadline that is the other financing's default (5 days on a financed deal, 15 on cash); a flood zone not recorded; Rider H's boxes not recorded; Rider H days written in the date blank (`insurance_days`): the date counted back from closing too, and the safe date for the agent's side; Rider P without `year_built` or `built_before_1978` (or with a home built in 1978 or later), and a home built before 1978 without Rider P; Rider U with no tenant and no `occupancy` of `owner` or `vacant` (Para. 6(b)'s lease windows aren't dated); an Effective Date taken from signatures with no delivery shown (`effective_date_delivered: false`); Rider GG's cancel window when the agreement period rolled past a weekend or holiday (the reading used, plus the safe date for the agent's side); an amendment that lengthens a period whose original end had rolled (both readings, EA-4); a split time-zone county, or a time zone taken from the state's main zone (`time_zone_assumed`); rider names that aren't CR-7 riders; time rules the contract doesn't state; an Effective Date or amendment dated after the report date; deadlines before the report date not recorded as done; rows waiting on a receipt date; rider dates left blank with no default; a missing closing date when a date counts back from it; and market assumptions (MLS and cost notes are left out). An agent note keyed to one of these (or with the same words) is dropped: don't restate them.
- **`if_changed`**: for a note whose answer could change a date (Rider F fields without Rider F, the title evidence period, the flood zone, Rider H days written in), `{note_key, if, rows}`: the rows and dates the timeline would have if the answer is the other one. The note quotes the date too; never build a second deal file to find it.
- **`repair_limits`**: the Para. 9(a) limits in dollars (`general`, `wdo`, `permit`, and `blank` for those left blank) when the Standard form's repair obligation applies (alone or with Rider L); otherwise null.
- **`joined_agent_notes`**: the row keys of your notes that merged with their row (above).
- **`critical`** on a row: missing it can cost a contract right. A lender's target (`lender`: insurance bound, Closing Disclosure) is an estimate, never critical, so it carries no star on the report.
- **`first_deadline`**: the earliest open dated row from the report date (not done or past), whoever owes it, critical or not (Rider GG rows only while open), so it never names a later date than a row above it in the table. Never a lender target.
- **`open_rights`**: the rights that outlast the main contingencies, each worded for a sentence ("title defect notices", "the FHA appraisal clause (to closing)").
- **`documents`**: the kinds of document the dates were read from (`contract`, then `riders`, `counteroffers`, `amendments`, each only when the deal records one: riders, a `counter_chain` or a counteroffer named in `effective_date_source`, amendments). The report's fine print names only these.
- **`appointment`** on a row: the closing or possession, which happens at a time. The calendar times only these; every deadline is an all-day event on its day, its title ending with the time the report prints after the day ("(by 11:59 PM)", "(by Closing)").
- **`form_family`**: `farbar` or `other`. For another contract the report states no consequence the deal file doesn't record (no "deposit at risk" line).
- **`warnings`** (for you, never passed on): a `contract` field or amendment change the script doesn't read, usually a misspelled name, or a `blanks` name no default reads. `render.py` prints them too. Fix it and re-run.
- **`chat_notes`** (chat only, never in `agent_notes` or any file): the best-effort line for a contract that isn't FAR/BAR, and a note when a FAR/BAR form isn't the verified revision.
