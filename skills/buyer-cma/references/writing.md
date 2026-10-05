# Writing the Report

## Voice

When the agent's profile has a `Voice` section, match its tone and word choice in the prose you write; the rules below and the Guardrails still win.

Every number gets a sentence saying what it means for this buyer. Short sentences. No selling words ("stunning", "must-see"). A range, never a single number presented as fact. Write as the agent's analysis and don't mention the tools that produced it. When the agent's profile has a voice section, follow it within these rules.

**Style and fair housing:** follow the Guardrails in SKILL.md: no em dashes, labels in Title Case, and describe the home and the numbers, never people (`references/fair-housing.md`).

## Sections (the Order Is Fixed by the Script)

Page 1 summary → the home → bottom line (+ history, offer plan, negotiating points) → comps → scatterplot → competition → market → costs (taxes, insurance, payment, price vs. credit) → watch items and questions → method.

- **Every figure is the script's.** Each count, price, percent, date and comparison in the report is a sentence the script writes from the numbers (where asking sits, the history's counts, the comps' dates, the market table, the costs). What you write is the judgment around them, with no figures: "the earlier sales", "repeated price cuts", "most sellers here help with costs". compute.py stops on a figure in a judgment field and names it.
- **Bottom line:** `why`, 2–3 sentences: why the range sits where it does and which sales it leans on. The script states the range, where asking sits in it and the median.
- **History:** `takeaway`: what the history adds up to and the question it raises. The script writes the heading, the counts and the table, so never restate a count.
- **Credit and cash:** the script says what each $5,000 of credit saves at closing and adds a month, and what the credit alternative saves; `takeaway` says which trade-off suits this buyer.
- **Where a value sits:** never place a price in the range in your own words. A figure you'd work out in a sentence (a price plus one adjustment) goes where the script computes it: a comp card's adjustments, or for a competing listing `competition.adjustments` (the script adds the adjusted price and where it sits to that row's note).
- **Competition:** 5–9 rows: actives, pendings, and any expired or canceled listing that shows what the market rejected. The notes column says why each one matters to this buyer.
- **Market:** the script's table from the export, then 3–5 bullets, each a finding and what it means for the offer, in words.
- **Costs:** the seller's bill against the buyer's estimate, the escrow warning, insurance drivers, the payment table, price vs. credit.
- **Watch items:** roof first when unknown or unproven, then era-specific systems, permits, bedroom-count discrepancies, a failed prior contract, and what the As-Is contract means, written conditionally ("If the offer is written on the As-Is contract, ...") unless the public remarks say As-Is: a seller's preference in Realtor Information or Realtor Remarks stays with the agent (`listing-sheet.md`). Questions for the listing agent: 5–7, specific and answerable.
- **Sources:** name any source beyond the export in `sources`; the script lists the export's sales and listings, the shelf life and, once in the closing notices, that this is a broker's opinion of value and not an appraisal.

## Page 1 (Write It Last)

The flyer for buyers who won't read the report. Someone who reads only page 1 knows the opening offer with target and walk-away, the range and where asking sits, the key numbers, the comps at a glance, what the home really costs them, the three things to check, and the next step.

Three `why` bullets (under about 25 words each), three `check_first` items and a headline under about 25 words, all without figures. The key numbers, the dot plot, the tax and payment figures and the payment tile are the script's.

## After Rendering

Look at every page. A chart label overlapping a marker: flip that callout's `side`. A heading alone at the bottom of a page or a split table shouldn't happen; if it does, shorten the intro. A mostly empty page is fine when a section moved to a fresh page. Change the content, never the HTML.

**Other listings' remarks.** Describe each comp and competing listing in your own words from the data fields (beds, baths, size, pool, updates the remarks name). Never quote or closely paraphrase another agent's public remarks in a client report: MLS rules often limit reproducing them, and they're the listing agent's marketing, not facts.
