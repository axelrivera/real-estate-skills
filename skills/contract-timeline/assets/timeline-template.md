## Contract Timeline: {{property}} ({{Side}} View){{" · What-If" when what_if}}

**{{effective.short}} → {{closing.short}} · {{length_days}} days.**{{or, when closing is null (a short sale before approval): "**{{effective.short}} → closing {{short_sale.closing_days}} days after the short sale approval.**"}} {{one or two sentences: for the buyer view "Your main protections run through {{contingencies_end.display}} ({{contingencies_end.short}})." For the seller view "The buyer's main contingencies end {{contingencies_end.display}} ({{contingencies_end.short}})." When open_rights has items, add "These rights stay open after that: {{open_rights, joined}}." and never call the deal firm; otherwise add "After that the deposit is at risk" (buyer) or "After that the deal is firm unless the buyer defaults" (seller). When contingencies_waiting has items (a short sale before approval), say instead "The contingency periods ({{contingencies_waiting, joined}}) start when the buyer receives the short sale approval." If there's no contingency, say so.}} {{when first_deadline is set: "Next deadline: {{first_deadline.label}}, {{first_deadline.date_display}}."}}

| Date | Day | Deadline | Who | Action | If Missed |
|---|---|---|---|---|---|
| {{row.display}} | {{row.day}} | {{row.label}}{{" · was " + row.was when it moved}}{{" ★" when row.critical and not row.done}}{{" · " + row.done_display when row.done}}{{" · " + row.past_display when row.past}} | {{row.party}} | {{row.action}} | {{row.if_missed}} |

{{one line per pending item: "**{{label}}:** {{rule}}."}}

**Check Before Relying on These Dates:**
- {{each flag, in plain words; flags only: agent_notes and chat_notes never go in this timeline, they go in your reply to the agent after it}}

★ Critical = missing it can cost a contract right or put the deposit at risk. Effective Date {{effective.display}} ({{effective.source}}). Dates follow {{rules.family}}; confirm them with the escrow or title agent.

{{the agent's disclaimers from their profile, verbatim, one line each, when there are any}}
