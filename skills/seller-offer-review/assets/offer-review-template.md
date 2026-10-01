<!-- Fill from scripts/review.py output. Values come from the JSON as printed; never recompute them. Use the single or the multi block, not both.
     Offers are named by their label (offer_label, plan.offer, r.offer), never by id letter. -->

## Offer Review: {{property}} (List {{list_price}})

{{value_range_confirm, when present}} {{deadline_note, when present}}

<!-- single mode; when summary.action is INCOMPLETE, write only the title, why, the fixes as a list ("issue: fix") and the next step: no counter, options or recommendation.
     Exception, an offer whose time for acceptance has passed (summary.revive is present): a seller counter would set a new time for acceptance, so after the fixes also give the "What a Counter Could Look Like" block below. It's reference, never a recommendation. -->
**{{summary.title}}.** {{summary.why}}

{{when summary.counter:}}
**Our Counter** ({{summary.counter.summary}}):

| Term | Buyer Offered | We Counter | Why |
|---|---|---|---|
| {{row.term}} | {{row.offered}} | **{{row.counter}}** | {{row.why}} |

{{when summary.revive:}}
**If the Seller Wants This Buyer: What a Counter Could Look Like** (for reference; {{summary.revive.summary}}). {{summary.revive.note}}

| Term | Buyer Offered | A Counter Could Say | Why |
|---|---|---|---|
| {{row.term}} | {{row.offered}} | {{row.counter}} | {{row.why}} |


| | |
|---|---|
| {{each summary.kpis: kpi.label}} | **{{kpi.value}}** ({{kpi.note}}, when there is one) |
| Certainty | {{summary.certainty.score}}/100, {{summary.certainty.band}}; buyer can walk away until {{summary.certainty.walk_away_until}} ({{summary.certainty.walk_away_note}}, when there is one); biggest threat: {{summary.certainty.threat}} |

**Top Risks:** {{each summary.risks: risk.issue}}

{{when summary.terms_reason:}} **Terms Reason:** {{summary.terms_reason}}

<!-- multi mode -->
**{{summary.title}}.** {{summary.why}}

**The Plan** ({{summary.plan_summary}}):

| # | Offer | Action | Price | Net | Downside | Certainty | Buyer Can Walk | Close | Terms / Reason |
|---|---|---|---|---|---|---|---|---|---|
| {{r.rank}} | {{r.offer}} ({{r.financing}}) | {{r.action}} | {{r.price}} | {{r.net}} | {{r.downside}} | {{r.score}} | {{r.risk_days}} days | {{r.close}} | {{r.terms}} |

{{summary.plan_note}} <!-- always there: one counter or acceptance goes out at a time -->

{{when summary.terms_reason:}} **Terms Reason:** {{summary.terms_reason}}

<!-- both modes -->
**Options:** {{each summary.options: "**" + option + "**" + (" (recommended)" when recommended) + ": " + net + " · " + certainty + " · " + what}}

{{summary.preliminary, when present}}

{{when summary.respond_by_also:}} **Also Due:** {{each summary.respond_by_also: what + ", " + when; joined with "; "}}

**Next Step:** {{summary.next_step}}

**Estimated:** {{estimated_costs, joined with commas; skip when empty}}

**To Sharpen This:** {{to_confirm, as one short question; skip when empty}}

<sub>Net = after all costs and holding, {{"before mortgage payoff" when the data note says so}}. Downside = {{offers[].downside_note for the offer shown; in multi mode "if the appraisal and inspection go badly"}}. Estimates only; the title company's settlement statement governs. Commissions are negotiable and not set by law. Not legal advice.</sub>

{{the agent's disclaimers from their profile, verbatim, one line each, when there are any}}

<!-- On request only ("show me the net sheet"): one table per offer from offers[].net_sheet, columns net_sheet.columns, rows net_sheet.rows. Then list assumptions[] as "impact · where · what". -->
