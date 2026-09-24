## {{subject.address}}: pricing your home

{{"**Preliminary:** some local closing costs are still missing, so the net figures will change." when compute.py's preliminary is true}}

**Recommended list price: {{recommendation.list_price_display}}** · supported value range {{recommendation.range_display}} · expected sale {{recommendation.expected_sale}}

{{recommendation.paragraph, shortened to 2 sentences}}

**Why this price:**
- {{summary_page.why[0]}}
- {{summary_page.why[1]}}
- {{summary_page.why[2]}}

**Comps, adjusted to your home** (median {{median_adjusted_display}}):

| Sale | Sold for | Adjusted |
|---|---|---|
| {{each comps.summary_rows: address, sold price, adjusted}} |

**Your pricing options** (estimates, not guarantees):

| List at | Time to contract | Expected sale | Est. net* | Buyer's payment |
|---|---|---|---|---|
| {{each strategies: list_price_display (★ when recommended), time, expected_sale_display, net_display (or "pending brokerage terms" when net.incomplete is true: never show a net without the commission), payment_display/mo}} |

\*{{"Before mortgage payoff" or, with a payoff, "Cash at closing after your payoff"}}. Every $10,000 in price is about {{payments.per_10k_display}} a month to a buyer. {{one line naming any placeholder in net.notes, such as the brokerage}}

**Before we list:**
1. {{summary_page.first_steps[0]}}
2. {{summary_page.first_steps[1]}}
3. {{summary_page.first_steps[2]}}

**Next step:** {{summary_page.next_step}}

_Broker's opinion of value, not an appraisal. Net figures are estimates; the closing agent provides exact figures._

{{handoff_block, pasted exactly as compute.py printed it}}
