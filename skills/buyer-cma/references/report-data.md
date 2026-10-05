# report.json

`assets/example-report.json` is a complete, approved report: copy it and replace every value. Body-text strings may contain `<strong>` and `<em>`, nothing else. Money fields marked *number* are plain numbers (no `$` or commas). Any string may quote a computed number with a placeholder (SKILL.md step 3 lists them); the scripts fill it everywhere and warn on any `{name}` they don't know.

## Contents

- Top level · subject · summary_page · bottom_line · history · offer_plan · offer · comps · scatter · competition · market · costs · watch · method

## Top Level

| Field | Notes |
|---|---|
| `prepared_date` | Written out ("September 22, 2026"). The date the agent gave as today, when they gave one. Default: the computer's date |
| `as_of` | `YYYY-MM-DD`: the date the export was pulled (also stats.py's `--as-of`), used for the handoff, months of supply and date rules. The date the agent gave as today, when they gave one. Default: the computer's date |
| `export` | Path to the MLS export CSV (absolute, or relative to report.json's folder; keep them together in the temporary folder) (used for the chart and the handoff's market stats) |
| `split_date` | The `--split-date` you used with stats.py |
| `mls` | The MLS name when it isn't the one built in for the county (same as `--mls`) |
| `export_columns` | For an MLS that isn't built in: `{field name: export header}` for `address`, `status`, `living_area`, `close_price`, `current_price` and any others the export has (same as stats.py `--columns`) |
| `labels` | Optional overrides of fixed wording |

The agent's name, brokerage, license and contact come from the agent's profile (`--profile`), never from report.json. Local costs never come from the profile: see `local-costs.md`.

## subject

| Field | Notes |
|---|---|
| `address` | Display form ("1438 Buttonbush Dr") |
| `mls_address` | Exactly as in the export's address column |
| `city`, `state`, `county` | `state` and `county` pick the market's tax rules, millage and MLS format |
| `locality` | "City, ST ZIP · Subdivision · County · MLS #". Keep the parts in this order, separated by " · ": page 1 puts the city line under the address and the rest at the right |
| `mls_number` | Optional: the listing's MLS number, when `locality` doesn't carry it. compute.py warns when the export's current row or the history's newest row has another |
| `list_price`, `sqft` | *numbers* |
| `latitude`, `longitude` | Optional *numbers*: only when the export has no Distance column and no row for the home (distances are measured from its own row otherwise) |
| `beds`, `baths`, `year_built`, `pool` | For the handoff (`pool` true/false) |
| `roof_year`, `hoa_monthly`, `hoa_frequency` | Optional, for the handoff: the offer skills' insurance and HOA checks (`hoa_frequency`: `monthly`, `quarterly`, `semiannual` or `annual`, how the association bills the dues, so the offer's HOA rider shows them as billed). The handoff also carries the current bill, the payment's millage and homestead, the payment's insurance and the price it was figured at (so the offer's payment uses the same premium), the flood zone (a FEMA code only), and the history's active days (`dom`) and number of price cuts (`price_cuts`) |
| `legal_description`, `parcel_id` | Optional, for the handoff only (never printed): the legal description and the tax ID (parcel ID) as the property report prints them, copied exactly, never invented. The offer worksheet's paragraph 1 uses them |
| `subdivision` | As in the export (improves the handoff's comp ranking) |
| `as_is_public` | Optional: `true` only when the public remarks or the flyer say As-Is. Without it, compute.py warns on a sentence that states the seller's As-Is preference (`listing-sheet.md`) |
| `property_type` | `single_family`, `condo`, `townhouse`, `multifamily` or `land`. A condo follows `condo.md` (comps, adjustments, association questions) |
| `facts` | Ten `[label, value]` in this order, labels in Title Case: List Price, Price per Sq Ft, Beds / Baths, Living Area, Lot, Built, Pool, Garage, HOA / CDD, Flood Zone |
| `summary` | 2–3 sentences: what the home is and anything unusual about the sale |
| `summary_facts` | Short line for page 1 ("4 bed · 2 bath · 1,849 sq ft · pool · built 1972") |

## summary_page

`label` (default "Buyer Summary"), `headline`, `key_stats` (exactly 3 `[value, label]`, label in Title Case), `why` (exactly 3), `check_first` (exactly 3 `[heading, one line]`, heading in Title Case), `next_step`. The dot plot and the cost table are computed.

## bottom_line

`low`, `high`, `midpoint` (*numbers*), `paragraph`.

## history (whenever there's more than the current listing)

`heading` (a finding), `intro`, `events`, `after`. The gut check needs `events` too: the history's counts come only from them.

`events`: one per row of the MLS history grid, in the grid's order (newest first), copied as they are, never re-sorted by hand and never left out: an earlier owner's listing and its sale stay in, so the table shows the whole record: compute.py warns when a row is out of date order and counts it by its date.

| Field | Notes |
|---|---|
| `date` | `YYYY-MM-DD` |
| `mls` | The row's MLS number |
| `change` | `listed`, `price`, `off_market`, `back_on`, `pending`, `sold`, `canceled`, `expired` or `withdrawn`, or the MLS's code (Stellar: NEW, DECR, INCR, TOM, BOM, PNC, SLD, CANC, EXP, WDN; the 360 grid's `->ACT` is `listed`, `ACT->PND` is `pending`, a price move is `price`). A row that moves both status and price ("INCR … (BOM)") is the status change with the new `price` |
| `price` | *number*, the asking price after the row, when it shows one. Any price that differs from the one before it counts as a cut or an increase |
| `dom` | Optional *number*: the grid's days on market at that row. A listing's latest `dom` replaces the calendar count of its active days. A DOM or CDOM note printed on another row of the block ("CDOM at cancel: 83") goes on that listing's last event |
| `cdom` | Optional *number*: the grid's cumulative days on market, when that's all it shows. Counted as `dom` on the oldest listing only; on a later one it spans earlier listings and can reset, so compute.py warns and asks for that listing's own DOM |
| `note` | Optional wording for the report's row (default: "Price cut", "Went under contract"…) |
| `days_off`, `days_on` | Optional *numbers*: days off or back on the market in undated off/on pairs the row sums up (see below) |

**Undated off/on pairs.** A grid row that sums up several moves ("TOM (off and on twice through Mar 5)") hides off/on pairs with no dates, so the calendar counts that stretch as all off (or all on). Enter the row as its dated event with the wording in `note`, then, in this order of preference: the listing's DOM from the grid as `dom` (the MLS's count already includes the pairs, so nothing else is needed); each pair as its own dated `off_market` and `back_on` events, when the agent has the dates; or the days in `days_on` (days back for sale inside an off stretch) or `days_off` (days off inside an active stretch), when the agent knows them. A note that says a move happened more than once, with none of these, is warned (`history_repeat`): ask the agent, and quote the active days as compute.py counted them until they answer.

