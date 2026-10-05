# Method: History, Comps, Adjustments, Chart

## The Subject

Pull the ten facts for the fact grid (see `report-data.md`) from the property report, using the county's figures where the MLS and public records disagree (`listing-sheet.md`). Note anything unusual about the sale: vacant, trust, estate or LLC owner, an As-Is sale the public remarks state, "may be temporarily off market". What only Realtor Information, Realtor Remarks or private notes say (an As-Is preference, the listing agent is related to the owner, proof of funds required, showing instructions) stays with the agent: never in the report, but a watch item for the agent in the chat reply (`listing-sheet.md`, What Stays with the Agent).

## The Listing History

The MLS history grid lists every change across MLS numbers, newest first: read it bottom to top. For the 360 property view's grid (status moves like `ACT->PND`, price moves like `895000.00->839000`) and checking closings against the public-record sale history, see `listing-sheet.md`. The status codes and what they mean are in the MLS layer (`mls_format.history_codes`; for Stellar: NEW, DECR/INCR, TOM/BOM, PNC, SLD, CANC/EXP/WDN).

- A new MLS number resets days on market. Look for older numbers below it and report the true timeline: first list date, total active days across all listings, every price change. Enter every row as `history.events` (`report-data.md`): compute.py counts the cuts, increases, failed contracts and active days, and the report quotes them with placeholders (`{price_cuts}`, `{active_days}`), never a hand count.
- A row out of date order in the grid, or an MLS number that isn't the listing's (in the history or the export), is warned. Don't guess which date or listing is right: ask the agent in the reply, and count it as compute.py did until they answer.
- A pending followed by anything other than a sale means a contract failed. That's a question for the listing agent, not an assumption about the house.
- Repeated off/back-on-market pairs usually mean a seller managing showings or pausing to reset. A row that sums up undated pairs ("off and on twice") is entered as `report-data.md` describes (Undated off/on pairs).
- A price increase after a failed contract is a signal worth naming.

A relist at a higher price than a listing that failed (canceled, expired or withdrawn) is a finding too: the market already passed at the lower price.

Search the address: earlier syndicated remarks sometimes claim things (a "brand-new roof") that later vanish from the listing. That's a watch item.

## Choosing Comps

For a condo, choose and adjust comps by `condo.md` instead of the rules below.

From `stats.py`'s `sold_candidates`, pick the closest 5 sales when 5 or more qualify (4 or 6 only with a reason in `method_note`, such as a sixth sale in the subject's own subdivision; 3 only when no more qualify: compute.py warns below 3), taking them in the ranking's order and skipping only the ones the rules below rule out, so the same export gives the same comps and the same median:

- same subdivision first, then an immediately comparable neighborhood within about a mile;
- within about 20% of the subject's size, same pool status, similar age and construction, closed within about 6 months.

Include the sales that hurt a low offer. The buyer will find them anyway, and a report that hides them loses its credibility.

Each candidate carries `flags`: `distressed` (REO, short sale, auction) and `new_construction`. Leave those out unless the market is mostly distressed or new construction (or the subject is), then adjust for it and explain why in `method_note`. The export holds the property types the agent chose to compare. Single-family homes and townhouses can be compared when they overlap in size and price, so neither is dropped: the ranking puts the subject's type first, then close types, and puts condos, 55+ communities, leased land, a different waterfront status or a different number of stories lower. `sold_by_type` shows the mix; when the comps span types, say so in `method_note`. Duplicate sale records are already dropped (see `market_notes`), and a relisted home shows once in the competition with `listings` and `earlier_prices`. The ranking already favors recent, close sales; `more_candidates` counts the ones not listed (re-run stats.py with `--limit 30` to see them). Pass `--as-of` with the date the export was pulled so months of supply runs to that day.

## Adjusting

Judge each comp's condition from its remarks (renovated, partially updated, maintained, needs work), and say that condition adjustments are judgment calls based on listing text.

