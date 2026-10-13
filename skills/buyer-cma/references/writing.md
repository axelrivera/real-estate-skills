# Writing the Report

## Voice

When the agent's profile has a `Voice` section, match its tone and word choice in the prose you write; the rules below and the Guardrails still win.

The report is an objective analysis of value: what the comps, the history and the market show, including the parts that argue against buying or against a lower price. It never tells the buyer what to offer or how to negotiate; that's the buyer offer strategy's. Every number gets a sentence saying what it means for this buyer. Short sentences. No selling words ("stunning", "must-see"). A range, never a single number presented as fact. Write as the agent's analysis and don't mention the tools that produced it. When the agent's profile has a voice section, follow it within these rules.

**Style and fair housing:** follow the Guardrails in SKILL.md: no em dashes, labels in Title Case, and describe the home and the numbers, never people (`references/fair-housing.md`).

## Sections (the Order Is Fixed by the Script)

Page 1 summary → the home → bottom line (+ history) → comps → scatterplot → competition → market → costs (taxes, insurance, payment) → watch items and questions → method.

- **Every figure is the script's.** Each count, price, percent, date and comparison in the report is a sentence the script writes from the numbers (where asking sits, the history's counts, the comps' dates, the market table, the costs). What you write is the judgment around them, with no figures: "the earlier sales", "repeated price cuts", "most sellers here help with costs". compute.py stops on a figure in a judgment field and names it. A count in words is a figure too ("twice", "five nearby sales", "came down three times"): say "repeated", "several" or "the closest sales" instead.
- **Bottom line:** `why`, 2–3 sentences: why the range sits where it does and which sales it leans on. The script states the range, where asking sits in it and the median.
- **History:** `takeaway`: what the history adds up to and the question it raises. The script writes the heading, the counts and the table, so never restate a count.
- **Where a value sits:** never place a price in the range in your own words. A figure you'd work out in a sentence (a price plus one adjustment) goes where the script computes it: a comp card's adjustments, or for a competing listing `competition.adjustments` (the script adds the adjusted price and where it sits to that row's note).
- **Scatterplot:** `takeaway`: what the chart says about this home's value, in words. The script's sentence right above it states how much size explains the sale prices, so never restate it or say it differently.
- **Competition:** 5–9 rows: actives, pendings, and any expired or canceled listing that shows what the market rejected. The notes column says why each one matters to this buyer.
- **Market:** the script's table from the export, then 3–5 bullets, each a finding and what it means for this home's value, in words. "Homes now sell under their original asking price", never "sellers expect to negotiate".
- **Costs:** the seller's bill against the buyer's estimate, the escrow warning, insurance drivers, the payment table (at asking, with the total at the median adjusted value beside it when that's lower).
- **Watch items:** roof first when unknown or unproven, then era-specific systems, permits, bedroom-count discrepancies, a failed prior contract, and what the As-Is contract means, written conditionally ("If the offer is written on the As-Is contract, ...") unless the public remarks say As-Is: a seller's preference in Realtor Information or Realtor Remarks stays with the agent (`listing-sheet.md`). Questions for the listing agent: 5–7, specific and answerable.
- **Sources:** name any source beyond the export in `sources`; the script lists the export's sales and listings, the shelf life and, once in the closing notices, that this is a broker's opinion of value and not an appraisal.

## Page 1 (Write It Last)

The flyer for buyers who won't read the report. Someone who reads only page 1 knows the supported range, where asking sits against it and the median, the key numbers, the comps at a glance, what the home really costs them, the three things to check, and the next step.

Three `why` bullets (the reasons for the range, under about 25 words each), three `check_first` items and a headline under about 25 words, all without figures and without offer advice. The headline gives the one fact that explains the value: "Renovated Spring Oaks pool homes of the same size set the value; this one's roof age is unknown", never "Open at the bottom of the range". Where asking sits is the script's sentence right above it, so the headline never says it (no "asking", "above", "below", "inside", "top", "bottom", "middle" or "median": compute.py stops on them), and write it after compute.py has printed the range. The `next_step` may point to building the offer options. The range, the key numbers, the dot plot, the tax and payment figures and the payment tile are the script's.

## After Rendering

Look at every page. A chart label overlapping a marker: flip that callout's `side`. A heading alone at the bottom of a page or a split table shouldn't happen; if it does, shorten the intro. A mostly empty page is fine when a section moved to a fresh page. Change the content, never the HTML.

**Other listings' remarks.** Describe each comp and competing listing in your own words from the data fields (beds, baths, size, pool, updates the remarks name). Never quote or closely paraphrase another agent's public remarks in a client report: MLS rules often limit reproducing them, and they're the listing agent's marketing, not facts.
