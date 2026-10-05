# Client Wording

Everything you write into the data file can reach a client, so write it in the client's words. `render.py` checks the data file, any deck or CMA file it reads, and the profile's voice and disclaimers before it builds anything, and lists every problem at once as `field: problem → fix`. Rewrite each field it names, then render again. Missing data never stops a render: leave a field out and the report uses its default and says so once, in its notes.

## What Stops a Render

| Don't Write | Write Instead |
|---|---|
| Tool words: placeholder, JSON, data file, script, schema, re-run, export, CSV | The client's words: "estimate", "the report", "we'll update the report", "MLS records" |
| Empty or unfinished values: null, undefined, NaN, TODO, TBD | The value, or leave the field out |
| A figure in a judgment field or label: digits, `$`, `%`, a month's name | Words ("the spring sales", "After a Price Cut"): the report prints every figure itself |
| A `{placeholder}` | The words: the report fills nothing into what you write |
| Data keys in a sentence: `insurance_annual`, `closing_date` | Plain words: "yearly insurance", "closing date" |
| ISO dates in a sentence: 2026-09-26 | Sep 26, 2026 |
| Jargon (list below) | The plain words beside it |

A one-word value (`as_is`, `2026-09-26`) is data, not a sentence, and passes. Names, ids, form and rider names, addresses, links, emails and file names keep their own spelling.

## Jargon

| Term | Plain Words |
|---|---|
| DOM | days on market |
| CDOM | cumulative days on market |
| wind-mit | wind mitigation |
| CASSB, CASSB-1 | the compensation agreement with the buyer's broker |
| LTV | loan-to-value |
| DTI | debt-to-income |
| COE | closing |
| EMD | escrow deposit, or earnest money as the contract calls it |

HOA, MLS and CMA are fine: clients use them too. LTV and DTI are fine in the offer package worksheet, which only the agent sees.

## Labels

Scenario, strategy and option names, headings and tile labels are put in Title Case for you when the files are built. Write them as labels ("After a Price Cut"), not sentences, and never with a figure or an "Estimate" or "Assumed" tag: the notes say what's estimated, once.
