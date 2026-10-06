<!-- The full review in chat, or the markdown review when the PDF can't render. Fill it from scripts/review.py output.
     Values come from the JSON as printed; never recompute them. Offers are named by their label (offer_label,
     summary.ranked[].offer, offers[].label), never by id letter.
     One offer (mode "single"): the header, the single block once, then the closing block.
     Two or more active offers (mode "multi"), as the PDFs (a comparison plus each offer's single review): the header,
     the multi block, then for each row of summary.ranked whose rank is a number, in that order, run
     `python3 scripts/review.py listing.json [--cma file.cma.json] --mode single --offer {{r.id}}` and fill the single
     block from that output under "### {{r.offer}}"; then the closing block once, from the multi output.
     Leave out any line whose value is empty or null. -->

## Offer Review: {{property}} (List {{list_price}})

{{value_range_confirm, when present}} {{deadline_note, when present}}

<!-- ===== multi block (mode "multi") ===== -->
**{{summary.title}}.** {{summary.why}}

{{when summary.wait:}} The plan is to wait for the final offers (due {{summary.wait.due}}), then decide. {{summary.wait.fallback}}, as below.

**Respond By:** {{summary.respond_by}} ({{summary.respond_by_offer}}, when present)

{{when summary.respond_by_also:}} **Also Due:** {{each summary.respond_by_also: when + ", " + what; joined with "; "}}

**The Plan** ({{summary.plan_summary}}):

| # | Offer | Action | Price | Net | Downside | Certainty | Buyer Can Walk | Close | Terms / Reason |
|---|---|---|---|---|---|---|---|---|---|
| {{r.rank}} | {{r.offer}} ({{r.financing}}) | {{r.action}} | {{r.price}} | {{r.net}} | {{r.downside}} | {{r.score}} | {{r.risk_days + " days" when it is a number, else r.risk_days as printed}} | {{r.close}} | {{r.terms}} |

{{when any r.escalation:}} **Escalation:** {{each r with r.escalation: r.offer + ": " + r.escalation; joined with "; "}}

{{summary.plan_note}} <!-- always there: one counter or acceptance goes out at a time -->

{{when summary.counter_stance:}} **Counter Stance: {{summary.counter_stance.name}}.** {{summary.counter_stance.note}}

**Biggest Risk:**
- {{each offers[]: "**" + label + ":** " + (biggest_risk, or "None major" when null)}}

{{when summary.terms_reason:}} **Terms Reason:** {{summary.terms_reason}}

**Your Options:**

| Option | Net After Holding | Certainty | What Happens |
|---|---|---|---|
| **{{opt.option}}**{{" (recommended)" when opt.recommended}} | {{opt.net}} | {{opt.certainty}} | {{opt.what}} |

{{summary.preliminary, when present}}

**Next Step:** {{summary.next_step}}

{{summary.data_note}}

**What to Confirm:**
- {{each assumptions[]: impact (High, Med or Low) + " · " + where + " · " + what}}

<!-- ===== single block (mode "single"; under "### {{offer label}}" after the multi block) =====
     When summary.action is INCOMPLETE: the title and why, the fixes, the "What a Counter Could Look Like" block when
     summary.revive is present (reference, never a recommendation), the key numbers and certainty (labeled for
     reference), Top Risks, Next Step, the data note and the assumptions. No counter, options or recommendation. -->
**{{summary.title}}.** {{summary.why}}

**Respond By:** {{summary.respond_by}} ({{summary.respond_by_offer}}, when present)

{{when summary.respond_by_also:}} **Also Due:** {{each summary.respond_by_also: when + ", " + what; joined with "; "}}

{{when summary.fixes (INCOMPLETE):}} **Fix Before Review:**
- {{each summary.fixes: "**" + sev + ":** " + issue + " " + fix}}

{{when summary.revive:}}
**If the Seller Wants This Buyer: What a Counter Could Look Like** (for reference; {{summary.revive.summary}}). {{summary.revive.note}}

| Term | Buyer Offered | A Counter Could Say | Why |
|---|---|---|---|
| {{row.term}} | {{row.offered}} | {{row.counter}} | {{row.why}} |

{{when summary.counter:}}
**{{"Fallback Counter" when summary.wait, else "Our Counter"}}** ({{summary.counter.summary}}):

| Term | Buyer Offered | We Counter | Why |
|---|---|---|---|
| {{row.term}} | {{row.offered}} | **{{row.counter}}** | {{row.why}} |

**Counter Stance: {{summary.counter.stance.name}}.** {{summary.counter.stance.note}}

{{when summary.compare:}}
**How It Compares** (vs. {{summary.compare.vs}}, the recommended offer):

| Measure | {{summary.compare.this}} | {{summary.compare.vs}} |
|---|---|---|
| {{row[0]}} | {{row[1]}} | {{row[2]}} |

| | |
|---|---|
| {{each summary.kpis: kpi.label}} | **{{kpi.value}}** ({{kpi.note}}, when there is one) |
| Certainty | {{summary.certainty.score}}/100, {{summary.certainty.band}} |
| Buyer's Last Cancel Right | {{summary.certainty.walk_away_until}} ({{summary.certainty.walk_away_note}}, when there is one) |
| Deposit at Risk After That | {{summary.certainty.deposit}} |
| Closing | {{summary.certainty.closing}} |
| Biggest Threat | {{summary.certainty.threat}} |

**Top Risks:**
- {{each summary.risks: "**" + sev + ":** " + issue; when empty, "No significant risks found." (INCOMPLETE: "See Fix Before Review above.")}}

{{when summary.terms_reason:}} **Terms Reason:** {{summary.terms_reason}}

{{when summary.options (never INCOMPLETE):}} **Your Options:**

| Option | Net After Holding | Certainty | What Happens |
|---|---|---|---|
| **{{opt.option}}**{{" (recommended)" when opt.recommended}} | {{opt.net}} | {{opt.certainty}} | {{opt.what}} |

{{summary.preliminary, when present}}

**Next Step:** {{summary.next_step}}

{{summary.data_note}}

**What to Confirm:**
- {{each assumptions[]: impact (High, Med or Low) + " · " + where + " · " + what}}

<!-- ===== closing block (once, at the end) ===== -->
**Estimated:** {{estimated_costs, joined with commas; skip when empty}}

**To Sharpen This:** {{to_confirm, as one short question; skip when empty}}

**Notes:** {{notes, one line each; skip when empty}}

<sub>Net = after all costs and holding, {{"before mortgage payoff" when the data note says so}}. Downside = {{offers[].downside_note for the offer shown; in multi mode "if the appraisal and inspection go badly"}}. Estimates only; the title company's settlement statement governs. Commissions are negotiable and not set by law. Not legal advice.</sub>

{{the agent's disclaimers from their profile, verbatim, one line each, when there are any}}

<!-- On request only ("show me the net sheet"): one table per offer from offers[].net_sheet, columns net_sheet.columns
     (As Offered, Downside Case, then Proposed Counter, or Counter (Reference) for a lapsed offer), rows net_sheet.rows. -->
