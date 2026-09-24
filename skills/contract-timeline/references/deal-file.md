# Deal File

The JSON record of an executed contract. `scripts/timeline.py` computes the dates from it and `scripts/render.py` builds the PDF. Keep it with the deliverable: amendments are added to it, never rebuilt.

```json
{
  "side": "buyer",
  "client": "Name on the report",
  "state": "FL",
  "county": "Seminole",
  "contract": { },
  "deadlines": [ ],
  "amendments": [ ],
  "flags": ["checks the client should see too; printed on the report"],
  "agent_notes": ["for the agent only: defaults used, readings to confirm; never printed"],
  "rules": { }
}
```

`time_zone` (optional: `CT`, `ET`...; Florida's western Panhandle counties are Central time and print "CT" after each time; Gulf County is split, so set it there). `state` (required: ask for it, never assume Florida) and `county` pick the market's time rules (built in for Florida). Those rules cover only the market's own forms (in Florida, FR/BAR AS IS and Standard); any other contract, such as a builder's form, takes its time rules from its own definitions in `rules`. `rules` also overrides the market's rules for this contract (see below).

`flags` print on the PDF as "Check:" lines; `agent_notes` go only to the agent in chat. When in doubt, it's an agent note: a client reading "used the 5-day form default" worries without being able to act on it.

## contract

| Field | Notes |
|---|---|
| `form_family` | `frbar` for FR/BAR AS IS or Standard; anything else is treated as another contract |
| `form` | Form name as printed, for other contracts ("TREC One to Four Family Residential Contract") |
| `effective_date` | **Required.** `YYYY-MM-DD`. The date the last party signed or initialed and delivered the final counter or acceptance |
| `effective_date_source` | The evidence ("Seller's initials on Counteroffer #1, 9/25 4:12 PM") |
| `closing_date`, `closing_time` | Date (needed for the report and for dates counted back from closing; a quick question can go without); time `HH:MM`. Leave the time out when the contract doesn't state one: 10:00 AM is used and an agent note says so |
| `property`, `buyer`, `seller`, `price`, `escrow_agent` | For the report |
| `financing` | `cash`, `conventional`, `fha`, `va`, `usda` |
| `possession_date`, `possession_time`, `possession_note` | Only if possession differs from closing |
| `date_overrides` | `{deadline key: "YYYY-MM-DD HH:MM"}` for deadlines the contract states as a specific date. With a time it's kept as given; a date alone (`"YYYY-MM-DD"`) ends at the contract's end of day and extends past a weekend or holiday like any period. A `closing` override also moves every date counted back from closing |

FR/BAR contracts also use the fields in `frbar.md` (deposit days, inspection days, riders…).

## deadlines

Required for contracts that aren't FR/BAR; optional extras for FR/BAR. One entry per deadline:

```json
{"key": "option_period", "label": "Option Period Ends", "short": "Option Ends",
 "basis": "after", "days": 7, "party": "Buyer", "critical": true, "contingency": true,
 "source": "Para. 5B", "action": "Deliver notice of termination before the deadline if not proceeding",
 "if_missed": "Right to terminate for any reason ends; option fee is not refunded"}
```

| Field | Notes |
|---|---|
| `key` | Short id, unique (used by amendments and overrides) |
| `label`, `short` | Full name; short name for the timeline strip. Both in Title Case ("Option Period Ends", "Option Ends") |
| `basis` | `after` (days after the Effective Date), `before` (days before closing), `date` (with `"date": "YYYY-MM-DD HH:MM"`), `event` (runs from `received`, when recorded) |
| `days` | For `after`, `before` and `event` |
| `business` | `true` when the contract counts this period in business days |
| `time` | When this deadline ends, `"17:00"`, when it differs from the contract's end of day (a TREC option period ends at 5:00 PM) |
| `rollover` | `false` when this deadline isn't extended past a weekend or holiday even though others are (read the paragraph's own words) |
| `receipt_date`, `what` | For an `after` period that runs from someone's receipt rather than the Effective Date (TREC Para. 6B: 20 days after the title company receives the contract): the receipt date and what was received ("title company's receipt of the contract"). Without the date, ask for it |
| `party` | `Buyer`, `Seller` or `Both` |
| `critical` | Missing it can cost a contract right or put the deposit at risk |
| `contingency` | It's a buyer protection that ends on this date (drives "your contingencies end") |
| `source`, `action`, `if_missed` | Paragraph, what to do, consequence |

## rules

Only when the contract's time rules differ from the market's (or the market has none):

| Rule | Values |
|---|---|
| `day_count` | `calendar` or `business` |
| `short_period_days` | Periods this long or shorter skip weekends and holidays; `0` for none |
| `end_time` | When a day ends, `"23:59"` |
| `weekend_holiday_rollover` | `next_business_day` or `none` |
| `rollover_time` | Time on the next business day, default `"17:00"` |
| `before_closing_rollover` | `previous_business_day` or `none` |
| `holidays` | `us_federal`; `tx_state` for TREC forms (Texas legal holidays: no Columbus Day, adds June 19 and the Friday after Thanksgiving, no observed days); or a list of extra holiday dates from the contract |

## amendments

In signing order. `changes` for contract fields, `date_overrides` for deadlines set to a specific date:

```json
{"date": "2026-10-20", "description": "Extend closing and loan approval",
 "changes": {"closing_date": "2026-11-06", "loan_approval_days": 37},
 "date_overrides": {"appraisal": "2026-10-23 17:00"}}
```

HOA or condo documents received: set `hoa_docs_received` or `condo_docs_received` in `contract` (FR/BAR), or `received` on the `event` deadline, and re-run.
