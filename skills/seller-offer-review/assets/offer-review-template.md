<!-- Fill from scripts/review.py output. Values come from the JSON as printed; never recompute them. Use the single or the multi block, not both.
     Offers are named by their label (offer_label, plan.offer, r.offer), never by id letter. -->

## Offer Review: {{property}} (List {{list_price}})

<!-- single mode; when summary.action is INCOMPLETE, write only the headline, why, the fixes as a list ("issue: fix") and the next step: no counter, options or recommendation -->
**{{summary.headline}}: {{summary.offer_label}}.** {{summary.why}}

{{when summary.counter:}}
**Our Counter** ({{summary.counter.summary}}):

| Term | Buyer Offered | We Counter | Why |
|---|---|---|---|
| {{row.term}} | {{row.offered}} | **{{row.counter}}** | {{row.why}} |


| | |
|---|---|
| {{each summary.kpis: kpi.label}} | **{{kpi.value}}** ({{kpi.note}}, when there is one) |
| Certainty | {{summary.certainty.score}}/100, {{summary.certainty.band}}; buyer can walk away until {{summary.certainty.walk_away_until}}; biggest threat: {{summary.certainty.threat}} |

**Top Risks:** {{each summary.risks: risk.issue}}

<!-- multi mode -->
**{{summary.headline}}: {{summary.offer_label}}.** {{summary.why}}

**The Plan** ({{summary.plan_summary}}):

| # | Offer | Action | Price | Net | Downside | Certainty | Buyer Can Walk | Close | Terms / Reason |
|---|---|---|---|---|---|---|---|---|---|
| {{r.rank}} | {{r.offer}} ({{r.financing}}) | {{r.action}} | {{r.price}} | {{r.net}} | {{r.downside}} | {{r.score}} | {{r.risk_days}} days | {{r.close}} | {{r.terms}} |

{{summary.plan_note}}

<!-- both modes -->
**Options:** {{each summary.options: "**" + option + "**" + (" (recommended)" when recommended) + ": " + net + " · " + certainty + " · " + what}}

{{summary.preliminary, when present}}

**Next Step:** {{summary.next_step}}

**To Sharpen This:** {{to_confirm, as one short question; skip when empty}}

<sub>Net = after all costs and holding, {{"before mortgage payoff" when the data note says so}}. Downside = if the appraisal and inspection go badly. Estimates only; the title company's settlement statement governs. Commissions are negotiable and not set by law. Not legal advice.</sub>

{{the agent's disclaimers from their profile, verbatim, one line each, when there are any}}

<!-- On request only ("show me the net sheet"): one table per offer from offers[].net_sheet, columns net_sheet.columns, rows net_sheet.rows. Then list assumptions[] as "impact · where · what". -->
