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
  "flags": ["checks the client should see too; printed on the report"],
  "agent_notes": ["for the agent only: defaults used, readings to confirm; never printed"],
  "rules": { }
}
```

`time_zone` (optional: `CT`, `ET`...; Florida's western Panhandle counties are Central time and print "CT" after each time; Gulf County is split, so set it there). `state` (required: ask for it, never assume Florida) and `county` pick the market's time rules (built in for Florida). Those rules cover only the market's own forms (in Florida, FR/BAR AS IS and Standard); any other contract, such as a builder's form, takes its time rules from its own definitions in `rules`. `rules` also overrides the market's rules for this contract (see below).

`completed` (optional): deadlines already met, by deadline key (the keys in the script output), with the date each was done. An escrow receipt in the package is the deposit done. A done row shows "Done Sep 26" on the report and in the output (`done`, `done_display`), never counts as the first deadline, and gets no calendar event. `report_date` (optional, `YYYY-MM-DD`): the report's Prepared date, today if left out. A deadline before it that isn't in `completed` shows "Past, Confirm" (`past`, `past_display`), is never the first deadline and gets no calendar event; the script lists it in an agent note.

`what_if` (optional): `true` for a hypothetical timeline the agent asked for (a future Effective Date). The PDF and the calendar say What-If. `sample` is for the plugin's own samples (prints SAMPLE DATA); leave it out.

`flags` print on the PDF as "Check:" lines; `agent_notes` go only to the agent in chat. When in doubt, it's an agent note: a client reading "used the 5-day form default" worries without being able to act on it.

## contract

| Field | Notes |
|---|---|
| `form_family` | `frbar` for FR/BAR AS IS or Standard; anything else is treated as another contract |
| `form` | Form name as printed, for other contracts ("Sample Residential Purchase Agreement") |
| `form_revision` | FR/BAR: the footer as printed ("FloridaRealtors/FloridaBar-ASIS-7x Rev. 2/26"). A revision other than the verified one adds an agent note |
| `effective_date` | **Required.** `YYYY-MM-DD`. The date the last party signed or initialed and delivered the final counter or acceptance |
| `effective_date_source` | The evidence ("Seller's initials on Counteroffer #1, 9/25 4:12 PM") |
| `closing_date`, `closing_time` | Date (needed for the report and for dates counted back from closing; a quick question can go without); time `HH:MM`. Leave the time out when the contract doesn't state one: 10:00 AM is used and an agent note says so. With a short sale rider (FR/BAR Rider G) the closing counts from the approval instead (`frbar.md`) |
| `closing_source`, `possession_source` | Optional: the paragraph cited for the closing and possession rows, when it isn't Para. 4 / Para. 6 (FR/BAR) or "Contract" |
| `property`, `buyer`, `seller`, `price`, `escrow_agent` | For the report. `price` is a number (412000) |
| `financing` | `cash`, `conventional`, `fha`, `va`, `usda` |
| `preapproval_expires` | The expiration date on the buyer's pre-approval letter when the package has one. Before closing: an agent note to ask the lender |
| `possession_date`, `possession_time`, `possession_note` | Only if possession differs from closing |
| `date_overrides` | `{deadline key: "YYYY-MM-DD HH:MM"}` for deadlines the contract states as a specific date. With a time it's kept as given; a date alone (`"YYYY-MM-DD"`) ends at the contract's end of day and extends past a weekend or holiday like any period. A `closing` override also moves every date counted back from closing |

FR/BAR contracts also use the fields in `frbar.md` (deposit days, inspection days, riders, rider dates).

## deadlines

Required for contracts that aren't FR/BAR; optional extras for FR/BAR. One entry per deadline:

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
| `receipt_date`, `what` | For an `after` period that runs from someone's receipt rather than the Effective Date (20 days after the title company receives the contract): the receipt date and what was received ("title company's receipt of the contract"). Without the date, ask for it |
| `party` | Required: `Buyer`, `Seller` or `Both` |
| `critical` | Missing it can cost a contract right or put the deposit at risk |
| `contingency` | It's a buyer protection that ends on this date (drives "your contingencies end") |
| `source`, `action`, `if_missed` | Paragraph, what to do, consequence |

## rules

Only when the contract's time rules differ from the market's (or the market has none). Without market rules only `day_count` is required: leave out any rule the contract doesn't state or you haven't confirmed. The script then uses the neutral reading (nothing skipped or moved, the federal holidays, no time of day), adds an agent note listing each open rule, and the report marks it "to confirm".

| Rule | Values |
|---|---|
| `day_count` | `calendar` or `business` |
| `short_period_days` | Periods this long or shorter skip weekends and holidays; `0` for none |
| `end_time` | When a day ends, `"23:59"` |
| `weekend_holiday_rollover` | `next_business_day` or `none` |
| `rollover_time` | Time on the next business day, default `"17:00"` |
| `before_closing_rollover` | `previous_business_day`, `next_business_day` or `none` |
| `before_closing_time` | When a date counted back from closing ends, when it differs from `end_time` |
| `holidays` | `us_federal`; a list of extra holiday dates the contract adds (`["2026-11-27"]`); or, when the contract defines its own full list instead of the federal one, `{"base": "none", "dates": ["2026-11-26", "2026-11-27"]}` |

## amendments

In signing order. `changes` for contract fields, `date_overrides` for deadlines set to a specific date:

```json
{"date": "2026-10-20", "description": "Extend closing and loan approval",
 "changes": {"closing_date": "2026-11-06", "loan_approval_days": 37},
 "date_overrides": {"appraisal": "2026-10-23 17:00"}}
```

HOA or condo documents received, short sale approval received (`short_sale_approval_received`), a back-up contract delivered, or any other event a rider runs from: set the matching field in `contract` (FR/BAR, listed in `frbar.md`), or `received` on the `event` deadline, and re-run. The output's `moved` lists the rows whose date changed (with `was`), and `newly_dated` the rows the amendment dated for the first time.

## Script Notes

`timeline.py` adds these itself; don't add them to the deal file.

- **`flags`** (printed as "Check:" lines): loan approval within 5 days of closing or after it; a contingency that ends after closing; a closing on a weekend or holiday; the FHA/VA appraisal note; a blank association approval box; a short sale approval received after the approval deadline or after the contract expired.
- **`agent_notes`** (chat only): the title evidence, Rider F appraisal and Rider H insurance defaults; the closing time when the contract states none (10:00 AM); who designates the closing agent when `title_by` is blank; the Rider G notes (Para. 4 closing replaced, approval not received, Rider GG's start, Para. 7 back-up offers); a pre-approval that expires before closing; a split time-zone county; rider names that aren't CR-7 riders; time rules the contract doesn't state; an Effective Date or amendment dated after the report date; deadlines before the report date not recorded as done; rows waiting on a receipt date; rider dates left blank with no default; and market assumptions (MLS and cost notes are left out).
- **`chat_notes`** (chat only, never in `agent_notes` or any file): the best-effort line for a contract that isn't FR/BAR, and a note when an FR/BAR form isn't the verified revision.
