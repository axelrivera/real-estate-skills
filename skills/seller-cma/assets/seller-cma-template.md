## {{subject.address}}: Seller Summary

{{"**Preliminary:** " + preliminary_reason, when preliminary is true}}

**{{"New List Price" when reprice is set, else "Recommended List Price"}}: {{recommendation.list_price_display}}** · **Supported Value Range:** {{recommendation.range_display}} · **Expected Sale:** {{recommendation.expected_sale}}

{{summary_page.headline, when there is one}}

{{reprice.price_history when reprice is set, or relist.price_history when relist is set}} {{"Listing history: " + each listing_history[].text, when there are any}} {{recommendation_paragraph, shortened to 2 sentences}}

**Why This Price:**
- {{summary_page.why[0]}}
- {{summary_page.why[1]}}
- {{summary_page.why[2]}}

**Comps, Adjusted to Your Home** (median {{median_adjusted_display}}):

| Sale | Sold For | Seller Paid | Adjusted Value |
|---|---|---|---|
| {{each comps_table: address | sold_display | seller_paid_display | adjusted_display}} |

**Your Pricing Options:**

| List At | Time to Contract | Expected Sale | {{options_summary.net_header}}{{" (Assumed Brokerage)" when net.standard_terms is true}} | Buyer's Payment |
|---|---|---|---|---|
| {{each strategies, row i: "Stay at " + list_price_display when i is reprice.stay_index, else list_price_display; " ★" when recommended | time | expected_sale_display | net_after_holding_display ("pending brokerage terms" when net.incomplete is true: never show a net without the commission) | payment_display/mo}} |

{{options_summary.note}} {{expected_sale_basis.note}} Every $10,000 in price is about {{payments.per_10k_display}} a month to a buyer. {{one line naming any placeholder in net.notes, such as the brokerage}}

{{one line comparing the options, on the table's basis: each other strategy's net_vs_recommended_about, and net_spread_about}}

Buyer's payments assume: {{payments.basis_note}} {{"Flood insurance is not included." when payments.flood.annual is empty, plus, when payments.flood.required is set, payments.flood.note's requirement in one short clause}}

**{{first_steps_heading}}:**
1. **{{summary_page.first_steps[0][0]}}:** {{summary_page.first_steps[0][1]}}
2. **{{summary_page.first_steps[1][0]}}:** {{summary_page.first_steps[1][1]}}
3. **{{summary_page.first_steps[2][0]}}:** {{summary_page.first_steps[2][1]}}

**Next Step:** {{summary_page.next_step}}

_Broker's opinion of value, not an appraisal, and not for lending purposes. Sales data: {{"{data_source.mls} MLS" when data_source.export is true, else "the sales provided"}} as of {{data_source.as_of_display}}, deemed reliable but not guaranteed. Payment, tax and cost figures are estimates only, not lending or tax advice; the closing agent provides exact net figures. Commissions are negotiable and not set by law._

{{the agent's disclaimers from their profile, verbatim, one line each, when there are any}}
