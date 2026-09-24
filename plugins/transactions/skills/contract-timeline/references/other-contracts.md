# Other contracts (outside FR/BAR)

For any contract that isn't an FR/BAR form: another state's promulgated form, a builder contract, a custom addendum-heavy deal. The script doesn't know these forms, so you read the deadlines from the contract and the agent confirms them. That's the safe split: the script does the date math, you do the reading, the agent checks your reading.

## 1. Time rules

Find the contract's definitions of time (usually a "Time", "Computation of time" or "Definitions" paragraph):

- Are days calendar or business days? Does it say periods of a few days or less skip weekends?
- When does a day end (5:00 PM, 11:59 PM, "local time")?
- What happens when a period ends on a weekend or holiday?
- Does it name holidays beyond the federal ones? Texas forms use Texas legal holidays: set `holidays: tx_state`.

If the agent's market profile has `contract` rules and they match, nothing more is needed. Otherwise put what the contract says in the deal file's `rules` (format in `deal-file.md`). If the contract is silent on something, ask the agent rather than assume Florida's rules; that's what would otherwise quietly move a deadline by a day.

## 2. Deadlines

Set `"form_family": "other"` and `"form"` to the form name. Then add one `deadlines` entry per date the contract creates. Common ones to look for:

| Look for | Usually |
|---|---|
| Earnest money / escrow deposit | days after Effective Date, Buyer, critical |
| Option or due-diligence period (TX option, NC due diligence, GA due diligence) | days after Effective Date, Buyer, critical, contingency |
| Inspection / objection / resolution periods | after, Buyer, critical, contingency |
| Financing application and approval | after, Buyer, contingency for approval |
| Appraisal contingency | after, Buyer, critical, contingency |
| Seller disclosures, HOA documents | after or event, Seller |
| Title commitment, survey, objections | after or before closing |
| Closing and possession | the contract's dates |

Use the contract's own words for `label` (in Title Case), `action` and `if_missed`, and its paragraph numbers for `source`. When one deadline has its own time or weekend rule, set `time` and `rollover` on that deadline. A period that runs from someone's receipt rather than the Effective Date gets `receipt_date` and `what`.

**Texas (TREC 20-19, required since July 1, 2026; it replaced 20-18).** Verified against the form:

| Deadline | Rule | Deal File |
|---|---|---|
| Earnest money and option fee (Para. 5A) | 3 days after the Effective Date, to the end of the day; a last day on a weekend or Texas legal holiday extends to the next day that isn't one. The only extension in the form | `days: 3`, `rollover: true` |
| Option period (Para. 5B) | Notice by 5:00 PM local time on the last day; never extended | `time: "17:00"`, `rollover: false` |
| Title commitment (Para. 6B) | 20 days after the title company receives the contract; extended automatically up to 15 days or 3 days before closing, whichever is earlier | `receipt_date`, `days: 20` |
| Appraisal termination | TREC 49-1 addendum (not for FHA or VA, which have their own amendatory clause) | its own days |

Rules for 20-19: `end_time: "23:59"`, `weekend_holiday_rollover: none`, `rollover_time: "23:59"`, `before_closing_rollover: none`, `holidays: tx_state`. Texas legal holidays (Tex. Gov't Code 662.003) don't include Columbus Day, add June 19 and the Friday after Thanksgiving, and aren't moved when they fall on a weekend. The fixture `texas-trec.json` in the repo is a worked example. Contract time rules come from the contract or the agent: a web search can find a form's text, but confirm with the agent which version they signed. Mark `contingency: true` only on buyer protections that end on that date. That's what drives "your contingencies end" on page 1.

## 3. Confirm

For a quick question about one date, skip the round trip: answer, and state in the same reply the rule you used and the reading to confirm ("7 days after Nov 20, ending 5:00 PM, not extended; confirm your form says the same").

For a full timeline, before running, list the deadlines back to the agent in plain words ("Option period: 7 days after the Effective Date, ends Oct 2 at 5 PM") and ask them to confirm. Put anything you had to interpret in `flags`.
