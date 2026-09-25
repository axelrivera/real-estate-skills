## {{subject.address}}: Pricing Your Home

{{"**Preliminary:** some local closing costs are still missing, so the net figures will change." when compute.py's preliminary is true}}

**Recommended List Price: {{recommendation.list_price_display}}** · **Supported Value Range:** {{recommendation.range_display}} · **Expected Sale:** {{recommendation.expected_sale}}

{{recommendation.paragraph, shortened to 2 sentences}}

**Why This Price:**
- {{summary_page.why[0]}}
- {{summary_page.why[1]}}
- {{summary_page.why[2]}}

**Comps, Adjusted to Your Home** (median {{median_adjusted_display}}):

| Sale | Sold For | Adjusted |
|---|---|---|
| {{each comps.summary_rows: address, sold price, adjusted}} |

**Your Pricing Options** (estimates, not guarantees):

| List At | Time to Contract | Expected Sale | Est. Net* | Buyer's Payment |
|---|---|---|---|---|
| {{each strategies: list_price_display (★ when recommended), time, expected_sale_display, net_display (or "pending brokerage terms" when net.incomplete is true: never show a net without the commission), payment_display/mo}} |

\*{{"Before mortgage payoff" or, with a payoff, "Cash at closing after your payoff"}}. Every $10,000 in price is about {{payments.per_10k_display}} a month to a buyer. {{one line naming any placeholder in net.notes, such as the brokerage}}

**Before We List:**
1. {{summary_page.first_steps[0]}}
2. {{summary_page.first_steps[1]}}
3. {{summary_page.first_steps[2]}}

**Next Step:** {{summary_page.next_step}}

_Broker's opinion of value, not an appraisal, and not for lending purposes. Sales data: {{data_source.mls}} MLS as of {{data_source.as_of}}, deemed reliable but not guaranteed. Net figures are estimates; the closing agent provides exact figures. Commissions are negotiable and not set by law._

{{the agent's disclaimers from their profile, verbatim, one line each, when there are any}}
