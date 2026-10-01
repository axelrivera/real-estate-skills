## {{subject.address}}: Buyer Market Analysis

**Suggested Opening Offer: {{offer_plan.opening}}** · Target {{offer_plan.target}} · Walk Away Above {{offer_plan.walk_away}}

**Supported Value Range: {{range.display}}.** Asking {{subject.list_price_display}} is {{range.asking_position}}. {{bottom_line_paragraph, shortened to 2 sentences}}

**Why:**
- {{summary_page.why[0]}}
- {{summary_page.why[1]}}
- {{summary_page.why[2]}}

{{when history is not null: "**History:** listed {{history.display.first_listed}}; {{history.display.price_cuts}} ({{history.display.price_cut_total}}), {{history.display.price_increases}}, {{history.display.failed_contracts}}; {{history.display.active_days}} actively for sale." Leave out a part that reads "no …" unless it matters}}

**Comps, Adjusted to This Home** (median {{median_adjusted_display}}):

| Sale | Sold For | Adjusted |
|---|---|---|
| {{each comps_table: address | sold_display | adjusted_display}} |

**What It Will Cost:** estimated tax {{taxes[payments.tax_index].annual_display}}/yr{{" (Estimate from the market's average rate)" when payments.tax_basis.estimated; " (Estimate: the {{payments.tax_basis.short}} bill, until the district is confirmed)" when payments.tax_basis.unconfirmed}}{{ (the listing shows current_bill_display), left out when current_bill_display is null}}; at {{payments.price_display}} ({{payments.price_basis: the target, the asking price…}}), {{payments.rows[0].label}}: about {{payments.rows[0].total_display}}/mo with {{payments.rows[0].cash_down_display}} down and about {{payments.rows[0].cash_to_close_display}} cash to close (down payment plus closing costs). {{when any payments.rows[].cash_short or credit.columns[].cash_short: one line saying which cash to close is more than the buyer's {{payments.buyer_cash_display}}, and by how much, then the option that fits when cash_fit is set ("To fit your cash: {{cash_fit.price_display}} with a {{cash_fit.credit_display}} seller credit needs about {{cash_fit.cash_display}} to close"); when payments.rows[0].cash_left is set, one line saying only that much is left}} {{payments.flood.note, shortened: when payments.flood.annual is null say the total leaves out flood insurance until there's a quote; never write $0 or that flood insurance isn't required}} {{one line on price vs. credit when there are credit scenarios: the cash saved is credit_alt.cash_saved_display (or placeholders.credit_cash_per_5k for each $5,000), never the credit amount}}

**Check Before Offering:**
1. {{summary_page.check_first[0]}}
2. {{summary_page.check_first[1]}}
3. {{summary_page.check_first[2]}}

**Next Step:** {{summary_page.next_step}}

_Broker's opinion of value, not an appraisal, and not for lending purposes. Sales data: {{data_source.mls}} MLS as of {{data_source.as_of_display}}, deemed reliable but not guaranteed. Estimates for planning, not lending or tax advice; confirm with the lender and insurer._

{{the agent's disclaimers from their profile, verbatim, one line each, when there are any}}
