# report.json

`assets/example-report.json` is a complete, approved report: copy it and replace every value. Body-text strings may contain `<strong>` and `<em>`, nothing else. Money fields marked *number* are plain numbers (no `$` or commas). Any string may quote a computed number with a placeholder (SKILL.md step 3 lists them); the scripts fill it everywhere and warn on any `{name}` they don't know.

## Contents

- Top level · subject · summary_page · bottom_line · history · offer_plan · offer · comps · scatter · competition · market · costs · watch · method

## Top Level

| Field | Notes |
|---|---|
| `prepared_date` | Written out ("September 22, 2026"). Default: today |
| `as_of` | `YYYY-MM-DD`: the date the export was pulled (also stats.py's `--as-of`), used for the handoff, months of supply and date rules. Default: today |
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
| `roof_year`, `hoa_monthly` | Optional, for the handoff: the offer skills' insurance and HOA checks. The handoff also carries the current bill, the payment's millage and homestead, and the flood zone (a FEMA code only) |
| `subdivision` | As in the export (improves the handoff's comp ranking) |
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

`events`: one per row of the MLS history grid, in the grid's order (newest first), copied as they are, never re-sorted by hand: compute.py warns when a row is out of date order and counts it by its date.

| Field | Notes |
|---|---|
| `date` | `YYYY-MM-DD` |
| `mls` | The row's MLS number |
| `change` | `listed`, `price`, `off_market`, `back_on`, `pending`, `sold`, `canceled`, `expired` or `withdrawn`, or the MLS's code (Stellar: NEW, DECR, INCR, TOM, BOM, PNC, SLD, CANC, EXP, WDN; the 360 grid's `->ACT` is `listed`, `ACT->PND` is `pending`, a price move is `price`). A row that moves both status and price ("INCR … (BOM)") is the status change with the new `price` |
| `price` | *number*, the asking price after the row, when it shows one. Any price that differs from the one before it counts as a cut or an increase |
| `dom` | Optional *number*: the grid's days on market at that row. A listing's latest `dom` replaces the calendar count of its active days. A DOM or CDOM note printed on another row of the block ("CDOM at cancel: 83") goes on that listing's last event |
| `cdom` | Optional *number*: the grid's cumulative days on market, when that's all it shows. Counted as `dom` on the oldest listing only; on a later one it spans earlier listings and can reset, so compute.py warns and asks for that listing's own DOM |
| `note` | Optional wording for the report's row (default: "Price cut", "Went under contract"…) |

A past sale from the public records is a `sold` event with no `mls`. compute.py prints `history`: `price_cuts`, `price_increases`, `price_cut_total`, `price_cut_pct` (of the first list price), `failed_contracts` (a pending followed by anything but a sale), `last_contract_price` and `vs_last_contract` (asking now minus the asking price when it last went under contract, quoted with `{last_contract_price}` and `{vs_last_contract}`), `out_of_order` (the rows that break the grid's date order), `active_days` (days listed for sale, not off the market or under contract, across every MLS number, the current one to `as_of`), and builds the report's table from the events. `rows` (`[date, event, price]` strings) replaces that table only when you need wording the events can't give; the counts still come from `events`.

## offer_plan

`intro`; `opening`, `target_low`, `target_high`, `walk_away` (*numbers*); `why_opening`, `why_target`, `why_walk_away`; optional `credit_alt` `{price, credit}`; `conditions` (lowercase clause completing "This assumes: …").

## offer

`heading` ("Negotiating Points") and 2–4 `bullets`, each starting with a `<strong>` lead-in.

## comps

`intro`, `method_note`, `cards` (3–6: `address`, `sold_price` *number*, `seller_concessions` *number* (what the seller paid toward the buyer's costs, 0 if none), `adjustments` (`[{label, amount}]`, Title Case labels, signed dollars: `{"label": "Renovation", "amount": 45000}`), `meta`, 2–3 `bullets` that explain the same adjustments in words), `summary_paragraph`. At the comps-only stage (the gut check, or the first run to set the range) a card needs only `address`, `sold_price`, `seller_concessions` and `adjustments`; `meta`, `bullets` and the other `comps` fields are optional until the full report. compute.py computes each adjusted value (sale price − concessions + adjustments) and builds the summary table from the cards; never type `adjusted` or `summary_rows`. It warns when a comp's adjustments pass 15% net or 25% gross of its sale price.

## scatter (standard)

`heading` (Title Case), `intro` (may use `{trend_at_subject}`), `subject_label`, `subject_label_pos` and each callout's `side` (`left`, `right`, `above` or `below`), `callouts` (1–3 `{address, label, side}`), `after_paragraph` (may use `{trend_at_subject}` and `{r2_share}`, which reads like "most" or "only about a third"), optional `min_size_ratio`/`max_size_ratio`/`fit_size_ratio` (defaults 0.6/1.4/1.6). The dashed line is fit to sales from subject size ÷ `fit_size_ratio` to × `fit_size_ratio`; sales priced far off it (and listings wildly off it) are left out of the line and off the chart, never a comp card, and the script adds a note with the count. The script adds a caption under the chart that explains the dashed line and says how far above or below it the home sits; don't repeat that in `intro` or `after_paragraph`.

## competition

`intro`, `rows`: `[address, status, price, sqft, pool ("Yes"/"No"), days, notes]`. `price` and `sqft` are plain numbers (474500, 1850), not formatted text.

## market

`intro`, `columns` (Title Case), `rows` (first cell a Title Case row name; strings you format from stats.py's numbers: "95.2%", "22 days"), `bullets` (3–5, each a `<strong>` finding plus what it means for the offer).

## costs

- This home's own cost numbers, when you have them (see `local-costs.md`): `transfer_tax_rate`, `transfer_tax_payer`, `title_payer`, `title_estimate_pct`, `title_fees`, `buyer_closing_cost_pct`, `tax_rate`, `insurance_rate` (fractions: `0.007` for 0.7%). They replace the built-in and national values.
- `buyer_cash`: optional *number*, what the buyer has for the down payment and closing. compute.py warns, and the report flags the figure, wherever cash to close or a down payment is more than that.
- `taxes`: `heading`, `intro`, `current_bill` and `current_year` (optional: leave out when there's no bill for the home, as with new construction or a land-only bill), `purchase_price` (optional: the payment's price by default), `homestead`, `jurisdictions` (1–2 of `{label, short, district}` or `{label, short, school_mills, total_mills}`; `label` completes the row name "Your Bill if the Home Is …" and `short` fills "If … Instead", so write them in Title Case: "in Unincorporated Seminole County", "City"), `note`, `after_paragraph` (escrow warning).
- `insurance`: `paragraph`.
- `payment`: `intro`, `price` (optional: leave it out and the payment is figured at the offer plan's target, the middle of `target_low` to `target_high`; page 1's tile and the table header name the price as Target, Asking, Opening Offer or Walk-Away), `rate` (percent), `insurance_annual` (placeholder), `tax_jurisdiction_index` (optional: with two jurisdictions and no confirmed district, leave it out and the payment uses the higher bill, labeled Estimate), `scenarios` (`{label, type, down_pct}`, `label` a Title Case column header like "Conventional, 5% Down", `down_pct` a fraction: 0.05 for 5%; put the buyer's own program first, since page 1's payment tile shows the first scenario), optional `hoa_cdd_monthly`, optional `flood_zone` (else the Flood Zone fact), optional `flood_insurance_annual` (a quote; without one the Flood Insurance row reads "Get a Quote" and the total leaves it out, never $0), optional `note` (compute.py adds the flood rule to it).
- `credit_scenarios`: `intro`, `loan_type`, `down_pct` (fraction), `closing_costs` or `closing_cost_pct` (fraction; the lender's figure, taxes included. Without either, the market's `buyer_closing_cost_pct` is used and its loan taxes are added on the loan amount: Florida note stamps 0.35% and intangible tax 0.2%), `scenarios` (2–4 `{price, credit}`), `after_paragraph`, optional `buydown` `{price, credit}`, optional `buyer_broker_agreement_pct` and `seller_pays_buyer_broker_pct` (fractions: when the seller pays less than the buyer's agreement, the difference is a "Buyer's Broker Fee (Not Paid by Seller)" row and counts in cash to close). See `offer-plan.md`.

## watch

`items` (each with a `<strong>` lead) and 5–7 `questions`.

## method

Two paragraphs: sources with dates; the not-an-appraisal statement and shelf life.
