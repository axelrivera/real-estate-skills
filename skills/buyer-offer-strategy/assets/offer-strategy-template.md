<!-- Fill from scripts/strategy.py output. Every value comes from the JSON as printed; never recompute or reword one.
     The full answer is the block down to the disclaimers; the sections after it are on request only.
     chat_notes (the best-effort line for a contract that isn't FAR/BAR) goes in chat, word for word, in its own paragraph after the answer; never in a saved markdown report. -->

## Offer Options: {{property}} (List {{list_price}})

**{{summary.kicker}}: {{summary.outlook}}.** {{summary.why}}

**Submit By:** {{summary.submit_by}} · **Competition:** {{summary.signal}} · **Your Limits:** {{summary.limits}}{{" · **Buyer's Priority:** " + summary.priority.name when summary.priority.line}}

{{each summary.tiles: "**" + label + "** " + value + " (" + sub + ")", joined with " · "}}

| Term | Offer | Why |
|---|---|---|
| {{t.term}} | **{{t.offer}}**{{on the Price row only: " (" + summary.price_note + ")"}} | {{t.why}}{{" (Agent)" when t.agent}} |

**{{summary.options_title}}** ({{summary.options_sub}})

| Option | Price | Outlook | Seller Net* | Worst-Case Cash | Reserve | What Changes |
|---|---|---|---|---|---|---|
| {{o.option}} | {{o.price}} | {{o.outlook}} | {{o.seller_net}} | {{o.worst_cash}} | {{o.reserve}} | {{o.what}} |

{{each summary.absent: "**" + label + "** " + why, one line each; skip when empty}}
{{"**Higher Price:** " + summary.higher_price; skip when empty}}

**How It Stacks Up** (By Competition Level)

| If the Seller Has… | {{each summary.option_labels, one column each}} |
|---|---|
| {{b.level}} | {{each b.values: value.band, one column each}} |

{{each reply_lines except keys "tight_reserve" (it's summary.cautions, below) and "higher_price" (above): text, one line each; skip when empty}}

**Your Exposure: Recommended Offer**

| Item | Amount |
|---|---|
| {{e.label, for each entry e of summary.exposure}} | {{e.value}} |

{{each summary.constraints: "**Limit:** " + text}}

{{each summary.cautions: text, one line each; skip when empty}}

{{summary.preliminary, when present}}

**Next Step:** {{summary.next_step}}

**To Sharpen This:** {{to_confirm, as one short question; skip when empty}}

<sub>*Seller net before mortgage payoff, as a listing agent would calculate it. Financing: {{summary.financing}}. {{notes, each once, in order}}</sub>

{{the agent's disclaimers from their profile, verbatim, one line each, then the brokerage's license, office address and phone in one line when the profile has them; skip when there are none}}

<!-- On request only, each when the agent asks for it. An on-request answer given on its own (no full answer above it) ends with the same disclaimers line. -->

### Options Side by Side

| Term | {{each summary.option_labels, one column each}} |
|---|---|
| {{row.term}} | {{each row.values, one column each}} |

<!-- side_by_side[] in order; its last row (key "payment") is the monthly payment. With one option, title it "Offer Terms". -->

### Market Check

| Item | Value |
|---|---|
| {{m.label}} | {{m.value}}{{" (" + m.note + ")" when m.note}} |

<!-- One row per entry m of market_check[], in order. -->

### Likely Pushback (On the Recommended Offer)

| Term | Yours | They May Ask | Response |
|---|---|---|---|
| {{p.term}} | {{p.yours}} | {{p.ask}} | {{p.response}} |

<!-- One row per entry p of pushback[]. When pushback is empty, write detail.pushback_none instead. -->

### Assumptions and Data to Confirm

| Impact | Where | What to Confirm |
|---|---|---|
| {{a.impact_label}} | {{a.where}} | {{a.what}} |

<!-- One row per entry a of assumptions[]. When assumptions is empty, write instead: "All key inputs provided." -->

<!-- On request only: the worksheet ("contract entries", "the worksheet", "the package"). It holds offer terms only, never the buyer's limits, cash or reserve, so the agent can forward it on its own. -->

## Offer Package Worksheet: {{worksheet.option}} Offer at {{worksheet.price}}

**Draft for the Agent.** Enter in {{worksheet.software}} and {{"verify every paragraph and rider against the current FAR/BAR form version" when worksheet.farbar, else "match each entry to your contract by name (paragraph numbers vary by form)"}}. Text in [brackets] is a blank to fill. Suggested language is for broker review, not legal advice.

**Contract Form:** {{worksheet.form_name}}. {{worksheet.form_why}}

### Contract Entries

| Para. | Field | Enter | Note |
|---|---|---|---|
| {{x.para}} | {{x.field}} | {{x.entry}} | {{x.note}} |

<!-- The Para. column only when worksheet.farbar; otherwise Field | Enter | Note. -->

### Riders to Attach (With Suggested Inputs)

| Rider | Suggested Inputs | Why |
|---|---|---|
| {{x.rider}} | {{x.inputs}} | {{x.why}} |

<!-- When worksheet.riders is empty, write instead: "No riders needed." -->

### Additional Terms (Draft Language)

{{each worksheet.clauses: "**" + title + ":** " + text, the text quoted as written; skip the heading when empty}}

### Offer Package Checklist

{{each group of worksheet.package, in order: "**" + group + "**", then one line per item:
  status Yes, Done, True or ✓: "- [x] " + item
  status Never: "- ✕ " + item (a thing to leave out, never a checkbox)
  any other status: "- [ ] " + item
  then " (" + note + ")" when the item has a note}}

### Request from the Seller After Acceptance

{{each worksheet.docs: "- [ ] " + doc}}
