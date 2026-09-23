# Writing the report

## Voice

Write to the homeowner ("your home"), in plain language. Every number gets a sentence saying what it means for their price or their net. No selling adjectives, and don't flatter the home: a seller who lists too high loses the first weeks, when buyer attention is highest. Give a range and a recommendation, never a promise. Write as the agent's analysis and don't mention the tools that produced it. When the agent profile has a voice section, follow it within these rules.

## Sections (the order is fixed by the script)

Page 1 summary → the home → the bottom line and what it means → comparable sales (cards, table, scatterplot) → competition → market → choosing a list price → estimated net proceeds → what your price means to buyers → before we list → what we need from you → how this was prepared.

- **Bottom line:** the range, the recommended price and why, and why a higher first price is a risk, in 4–5 sentences.
- **What this means:** expected negotiation (from the recent sale-to-list and concession data), the first-weeks window, the appraisal ceiling, and what documentation is worth.
- **Comps:** each card explains its adjustments in sentences with dollar amounts. Include the sales that argue for a lower price.
- **Competition:** 5–9 rows, actives, pendings, and any expired listing that shows what the market rejected. The notes say why each matters to this seller.
- **Market:** the table from stats.py, then 3–5 bullets that each tie a number to price or timing.
- **Pricing:** the three options as estimates, saying whether the nets are close and what really differs (time and risk). The net sheet's note names what isn't included.
- **Before we list:** low-cost steps that remove the questions that cost sellers money (roof documentation, pre-listing and insurance inspections, permits, the public record, easy showings, a seller-credit budget, a review point).
- **What we need from you:** specific, answerable requests.
- **Method:** sources with dates, then, once, that this is a broker's opinion of value and not an appraisal, that nets are estimates the closing agent will finalize, and the report's shelf life.

## Page 1 (write it last)

The flyer for sellers who won't read the report. Someone who reads only page 1 knows the recommended price, range and expected sale; the key numbers behind the price; the comps at a glance; the three options with their nets; the first three things to do; and the next step. Exactly three `key_stats`, three `why` bullets, three `first_steps`. Anything page 1 says must be supported later in the report.

## After rendering

Look at every page and slide. A chart label overlapping a marker: flip that callout's `side` or `subject_label_pos`. A heading alone at the bottom of a page or a split table shouldn't happen; if it does, shorten the intro. Change the content, never the HTML or the .pptx.