Default rates come from the built-in market (`cma.adjustments`; built in for Florida: about $75/sq ft for differences under about 300 sq ft, $25,000 for a private pool, $40,000–45,000 full renovation vs. dated, about $30,000 full vs. partial, and for a partial update $15,000 for a kitchen only and $10,000 for baths only over a dated home (condition is a ladder: dated, baths only, kitchen only, full; adjust by the difference between the comp's rung and the subject's, so a kitchen-only subject against an original comp is +$15,000 and against a baths-only comp +$5,000), the roof by its age on the as-of date (shingle: under 10 years $0, 10–14 years –$5,000, 15–19 years –$10,000, 20 or more –$15,000; double the years for tile or metal; adjust by the difference between the bands, so a comp with a 7-year roof against the subject's 16-year roof is –$10,000, and a comp in the subject's band gets nothing), –$5,000 for other documented recent systems (AC, water heater) the subject can't match (never for the roof as well), –$5,000 to –$10,000 for a noticeably better lot or water, 1–2% per quarter when the market has shifted, set as below, and 0 for sales in about the last 6 weeks). Outside the built-in market, derive the rates from paired sales in the export, scaled to the price, and say so. Explain any departure in `method_note`.

The built-in rates are flat dollars from Central Florida sales in one price band (`cma.calibrated_for`). compute.py warns when the home is outside that area or band: then derive the rates from paired sales in the export, or use the agent's, and scale flat amounts (a pool, a renovation) to the price. There are no built-in rates for garage spaces, bedroom or bath count, age, view, or size differences over about 300 sq ft: derive those from paired sales and say so, or leave the difference to the range and explain it.

- Subtract seller-paid buyer costs from the sale price, dollar for dollar.
- **Time (market shift).** Set one rate from stats.py's split: the change in median sale-to-original-list from `sold_early` to `sold_recent`. Under 1 point: no time adjustment. 1 to 3 points: 1% per quarter. Over 3 points: 2% per quarter. Apply it to every comp that closed more than about 6 weeks before `as_of`, prorated by months since the sale (4.5 months at 1% per quarter is 1.5%), taken on the sale price minus seller-paid costs (the price the comp really traded at, which compute.py starts from) and rounded to the nearest $1,000: minus when the ratio fell (a softer market), plus when it rose. Name both ratios and the rate in `method_note`. A split with fewer than about 5 sales on either side is too thin to read: use no time adjustment and say so. The gut check uses the same rate.
- List each comp's adjustments in the report data (`sold_price`, `seller_concessions`, `adjustments`); compute.py does the arithmetic and fills the card and the summary table from the same numbers. More than about 15% net or 25% gross of the sale price (common appraisal guidelines) means a weak comp: replace it, or explain why it stays.
- **Outliers.** After adjusting, a comp more than 10% above or below the median of the other comps (compute.py names it) is an outlier: replace it with the next candidate. Keep it only when it's one of the two closest matches in condition and location, say why in `method_note`, and don't let it set an end of the range. Decide once, before the range, so the same comps always give the same median.
- Write each adjustment as a sentence with its dollar amount: "It sold in April, when rates were lower and homes were moving faster: minus about $10,000." Not "Time adj –2%."

The supported range is a judgment around the median adjusted value, typically about $25,000 wide (`cma.typical_range_width`; 5% of the median where none is built in). Lean toward the best condition matches and the most recent sales, and say which way you leaned and why. Round each end to $5,000.

- **One comp never sets an end.** Each end sits at or inside the second-highest and second-lowest adjusted values, rounded outward to $5,000 (with 3 comps, inside the highest and lowest). A single high or low sale can pull the median a little, never an end: adjusted values of $431,000 to $496,000 with the second-highest at $478,800 top out at $480,000, not $490,000.
- **When comps disagree, widen, up to about twice the typical width** ($50,000 in Florida). Wider than that means the comps don't agree enough to support a range: replace the weakest match (the largest adjustments, the farthest or oldest sale) and re-run, or keep the range and say in the bottom line why it's this wide.

compute.py warns on both (`range_one_comp`, `range_wide`).

## The Scatterplot

The script marks the comp cards' sales as Comparable Sales (matched to the export by street address, case aside, so write each card's street address as the export spells it: "436 SUMMIT DR" or "436 Summit Dr", never "436 Summit Drive"; the report prints an all-caps address in title case), draws the other sales and the listings, computes the size-only trend line and notes how many homes were left off the chart for size. Pick 1–3 callouts, usually the top-selling comp and the strongest active competitor, each a home the chart plots (a sale or an active listing; never a pending one, and render.py names any callout that isn't on the chart: drop it or pick a plotted home). Each label goes on its `side` unless it would cover a marker or another label; then the script moves it and says so, and names any label it couldn't clear.
