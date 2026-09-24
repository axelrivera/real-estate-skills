## Contract Timeline: {{property}} ({{Side}} View)

**{{effective.short}} → {{closing.short}} · {{length_days}} days.** {{one or two sentences: for the buyer view "Your main protections run through {{contingencies_end.display}} ({{contingencies_end.short}})." For the seller view "The buyer's main contingencies end {{contingencies_end.display}} ({{contingencies_end.short}})." When open_rights has items, add "These rights stay open after that: {{open_rights, joined}}." and never call the deal firm; otherwise add "After that the deposit is at risk" (buyer) or "After that the deal is firm unless the buyer defaults" (seller). If there's no contingency, say so.}}

| Date | Day | Deadline | Who | Action | If Missed |
|---|---|---|---|---|---|
| {{row.display}} | {{row.day}} | {{row.label}}{{" · was " + row.was when it moved}}{{" ★" when row.critical}} | {{row.party}} | {{row.action}} | {{row.if_missed}} |

{{one line per pending (on-event) item: "**{{label}}:** {{rule}}."}}

**Check Before Relying on These Dates:**
- {{each flag, in plain words}}
- {{each agent note, in plain words (chat only; they are not on the PDF)}}

★ Critical = missing it can cost a contract right or put the deposit at risk. Effective Date {{effective.display}} ({{effective.source}}). Dates follow {{rules.family}}; confirm them with the escrow or title agent.

{{the agent's disclaimers from their profile, verbatim, one line each, when there are any}}
