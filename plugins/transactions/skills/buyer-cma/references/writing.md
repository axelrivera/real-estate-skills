# Writing the report

## Voice

When the agent profile has a `Voice` section, match its tone and word choice in the prose you write; the rules below and the Guardrails still win.

Every number gets a sentence saying what it means for this buyer. Short sentences. No selling words ("stunning", "must-see"). A range, never a single number presented as fact. Write as the agent's analysis and don't mention the tools that produced it. When the agent profile has a voice section, follow it within these rules.

**Style and fair housing:** follow the Guardrails in SKILL.md: no em dashes, labels in Title Case, and describe the home and the numbers, never people (`references/fair-housing.md`).

## Sections (the order is fixed by the script)

Page 1 summary → the home → bottom line (+ history, offer plan, negotiating points) → comps → scatterplot → competition → market → costs (taxes, insurance, payment, price vs. credit) → watch items and questions → method.

- **Bottom line:** the range, then where asking sits within it and why, in 3–4 sentences. The section the buyer reads first.
- **History:** a finding as the heading ("On the Market Since January"), the table, then what it adds up to and the question it raises.
- **Competition:** 5–9 rows: actives, pendings, and any expired or canceled listing that shows what the market rejected. The notes column says why each one matters to this buyer.
- **Market:** the table from stats.py, then 3–5 bullets that each tie a number to the offer.
- **Costs:** the seller's bill against the buyer's estimate, the escrow warning, insurance drivers, the payment table, price vs. credit.
- **Watch items:** roof first when unknown or unproven, then era-specific systems, permits, bedroom-count discrepancies, a failed prior contract, and what As-Is really means. Questions for the listing agent: 5–7, specific and answerable.
- **Method:** sources with dates, then, once, that this is a broker's opinion of value and not an appraisal, and the report's shelf life.

## Page 1 (write it last)

The flyer for buyers who won't read the report. Someone who reads only page 1 knows the opening offer with target and walk-away, the range and where asking sits, the key numbers, the comps at a glance, what the home really costs them, the three things to check, and the next step.

Exactly three `key_stats`, three `why` bullets (under ~25 words each), three `check_first` items; a headline under ~25 words. The dot plot, tax and payment figures and the payment tile are computed, so never type those numbers into `summary_page`.

## After rendering

Look at every page. A chart label overlapping a marker: flip that callout's `side`. A heading alone at the bottom of a page or a split table shouldn't happen; if it does, shorten the intro. A mostly empty page is fine when a section moved to a fresh page. Change the content, never the HTML.

**Other listings' remarks.** Describe each comp and competing listing in your own words from the data fields (beds, baths, size, pool, updates the remarks name). Never quote or closely paraphrase another agent's public remarks in a client report: MLS rules often limit reproducing them, and they're the listing agent's marketing, not facts.
