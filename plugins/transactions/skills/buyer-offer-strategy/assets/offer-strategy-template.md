<!-- Fill from scripts/strategy.py output. Values come from the JSON as printed; never recompute them. -->

## Offer strategy: {{property}} (list {{list_price}})

**Recommended offer: {{summary.outlook}} with {{summary.competition}}.** {{summary.why}}

| Term | Offer | Why |
|---|---|---|
| {{t.term}} | **{{t.offer}}**{{" (agent)" when t.agent}} | {{t.why}} |

**Your options**

| Option | Price | Outlook | Seller net | Worst-case cash | Reserve | What changes |
|---|---|---|---|---|---|---|
| {{o.option}} | {{o.price}} | {{o.outlook}} | {{o.seller_net}} | {{o.worst_cash}} | {{o.reserve}} | {{o.what}} |

**Your exposure (recommended):** {{each summary.exposure: label + " " + value, joined with " · "}}

{{each summary.constraints: "**Limit:** " + text}}

{{summary.preliminary, when present}}

**Next step:** {{summary.next_step}}

**To sharpen this:** {{to_confirm, as one short question; skip when empty}}

<sub>Financing: {{summary.financing}}. Seller net is before the seller's mortgage payoff, as a listing agent would calculate it. The outlook is an estimate, not a probability. Payments and closing costs are estimates; the lender's Loan Estimate governs.</sub>

<!-- On request only:
- "How does it stack up?": a table from summary.bands (rows = level, columns = summary.option_labels).
- "Side by side": side_by_side[] as a table (term + one column per option).
- "Contract entries / worksheet": worksheet.form_name, then worksheet.rows as "field: entry (note)" (paragraph first when worksheet.frbar), worksheet.riders, worksheet.clauses (quote the text as written), then worksheet.package as a checklist with "- [ ]". Text in [brackets] is a blank for the agent to fill.
- Assumptions: assumptions[] as "impact · where · what". -->
