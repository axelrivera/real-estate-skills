## {{subject.address}}: Buyer Market Analysis

**Suggested Opening Offer: {{offer_plan.opening}}** · Target {{offer_plan.target}} · Walk Away Above {{offer_plan.walk_away}}

**Supported Value Range: {{range.display}}.** Asking {{subject.list_price_display}} is {{range.asking_position}}. {{bottom_line_paragraph, shortened to 2 sentences}}

**Why This Offer:**
- {{summary_page.why[0]}}
- {{summary_page.why[1]}}
- {{summary_page.why[2]}}

{{when history is not null: "**History:** listed {{history.display.first_listed}}; {{history.display.price_cuts}} ({{history.display.price_cut_total}}), {{history.display.price_increases}}, {{history.display.failed_contracts}}; {{history.display.active_days}} actively for sale{{" since the {{history.counted_since_sale_display}} sale" when history.counted_since_sale_display is set}}." Leave out a part that reads "no …" unless it matters}}

**Comparable Sales, Adjusted to This Home** (median {{median_adjusted_display}}):

| Sale | Sold For | Adjusted |
|---|---|---|
| {{each comps_table: address | sold_display | adjusted_display}} |

**What It Will Cost You:** estimated tax {{taxes[payments.tax_index].annual_display}}/yr {{"with homestead" when payments.tax_basis.homestead, else "no homestead"}}{{" (Estimate from the market's average rate)" when payments.tax_basis.estimated; " (Estimate: the {{payments.tax_basis.short}} bill{{", the higher of the two" when payments.tax_basis.higher}}, until the district is confirmed)" when payments.tax_basis.unconfirmed}}{{" (the listing shows {{current_bill_display}})", left out when current_bill_display is null}}; at {{payments.price_display}}{{" (the target)", " (the asking price)", " (the opening offer)" or " (the walk-away)" for payments.price_basis target, asking, opening or walk_away; nothing when it is null}}, {{payments.rows[0].label}}: about {{payments.rows[0].total_display}}/mo with {{payments.rows[0].cash_down_display}} down and about {{payments.rows[0].cash_to_close_display}} cash to close (down payment plus closing costs). {{when payments.rows[0].cash_short is set: "That's {{payments.rows[0].cash_short_display}} over the buyer's {{payments.buyer_cash_display}}." Then, when cash_fit is set and cash_fit.credit is more than 0: "To fit your cash: {{cash_fit.price_display}} with a {{cash_fit.credit_display}} seller credit needs about {{cash_fit.cash_display}} to close.", or when cash_fit.credit is 0: "To fit your cash: a {{cash_fit.price_display}} price needs about {{cash_fit.cash_display}} to close."}}{{when payments.rows[0].cash_left is set: "That leaves only {{payments.rows[0].cash_left_display}} of the buyer's {{payments.buyer_cash_display}}."}} Insurance is an estimate until there's a quote{{"; closing costs are about {{payments.closing.pct_display}} of the price until the lender's estimate", left out when payments.rows[0].lender_closing_costs}}. {{payments.flood.note, shortened: when payments.flood.annual is null say the total leaves out flood insurance until there's a quote; never write $0 or that flood insurance isn't required}} {{when placeholders.credit_cash_per_5k is set: "Each $5,000 of seller credit saves about {{placeholders.credit_cash_per_5k}} at closing and adds about {{placeholders.credit_monthly_per_5k}} a month." When naming the credit alternative, its saving is credit_alt.cash_saved_display; never quote the credit amount as the cash saved}}

**Check Before You Offer:**
1. **{{summary_page.check_first[0][0]}}:** {{summary_page.check_first[0][1]}}
2. **{{summary_page.check_first[1][0]}}:** {{summary_page.check_first[1][1]}}
3. **{{summary_page.check_first[2][0]}}:** {{summary_page.check_first[2][1]}}

**Next Step:** {{summary_page.next_step}}

_Broker's opinion of value, not an appraisal, and not for lending purposes. Sales data: {{data_source.mls}} MLS as of {{data_source.as_of_display}}, deemed reliable but not guaranteed. Estimates for planning, not lending or tax advice; confirm with the lender and insurer._

{{the agent's disclaimers from their profile, verbatim, one line each, when there are any}}
