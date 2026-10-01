## {{address}}: Seller Net Sheet

{{"**Preliminary:** " + preliminary_reason, when preliminary is true}}

{{facts, each text joined with " · "}} · Prepared {{prepared_date}}{{" for " + prepared_for, when there is one}}

{{each columns: label + ", " + tile_label + ": **" + tile_display + "**", joined with " · "}}

| | {{each columns: label}} |
|---|{{"---:|" for each column}}
| {{each rows: label (in bold when kind is price, subtotal or final; a group row is its label in bold with empty cells) | display, one cell per column}} |

{{each notes, one bullet each}}

_Estimates only, not legal, lending or tax advice. The title company's settlement statement gives the final figures._

{{the agent's disclaimers from their profile, verbatim, one line each, when there are any}}
