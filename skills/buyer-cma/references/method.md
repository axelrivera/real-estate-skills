# Method: History, Comps, Adjustments, Chart

## The Subject

Pull the ten facts for the fact grid (see `report-data.md`). Note anything unusual about the sale: vacant, trust, estate or LLC owner, listing agent related to the owner, As-Is contract, proof of funds required, "may be temporarily off market".

## The Listing History

The MLS history grid lists every change across MLS numbers, newest first: read it bottom to top. The status codes and what they mean are in the MLS layer (`mls_format.history_codes`; for Stellar: NEW, DECR/INCR, TOM/BOM, PNC, SLD, CANC/EXP/WDN).

- A new MLS number resets days on market. Look for older numbers below it and report the true timeline: first list date, total active days across all listings, every price change.
- A pending followed by anything other than a sale means a contract failed. That's a question for the listing agent, not an assumption about the house.
- Repeated off/back-on-market pairs usually mean a seller managing showings or pausing to reset.
- A price increase after a failed contract is a signal worth naming.

Search the address: earlier syndicated remarks sometimes claim things (a "brand-new roof") that later vanish from the listing. That's a watch item.

## Choosing Comps

For a condo, choose and adjust comps by `condo.md` instead of the rules below.

From `stats.py`'s `sold_candidates`, pick 3–6 sales:

- same subdivision first, then an immediately comparable neighborhood within about a mile;
- within about 20% of the subject's size, same pool status, similar age and construction, closed within about 6 months.

Include the sales that hurt a low offer. The buyer will find them anyway, and a report that hides them loses its credibility.

Each candidate carries `flags`: `distressed` (REO, short sale, auction) and `new_construction`. Leave those out unless the market is mostly distressed or new construction (or the subject is), then adjust for it and explain why in `method_note`. The export holds the property types the agent chose to compare. Single-family homes and townhouses can be compared when they overlap in size and price, so neither is dropped: the ranking puts the subject's type first, then close types, and puts condos, 55+ communities, leased land, a different waterfront status or a different number of stories lower. `sold_by_type` shows the mix; when the comps span types, say so in `method_note`. Duplicate sale records are already dropped (see `market_notes`), and a relisted home shows once in the competition with `listings` and `earlier_prices`. The ranking already favors recent, close sales; `more_candidates` counts the ones not listed (re-run stats.py with `--limit 30` to see them). Pass `--as-of` with the date the export was pulled so months of supply runs to that day.

## Adjusting

Judge each comp's condition from its remarks (renovated, partially updated, maintained, needs work), and say that condition adjustments are judgment calls based on listing text.

Default rates come from the built-in market (`cma.adjustments`; built in for Florida: about $75/sq ft for differences under ~300 sq ft, $25,000 for a private pool, $40,000–45,000 full renovation vs. dated, ~$30,000 full vs. partial, –$5,000 for documented recent systems the subject can't match, –$5,000 to –$10,000 for a noticeably better lot or water, 1–2% per quarter when the market has softened and 0 for sales in the last ~6 weeks). Outside the built-in market, derive the rates from paired sales in the export, scaled to the price, and say so. Explain any departure in `method_note`.

The built-in rates are flat dollars from Central Florida sales in one price band (`cma.calibrated_for`). compute.py warns when the home is outside that area or band: then derive the rates from paired sales in the export, or use the agent's, and scale flat amounts (a pool, a renovation) to the price. There are no built-in rates for garage spaces, bedroom or bath count, age, view, or size differences over about 300 sq ft: derive those from paired sales and say so, or leave the difference to the range and explain it.

- Subtract seller-paid buyer costs from the sale price, dollar for dollar.
- Apply a time adjustment only when the data shows the market has shifted since the sale.
- List each comp's adjustments in the report data (`sold_price`, `seller_concessions`, `adjustments`); compute.py does the arithmetic and fills the card and the summary table from the same numbers. More than about 15% net or 25% gross of the sale price (common appraisal guidelines) means a weak comp: replace it, or explain why it stays.
- Write each adjustment as a sentence with its dollar amount: "It sold in April, when rates were lower and homes were moving faster: minus about $10,000." Not "Time adj –2%."

The supported range is a judgment around the median adjusted value, typically about $25,000 wide (`cma.typical_range_width`). Lean toward the best condition matches and the most recent sales, say which way you leaned and why, and widen the range when comps disagree.

## The Scatterplot

From the export's remarks, list in `scatter.renovated` the sold private-pool homes that are genuinely renovated. Be conservative: "upgraded" or "well maintained" alone doesn't count. Pick 1–3 callouts, usually the top-selling comp and the strongest active competitor. The script draws everything else, computes the size-only trend line and lists homes left off the chart.