A past sale from the public records is a `sold` event with no `mls`. compute.py prints `history`: `price_cuts`, `price_increases`, `price_cut_total`, `price_cut_pct` (of the first list price), `failed_contracts` (a pending followed by anything but a sale), `last_contract_price` and `vs_last_contract` (asking now minus the asking price when it last went under contract, quoted with `{last_contract_price}` and `{vs_last_contract}`), `out_of_order` (the rows that break the grid's date order), `active_days` (days listed for sale, not off the market or under contract, across every MLS number since the last sale, the current one to `as_of`). Every count starts after the last sale (an ownership change, `counted_since_sale`): an earlier owner's listing shows in the table but adds no days, cuts or contracts, and builds the report's table from the events. `rows` (`[date, event, price]` strings) replaces that table only when you need wording the events can't give; the counts still come from `events`.

## offer_plan

`intro`; `opening`, `target_low`, `target_high`, `walk_away` (*numbers*); `why_opening`, `why_target`, `why_walk_away`; optional `credit_alt` `{price, credit}`; `conditions` (lowercase clause completing "This assumes: …").

## offer

`heading` ("Negotiating Points") and 2–4 `bullets`, each starting with a `<strong>` lead-in.

## comps

`intro`, `method_note`, `cards` (3–6: `address`, `sold_price` *number*, `seller_concessions` *number* (what the seller paid toward the buyer's costs, 0 if none), `adjustments` (`[{label, amount}]`, Title Case labels, signed dollars: `{"label": "Renovation", "amount": 45000}`), `meta`, 2–3 `bullets` that explain the same adjustments in words), `summary_paragraph`. At the comps-only stage (the gut check, or the first run to set the range) a card needs only `address`, `sold_price`, `seller_concessions` and `adjustments`; `meta`, `bullets` and the other `comps` fields are optional until the full report. compute.py computes each adjusted value (sale price − concessions + adjustments) and builds the summary table from the cards; never type `adjusted` or `summary_rows`. It warns when a comp's adjustments pass 15% net or 25% gross of its sale price.

## scatter (standard)

`heading` (Title Case), `intro` (may use `{trend_at_subject}`), `subject_label_pos` and each callout's `side` (`left`, `right`, `above` or `below`), `callouts` (1–3 `{address, side}`; the script labels the subject and each callout with its address as the report prints it, the same form as the comp cards and the legend), `after_paragraph` (may use `{trend_at_subject}` and `{r2_share}`, which reads like "most" or "only about a third"), optional `min_size_ratio`/`max_size_ratio`/`fit_size_ratio` (defaults 0.6/1.4/1.6). The dashed line is fit to sales from subject size ÷ `fit_size_ratio` to × `fit_size_ratio`; sales priced far off it (and listings wildly off it) are left out of the line and off the chart, never a comp card, and the script adds a note with the count. The script adds a caption under the chart that explains the dashed line and says how far above or below it the home sits; don't repeat that in `intro` or `after_paragraph`.

## competition

`intro`, `rows`: `[address, status, price, sqft, pool ("Yes"/"No"), days, notes]`. `price` and `sqft` are plain numbers (474500, 1850), not formatted text. Optional `adjustments`: `{address as in rows: [{label, amount}]}`, for a note that adjusts a listing's price to this home: compute.py adds them to its price and fills `{adjusted_estimate}` and `{range_position}` ("near the top of this home's range") in that row's note only.

## market

`intro`, `columns` (Title Case), `rows` (first cell a Title Case row name; strings you format from stats.py's numbers: "95.2%", "22 days"; days are whole days, so a median of an even count rounds half up: 7.5 is "8 days", and compute.py warns on a fractional day), `bullets` (3–5, each a `<strong>` finding plus what it means for the offer). With an export and two period columns, the script adds a Median Sale Price row (before and since the split) after the first row; leave it out of `rows`.

## costs

- This home's own cost numbers, when you have them (see `local-costs.md`): `transfer_tax_rate`, `transfer_tax_payer`, `title_payer`, `title_estimate_pct`, `title_fees`, `buyer_closing_cost_pct`, `tax_rate`, `insurance_rate` (fractions: `0.007` for 0.7%). They replace the built-in and national values.
- `buyer_cash`: optional *number*, what the buyer has for the down payment and closing. compute.py warns, and the report flags the figure, wherever cash to close or a down payment is more than that.
- `taxes`: `heading`, `intro`, `current_bill` and `current_year` (optional: leave out when there's no bill for the home, as with new construction or a land-only bill), `purchase_price` (optional: the payment's price by default), `homestead`, `jurisdictions` (1–2 of `{label, short, district}` or `{label, short, school_mills, total_mills}`; `label` completes the row name "Your Bill if the Home Is …" and `short` fills "If … Instead", so write them in Title Case: "in Unincorporated Seminole County", "City"), `note`, `after_paragraph` (escrow warning).
- `insurance`: `paragraph`.
- `payment`: `intro`, `price` (optional: leave it out and the payment is figured at the offer plan's target, the middle of `target_low` to `target_high`; page 1's tile and the table header name the price as Target, Asking, Opening Offer or Walk-Away), `rate` (percent), `insurance_annual` (optional: a quote or the agent's figure; left out, compute.py estimates it, `costs.md`), `tax_jurisdiction_index` (optional: with two jurisdictions and no confirmed district, leave it out and the payment uses the higher bill, labeled Estimate), `scenarios` (`{label, type, down_pct, assumed}`, `label` a Title Case column header naming only the loan, like "Conventional, 5% Down", with no parentheses; `down_pct` a fraction: 0.05 for 5%; `assumed: true` when the buyer hasn't confirmed the financing, and the report adds ", Assumed" to the label once, in the table and on page 1 (compute.py warns on "Assumed" or parentheses typed into `label`); put the buyer's own program first, since page 1's payment tile and cash to close show the first scenario). compute.py adds each scenario's closing costs and cash to close (down payment plus closing costs, and any buyer's broker fee the seller doesn't pay), figured as in `credit_scenarios` below: the lender's `closing_costs` for the credit table's own program and down payment, otherwise `closing_cost_pct` or the market's estimate. The first scenario's cash to close warns `cash_short` or `cash_tight` against `buyer_cash`; optional `hoa_cdd_monthly`, optional `flood_zone` (else the Flood Zone fact), optional `flood_insurance_annual` (a quote; without one the Flood Insurance row reads "Get a Quote" and the total leaves it out, never $0), optional `note` (a sentence added after the report's own assumptions note, which always keeps the rate, mortgage insurance, closing costs and "every $10,000 off" lines; the tax and flood rules follow it).
- `credit_scenarios`: `intro`, `loan_type`, `down_pct` (fraction), `closing_costs` or `closing_cost_pct` (fraction; the lender's figure, taxes included. Without either, the shared estimate: the market's `buyer_closing_cost_pct` plus 0.5% prepaids, and its loan taxes on the loan amount: Florida note stamps 0.35% and intangible tax 0.2%), `scenarios` (2–4 `{price, credit}`), `after_paragraph`, optional `buydown` `{price, credit}`, optional `buyer_broker_agreement_pct` and `seller_pays_buyer_broker_pct` (fractions: when the seller pays less than the buyer's agreement, the difference is a "Buyer's Broker Fee (Not Paid by Seller)" row and counts in cash to close). See `offer-plan.md`.

## watch

`items` (each with a `<strong>` lead) and 5–7 `questions`.

## method

Two paragraphs: sources with dates; the not-an-appraisal statement and shelf life.
