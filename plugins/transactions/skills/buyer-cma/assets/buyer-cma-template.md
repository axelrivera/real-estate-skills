## {{subject.address}}: buyer market analysis

**Suggested opening offer: {{offer_plan.opening}}** · target {{offer_plan.target}} · walk away above {{offer_plan.walk_away}}

**Supported value range: {{range.display}}.** Asking {{subject.list_price_display}} is {{range.asking_position}}. {{bottom_line.paragraph, shortened to 2 sentences}}

**Why:**
- {{summary_page.why[0]}}
- {{summary_page.why[1]}}
- {{summary_page.why[2]}}

**Comps, adjusted to this home** (median {{median_adjusted_display}}):

| Sale | Sold for | Adjusted |
|---|---|---|
| {{each comps.summary_rows: address, sold price, adjusted}} |

**What it will cost:** estimated tax {{taxes[payments.tax_index].annual_display}}/yr (the listing shows {{current_bill_display}}); {{payments.rows[0].label}}: about {{payments.rows[0].total_display}}/mo with {{payments.rows[0].cash_down_display}} down. {{one line on price vs. credit when there are credit scenarios}}

**Check before offering:**
1. {{summary_page.check_first[0]}}
2. {{summary_page.check_first[1]}}
3. {{summary_page.check_first[2]}}

**Next step:** {{summary_page.next_step}}

_Broker's opinion of value, not an appraisal. Estimates for planning; confirm with the lender and insurer._

{{handoff_block, pasted exactly as compute.py printed it}}
