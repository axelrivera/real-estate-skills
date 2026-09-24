# Method: intake, comps, range, pricing strategies

## Intake checklist

Ask for what's missing in one message; use tappable choices for occupancy, timeline and pool when the runtime offers them.

**From the seller (about the home)**
1. Address.
2. Beds, full and half baths, heated square feet, lot size, year built, construction (block or frame).
3. Pool (private or none), garage spaces, HOA and CDD (amounts, or none). An HOA adds an estoppel letter to the net sheet. A condo also gets the association questions in `condo.md` (milestone inspection and SIRS status, special assessments, reserves, lender approval).
4. Updates with approximate dates: roof, AC, water heater, kitchen, baths, flooring, windows, electrical, plumbing, pool surface and equipment, and whether permits were pulled. Documented updates are worth money; claims aren't.
5. The current annual tax bill.
6. Known issues or past insurance claims. Most states require sellers to disclose known material defects, and they affect the price.
7. Flood history: any flood damage while they've owned it, flood insurance claims (including NFIP), and flood assistance (including FEMA). Where the market profile has `flood.seller_disclosure` (Florida: s. 689.302), the seller signs that disclosure at or before the contract, so collect the answers now and list the form under "What We Need from You".
8. Timeline to close, and whether the home will be occupied or vacant for showings.
9. Mortgage payoff (optional): ask for the lender's payoff statement (`mortgage_payoff`). A balance from a monthly statement understates it: give it as `mortgage_balance` with `mortgage_rate` and compute.py adds a month's interest and a $500 fee cushion, labeled an estimate. With either, the net sheet ends in estimated cash at closing.

**From the agent**
10. The MLS CMA export (CSV) of single-family homes nearby: sales from about the last 6 months, plus active, pending, expired and canceled listings. For Stellar the columns are built in; another MLS needs its columns mapped in the market profile.
11. Brokerage terms (listing fee and buyer's agent compensation, if the seller will offer it). Without them the agent's standard terms from their market profile are used and marked; with neither, ask (nothing is built in, in any state).
12. Flood zone, if known. Otherwise write "to confirm". Never tell the seller that buyers won't need flood insurance: lenders require it in zones A and V, and in Florida Citizens requires it on many policies outside them (see the market profile's `flood` notes).

If the seller knows only some dates, go ahead and list the rest under "What We Need from You". Never guess a roof date, a permit, or a tax amount.

## Comps

For a condo, choose and adjust comps by `condo.md` instead of the rules below.

From `stats.py`'s `sold_candidates`, choose 3–6 sales: same subdivision first, then a comparable neighborhood within about a mile; within about 20% of the size, same pool status, similar age and construction, closed within about 6 months. Include the sales that argue for a lower price; the seller's next agent will show them anyway.

Each candidate carries `flags`: `distressed` (REO, short sale, auction) and `new_construction`. Leave those out unless the market is mostly distressed or new construction (or the subject is), then adjust for it and explain why in `method_note`. The ranking already favors recent, close sales; `more_candidates` counts the ones not listed (re-run stats.py with `--limit 30` to see them). Pass `--as-of` with the date the export was pulled so months of supply runs to that day.

Judge each comp's condition from its remarks and compare it with the seller's described updates (never with an old listing of the subject). Say that condition adjustments are judgment calls based on listing text.

## Adjustments

Default rates come from the market profile (`cma.adjustments`; built in for Florida: about $75/sq ft for differences under ~300 sq ft, $25,000 for a private pool, $40,000–45,000 full renovation vs. dated, ~$30,000 full vs. partial, –$5,000 when a comp has documented recent systems (roof, AC) that the seller's home can't match; the seller's own recent updates earn no credit until they're documented, –$5,000 to –$10,000 for a noticeably better lot or water, 1–2% per quarter when the market has softened and 0 for sales in the last ~6 weeks). Outside the built-in market, use the agent's values or ask for local norms. Explain any departure in `method_note`.

The built-in rates are flat dollars from Central Florida sales in one price band (`cma.calibrated_for`). compute.py warns when the home is outside that area or band: then derive the rates from paired sales in the export, or use the agent's, and scale flat amounts (a pool, a renovation) to the price. There are no built-in rates for garage spaces, bedroom or bath count, age, view, or size differences over about 300 sq ft: derive those from paired sales and say so, or leave the difference to the range and explain it.

- Subtract seller-paid buyer costs from the sale price, dollar for dollar.
- List each comp's adjustments in the report data (`sold_price`, `seller_concessions`, `adjustments`); compute.py does the arithmetic and fills the card and the summary table from the same numbers. More than about 15% net or 25% gross of the sale price (common appraisal guidelines) means a weak comp: replace it, or explain why it stays.
- Write each adjustment as a sentence with its dollar amount, to the seller: "It sold in April, when rates were lower: minus about $10,000."

## Range and recommended price

- **Supported range:** a judgment around the median adjusted value, typically about $25,000 wide (`cma.typical_range_width`). Widen it when comps disagree.
- **Recommended list price:** near the middle of the range. Mind portal search brackets: buyers filter in steps ($25,000 under $1M, $50,000 to $100,000 above), so $469,900 drops out of a "$470,000 and up" search and $475,000 drops out of "up to $470,000". Pick the side of the bracket where the likely buyers search; just under a round number ($469,900) is the usual choice. The first two to three weeks bring the most showings: a price buyers see as fair turns them into offers, an ambitious one turns into a later cut from a weaker position. compute.py warns when it falls outside the range.
- **Appraisal ceiling:** name the highest similar sale. A contract well above it invites a low appraisal.

## The three pricing strategies

1. **Top of the range:** longer to contract, a likely price cut, and an expected sale near the middle anyway.
2. **Recommended:** the middle of the range, with room for the negotiating the data shows.
3. **Competing-offer price:** just below the middle; fast, possibly with a smaller seller credit, and only if competing offers actually show up. Say so.

Base each option's expected sale on the adjusted comps first (they already reflect what similar homes sold for, net of credits), then check it against stats.py's recent sale-to-original-list ratio: that ratio includes overpriced listings, so applied to a well-priced home it runs low. The recommended option usually expects about 97–99% of its list price in a balanced market; the top-of-range option less. Time to contract and the assumed seller credit come from recent days on market and the share and size of seller-paid costs. Write `time` as a range with its unit ("3–6 weeks"), or give `months_to_contract`: compute.py turns it into holding costs (loan interest, HOA, insurance, utilities) and shows the net after holding, so a slower, higher price is compared fairly. Label them estimates. If one option comes out ahead only because of an assumption (a smaller credit), say that in `pricing.note`; the table shouldn't suggest precision it doesn't have.

## The scatterplot

List in `scatter.renovated` the sold private-pool homes that are genuinely renovated (be conservative: "well maintained" doesn't count). Pick 1–3 callouts, usually the top comp and the strongest active competitor. The subject is plotted at the recommended list price; the script draws the rest, the size-only trend line, and lists homes left off the chart.
