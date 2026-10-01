# Writing the Report

## Voice

When the agent's profile has a `Voice` section, match its tone and word choice in the prose you write; the rules below and the Guardrails still win.

Every number gets a sentence saying what it means for this buyer. Short sentences. No selling words ("stunning", "must-see"). A range, never a single number presented as fact. Write as the agent's analysis and don't mention the tools that produced it. When the agent's profile has a voice section, follow it within these rules.

**Style and fair housing:** follow the Guardrails in SKILL.md: no em dashes, labels in Title Case, and describe the home and the numbers, never people (`references/fair-housing.md`).

## Sections (the Order Is Fixed by the Script)

Page 1 summary → the home → bottom line (+ history, offer plan, negotiating points) → comps → scatterplot → competition → market → costs (taxes, insurance, payment, price vs. credit) → watch items and questions → method.

- **Bottom line:** the range, then where asking sits within it and why, in 3–4 sentences. The section the buyer reads first.
- **History:** a finding as the heading ("On the Market Since January"), the table (built from `history.events`), then what it adds up to and the question it raises. Quote the counts with their placeholders ("{active_days} of active marketing, with {price_cuts}"), never a number you counted. Every claim about the history anywhere in the report (negotiating points, page 1, the bottom line) must match its numbers: compare the price now with an earlier one through a placeholder ("asking is {vs_last_contract} the {last_contract_price} it was listed at when the last contract was signed"), or check both prices in the events before writing "above", "below" or "back to".
- **Credit and cash:** a sentence about cash saved at closing quotes `{credit_alt_cash_saved}` or `{credit_cash_per_5k}`, never the credit itself: a credit paid for with a higher price saves less than its face amount.
- **Where a value sits:** "near the bottom of the range", "inside it" or "above it" is checked against both ends of the range with a computed number: the card's adjusted value, `{median_adjusted}`, or the asking position compute.py prints. A figure you work out in a sentence (a sale price plus one adjustment) goes in a comp card's adjustments so the script computes it, or is compared with both ends before you write where it sits.
- **Market numbers:** quote months of supply with `{months_supply}`, never rounded into words by hand ("about a month and a half" for 1.3 months).
- **Competition:** 5–9 rows: actives, pendings, and any expired or canceled listing that shows what the market rejected. The notes column says why each one matters to this buyer.
- **Market:** the table from stats.py, then 3–5 bullets that each tie a number to the offer.
- **Costs:** the seller's bill against the buyer's estimate, the escrow warning, insurance drivers, the payment table, price vs. credit.
- **Watch items:** roof first when unknown or unproven, then era-specific systems, permits, bedroom-count discrepancies, a failed prior contract, and what As-Is really means. Questions for the listing agent: 5–7, specific and answerable.
- **Method:** sources with dates, then, once, that this is a broker's opinion of value and not an appraisal, and the report's shelf life.

## Page 1 (Write It Last)

The flyer for buyers who won't read the report. Someone who reads only page 1 knows the opening offer with target and walk-away, the range and where asking sits, the key numbers, the comps at a glance, what the home really costs them, the three things to check, and the next step.

Exactly three `key_stats`, three `why` bullets (under about 25 words each), three `check_first` items; a headline under about 25 words. Write "about", never a tilde, for an approximate number. The dot plot, tax and payment figures and the payment tile are computed, so never type those numbers into `summary_page`.

## After Rendering

Look at every page. A chart label overlapping a marker: flip that callout's `side`. A heading alone at the bottom of a page or a split table shouldn't happen; if it does, shorten the intro. A mostly empty page is fine when a section moved to a fresh page. Change the content, never the HTML.

**Other listings' remarks.** Describe each comp and competing listing in your own words from the data fields (beds, baths, size, pool, updates the remarks name). Never quote or closely paraphrase another agent's public remarks in a client report: MLS rules often limit reproducing them, and they're the listing agent's marketing, not facts.
