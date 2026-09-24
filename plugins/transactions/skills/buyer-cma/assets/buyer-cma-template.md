## {{subject.address}}: Buyer Market Analysis

**Suggested Opening Offer: {{offer_plan.opening}}** · Target {{offer_plan.target}} · Walk Away Above {{offer_plan.walk_away}}

**Supported Value Range: {{range.display}}.** Asking {{subject.list_price_display}} is {{range.asking_position}}. {{bottom_line.paragraph, shortened to 2 sentences}}

**Why:**
- {{summary_page.why[0]}}
- {{summary_page.why[1]}}
- {{summary_page.why[2]}}

**Comps, Adjusted to This Home** (median {{median_adjusted_display}}):

| Sale | Sold For | Adjusted |
|---|---|---|
| {{each comps.summary_rows: address, sold price, adjusted}} |

**What It Will Cost:** estimated tax {{taxes[payments.tax_index].annual_display}}/yr{{ (the listing shows current_bill_display), left out when current_bill_display is null}}; {{payments.rows[0].label}}: about {{payments.rows[0].total_display}}/mo with {{payments.rows[0].cash_down_display}} down. {{payments.flood.note, shortened: when payments.flood.annual is null say the total leaves out flood insurance until there's a quote; never write $0 or that flood insurance isn't required}} {{one line on price vs. credit when there are credit scenarios}}

**Check Before Offering:**
1. {{summary_page.check_first[0]}}
2. {{summary_page.check_first[1]}}
3. {{summary_page.check_first[2]}}

**Next Step:** {{summary_page.next_step}}

_Broker's opinion of value, not an appraisal, and not for lending purposes. Sales data: {{data_source.mls}} MLS as of {{data_source.as_of}}, deemed reliable but not guaranteed. Estimates for planning, not lending or tax advice; confirm with the lender and insurer._

{{the agent's disclaimers from their profile, verbatim, one line each, when there are any}}

{{handoff_block, pasted exactly as compute.py printed it}}
