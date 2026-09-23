# Method: intake, comps, range, pricing strategies

## Intake checklist

Ask for what's missing in one message; use tappable choices for occupancy, timeline and pool when the runtime offers them.

**From the seller (about the home)**
1. Address.
2. Beds, full and half baths, heated square feet, lot size, year built, construction (block or frame).
3. Pool (private or none), garage spaces, HOA and CDD (amounts, or none). An HOA adds an estoppel letter to the net sheet.
4. Updates with approximate dates: roof, AC, water heater, kitchen, baths, flooring, windows, electrical, plumbing, pool surface and equipment, and whether permits were pulled. Documented updates are worth money; claims aren't.
5. The current annual tax bill.
6. Known issues or past insurance claims. Most states require sellers to disclose known material defects, and they affect the price.
7. Timeline to close, and whether the home will be occupied or vacant for showings.
8. Mortgage payoff (optional): with it, the net sheet ends in estimated cash at closing.

**From the agent**
9. The MLS CMA export (CSV) of single-family homes nearby: sales from about the last 6 months, plus active, pending, expired and canceled listings. For Stellar the columns are built in; another MLS needs its columns mapped in the market profile.
10. Brokerage terms (listing fee and buyer's agent compensation, if the seller will offer it). Without them the market's default is used and labeled a placeholder (Florida: 2.5% + 2.5%). Outside the built-in market, ask; never borrow Florida's.
11. Flood zone, if known. Otherwise write "to confirm".

If the seller knows only some dates, go ahead and list the rest under "What we need from you". Never guess a roof date, a permit, or a tax amount.

## Comps

From `stats.py`'s `sold_candidates`, choose 3–6 sales: same subdivision first, then a comparable neighborhood within about a mile; within about 20% of the size, same pool status, similar age and construction, closed within about 6 months. Include the sales that argue for a lower price; the seller's next agent will show them anyway.

Judge each comp's condition from its remarks and compare it with the seller's described updates (never with an old listing of the subject). Say that condition adjustments are judgment calls based on listing text.

## Adjustments

Default rates come from the market profile (`cma.adjustments`; built in for Florida: about $75/sq ft for differences under ~300 sq ft, $25,000 for a private pool, $40,000–45,000 full renovation vs. dated, ~$30,000 full vs. partial, –$5,000 for documented recent systems the seller can't yet document (reverse it once they do), –$5,000 to –$10,000 for a noticeably better lot or water, 1–2% per quarter when the market has softened and 0 for sales in the last ~6 weeks). Outside the built-in market, use the agent's values or ask for local norms. Explain any departure in `method_note`.

- Subtract seller-paid buyer costs from the sale price, dollar for dollar.
- Compute adjusted values with Python, not in your head.
- Write each adjustment as a sentence with its dollar amount, to the seller: "It sold in April, when rates were lower: minus about $10,000."

## Range and recommended price

- **Supported range:** a judgment around the median adjusted value, typically about $25,000 wide (`cma.typical_range_width`). Widen it when comps disagree.
- **Recommended list price:** near the middle of the range, usually just under a round number ($469,900). The first two to three weeks bring the most showings: a price buyers see as fair turns them into offers, an ambitious one turns into a later cut from a weaker position. compute.py warns when it falls outside the range.
- **Appraisal ceiling:** name the highest similar sale. A contract well above it invites a low appraisal.

## The three pricing strategies

1. **Top of the range:** longer to contract, a likely price cut, and an expected sale near the middle anyway.
2. **Recommended:** the middle of the range, with room for the negotiating the data shows.
3. **Competing-offer price:** just below the middle; fast, possibly with a smaller seller credit, and only if competing offers actually show up. Say so.

Base each option's expected sale on the adjusted comps first (they already reflect what similar homes sold for, net of credits), then check it against stats.py's recent sale-to-original-list ratio: that ratio includes overpriced listings, so applied to a well-priced home it runs low. The recommended option usually expects about 97–99% of its list price in a balanced market; the top-of-range option less. Time to contract and the assumed seller credit come from recent days on market and the share and size of seller-paid costs. Label them estimates. If one option comes out ahead only because of an assumption (a smaller credit), say that in `pricing.note`; the table shouldn't suggest precision it doesn't have.

## The scatterplot

List in `scatter.renovated` the sold private-pool homes that are genuinely renovated (be conservative: "well maintained" doesn't count). Pick 1–3 callouts, usually the top comp and the strongest active competitor. The subject is plotted at the recommended list price; the script draws the rest, the size-only trend line, and lists homes left off the chart.
