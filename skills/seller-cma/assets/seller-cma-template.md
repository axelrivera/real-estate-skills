## {{subject.address}}: Seller Summary

{{"**Preliminary:** " + preliminary_reason, when preliminary is true}}

**{{summary.rec_label, in Title Case}}: {{recommendation.list_price_display}}** · **Supported Value Range:** {{recommendation.range_display}} · **Expected Sale:** {{recommendation.expected_sale_display}}

{{summary.headline, when there is one}}

{{recommendation.line}} {{stance.line}} {{price_history, when it is set}} {{"Listing history: " + history_line, when it isn't empty}} {{recommendation.why, its first sentence}}

**Why This Price:**
- {{summary.why[0]}}
- {{summary.why[1]}}
- {{summary.why[2]}}

**Comps, Adjusted to Your Home** (median {{median_adjusted_display}}):

| Sale | Sold For | Seller Paid | Adjusted Value |
|---|---|---|---|
| {{each comps_table: address | sold_display | seller_paid_display | adjusted_display}} |

{{comps.strongest.line}}

**Your Pricing Options:**

| Option | Time to Contract | Expected Sale | {{options_summary.net_header}} | Buyer's Payment |
|---|---|---|---|---|
| {{each strategies: label, then " ★" when recommended | time | expected_sale_display | net_after_holding_display ("pending brokerage terms" when net.incomplete is true: never show a net without the commission) | payment_display/mo}} |

{{options_summary.note}} {{options_summary.spread_line}} Every $10,000 in price is about {{payments.per_10k_display}} a month to a buyer.

{{one line comparing the options, on the table's basis: each other strategy's net_vs_recommended_about, and net_spread_about}}

**Assumptions:** {{each assumptions, one short line each}}

**{{summary.first_heading}}:**
1. **{{summary.first_steps[0][0]}}:** {{summary.first_steps[0][1]}}
2. **{{summary.first_steps[1][0]}}:** {{summary.first_steps[1][1]}}
3. **{{summary.first_steps[2][0]}}:** {{summary.first_steps[2][1]}}

**Next Step:** {{summary.next_step}} {{summary.launch_line}}

_{{each notices, one after another}} {{each chat_notes, shortened to their first sentence}}_

{{the agent's disclaimers from their profile, verbatim, one line each, when there are any}}
