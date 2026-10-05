## {{subject.address}}: Buyer Market Analysis

**Suggested Opening Offer: {{offer_plan.opening_display}}** · Target {{offer_plan.target_display}} · Walk Away Above {{offer_plan.walk_away_display}}

**Supported Value Range: {{range.display}}.** {{bottom_line.line}} {{bottom_line.why, its first sentence}}

**Why This Offer:**
- {{summary.why[0]}}
- {{summary.why[1]}}
- {{summary.why[2]}}

{{when history_section is not null: "**History:** " then history_section.lines, as written, one after another}}

**Comparable Sales, Adjusted to This Home** (median {{median_adjusted_display}}):

| Sale | Sold For | Adjusted |
|---|---|---|
| {{each comps_table: address | sold_display | adjusted_display}} |

**What It Will Cost You** ({{summary.cost_note, its first sentence}}):
- {{each summary.cost_rows: "its label: its figure", then its flag in parentheses when it has one}}
- {{payments.rows[0].label}}: {{payments.rows[0].cash_down_display}} down, about {{payments.rows[0].cash_to_close_display}} cash to close{{" (payments.rows[0].cash_short_display over the buyer's payments.buyer_cash_display)" when payments.rows[0].cash_short is set; " (only payments.rows[0].cash_left_display of payments.buyer_cash_display left)" when payments.rows[0].cash_left is set}}
{{summary.cash_fit_line as its own line, when it isn't empty}}
{{costs.credit.per_5k as its own line, when costs.credit is set; when naming the credit alternative, its saving is credit_alt.cash_saved_display, never the credit amount}}

**Assumptions:** {{each assumptions, one short line each}}

**Check Before You Offer:**
1. **{{summary.check_first[0][0]}}:** {{summary.check_first[0][1]}}
2. **{{summary.check_first[1][0]}}:** {{summary.check_first[1][1]}}
3. **{{summary.check_first[2][0]}}:** {{summary.check_first[2][1]}}

**Next Step:** {{summary.next_step}}

_{{each notices, one after another}} {{each chat_notes, shortened to their first sentence}}_

{{the agent's disclaimers from their profile, verbatim, one line each, when there are any}}
