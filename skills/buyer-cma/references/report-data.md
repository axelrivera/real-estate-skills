# report.json

`assets/example-report.json` is a complete, approved report: copy it and replace every value. report.json holds two kinds of fields:

- **Data** copied from the sources: prices, dates, the history grid, each comp's sale and adjustments, the payment inputs. Money fields marked *number* are plain numbers (no `$` or commas).
- **Judgment** in your words: why the range sits where it does, why each step of the plan, what it assumes, the watch items and questions. Judgment fields carry **no figures**: no digits, `$`, `%` or month names (`{placeholders}` neither). The script writes every count, price, percent, date and comparison itself, from the numbers, in its own sentences next to yours; a figure typed into a judgment field stops compute.py and render.py, naming each field. Write "the spring sales", "repeated price cuts", "the four-point inspection", never "April" or "4 cuts". Body text may contain `<strong>` and `<em>`, nothing else.

Fields the script now writes itself (a `paragraph`, an `intro`, `key_stats`, the market table, a card's `meta`, a scenario's `label`) stop the run with a note saying where your judgment goes instead.

## Contents

- Top level · subject · summary_page · bottom_line · history · offer_plan · offer · comps · scatter · competition · market · costs · watch

## Top Level

| Field | Notes |
|---|---|
| `prepared_date` | The date the agent gave as today (`YYYY-MM-DD` or written out). Default: `as_of` |
| `as_of` | `YYYY-MM-DD`: the date the export was pulled (also stats.py's `--as-of`), used for the handoff, months of supply and date rules. The date the agent gave as today, when they gave one. Default: the computer's date |
| `export` | Path to the MLS export CSV (absolute, or relative to report.json's folder; keep them together in the temporary folder). The chart, the market table, each comp's sale line and the handoff's market stats come from it |
| `split_date` | The `--split-date` you used with stats.py: the market table's two periods and the time adjustment's cutoff |
| `mls` | The MLS name when it isn't the one built in for the county (same as `--mls`) |
| `export_columns` | For an MLS that isn't built in: `{field name: export header}` for `address`, `status`, `living_area`, `close_price`, `current_price` and any others the export has (same as stats.py `--columns`) |
| `sources` | Optional: other sources by name, figure-free ("the county property appraiser's final millage rates"). The script lists the export's sales and listings itself |

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
| `beds`, `baths`, `year_built`, `pool` | *numbers* and `true`/`false`: page 1's facts line and the Beds / Baths fact come from them |
| `latitude`, `longitude` | Optional *numbers*: only when the export has no Distance column and no row for the home |
| `roof_year`, `hoa_monthly`, `hoa_frequency` | Optional, for the handoff (`hoa_frequency`: `monthly`, `quarterly`, `semiannual` or `annual`, how the association bills the dues) |
| `flood_zone` | Optional: the FEMA zone code; else the Flood Zone fact |
| `legal_description`, `parcel_id` | Optional, for the handoff only (never printed): copied exactly from the property report, never invented |
| `subdivision` | As in the export (improves the comp ranking) |
| `as_is_public` | Optional: `true` only when the public remarks or the flyer say As-Is. Without it, compute.py warns on a judgment sentence that states the seller's As-Is preference (`listing-sheet.md`) |
| `property_type` | `single_family`, `condo`, `townhouse`, `multifamily` or `land`. A condo follows `condo.md` |
| `facts` | The listing's own facts as `[label, value]`, copied from the property report, labels in Title Case: Lot, Built, Pool, Garage, HOA / CDD, Flood Zone. The script puts List Price, Price per Sq Ft, Beds / Baths and Living Area first, from the numbers |
| `summary` | Judgment, 1–2 sentences: what the home is and anything unusual about the sale (vacant, trust or estate owner), figure-free |

## summary_page

All judgment, figure-free: `label` (default "Buyer Summary"), `headline` (under about 25 words), `why` (exactly 3 reasons, under about 25 words each), `check_first` (exactly 3 `[heading, one line]`, heading in Title Case), `next_step`. Page 1's key numbers, the dot plot, the cost table and the payment tile are the script's.

## bottom_line

`low`, `high` (*numbers*: the supported range, `method.md`); `why`: judgment, 2–3 sentences on why the range sits where it does (which sales it leans on). The script says where asking sits in the range and quotes the median adjusted comp.

## history (whenever there's more than the current listing)

`events` and `takeaway`. The script writes the heading, the counts (first listed, active days, price cuts and their total, increases, failed contracts, asking against the last contract) and the table. `takeaway`: judgment, what it adds up to and the question it raises. The gut check needs `events` too.

`events`: one per row of the MLS history grid, in the grid's order (newest first), copied as they are, never re-sorted by hand and never left out: an earlier owner's listing and its sale stay in, so the table shows the whole record. compute.py warns when a row is out of date order and counts it by its date.

| Field | Notes |
|---|---|
| `date` | `YYYY-MM-DD` |
| `mls` | The row's MLS number |
| `change` | `listed`, `price`, `off_market`, `back_on`, `pending`, `sold`, `canceled`, `expired` or `withdrawn`, or the MLS's code (Stellar: NEW, DECR, INCR, TOM, BOM, PNC, SLD, CANC, EXP, WDN; the 360 grid's `->ACT` is `listed`, `ACT->PND` is `pending`, a price move is `price`). A row that moves both status and price ("INCR … (BOM)") is the status change with the new `price` |
| `price` | *number*, the asking price after the row, when it shows one. Any price that differs from the one before it counts as a cut or an increase |
| `dom` | Optional *number*: the grid's days on market at that row. A listing's latest `dom` replaces the calendar count of its active days |
| `cdom` | Optional *number*: the grid's cumulative days on market, when that's all it shows. Counted as `dom` on the oldest listing only; on a later one compute.py warns and asks for that listing's own DOM |
| `note` | Optional figure-free wording for the report's row (default: "Price cut", "Went under contract"…) |
| `days_off`, `days_on` | Optional *numbers*: days off or back on the market in undated off/on pairs the row sums up (see below) |

**Undated off/on pairs.** A grid row that sums up several moves ("TOM (off and on twice through Mar 5)") hides off/on pairs with no dates. Enter the row as its dated event with a figure-free `note` ("Taken off the market (off and on twice)"), then, in this order of preference: the listing's DOM from the grid as `dom`; each pair as its own dated `off_market` and `back_on` events; or the days in `days_on` or `days_off`. A note that says a move happened more than once, with none of these, is warned (`history_repeat`): ask the agent.

A past sale from the public records is a `sold` event with no `mls`. compute.py prints `history` (`price_cuts`, `price_increases`, `price_cut_total`, `price_cut_pct`, `failed_contracts`, `last_contract_price`, `vs_last_contract`, `out_of_order`, `active_days`, `counted_since_sale`, and `display`, each formatted) and `history_section` (the report's heading, sentences and table). Every count starts after the last sale: an earlier owner's listing shows in the table but adds no days, cuts or contracts.

## offer_plan

`opening`, `target_low`, `target_high`, `walk_away` (*numbers*); judgment: `why_opening`, `why_target`, `why_walk_away`, `conditions` (lowercase clause completing "This assumes: …"); optional `credit_alt` `{price, credit}` (it must match a credit scenario; the script says what it saves at closing).

## offer

Optional `heading` (default "Negotiating Points") and 2–4 `bullets`, each starting with a `<strong>` lead-in: judgment, figure-free.

## comps

- `cards` (3–6): `address` (as the export spells the street), `sold_price` *number*, `seller_concessions` *number* (0 if none), `adjustments` (`[{label, amount}]`, Title Case labels, signed dollars: `{"label": "Renovation", "amount": 45000}`), optional `close_date` (`YYYY-MM-DD`, when the export doesn't have the sale), and 1–3 `bullets`: judgment, why the sale is a comp and what its adjustments are about, in words. The card's sale line (price, date, size, beds and baths, pool, lot, distance) comes from the export, and each adjustment prints with its amount, adding up to the adjusted value. compute.py computes each adjusted value (sale price − concessions + adjustments) and the summary table; never type `adjusted` or `summary_rows`. It warns when a comp's adjustments pass 15% net or 25% gross of its sale price.
- `time_adjustment` (optional, `method.md`, Time): `{rate_per_quarter, prices, cutoff}`. The script adds each card's time line and names the rate and cutoff in the method line.
- Judgment: `intro` (how the comps were chosen), `method_note` (caveats the method line doesn't say: condition is judged from listing text, a departure from the built-in rates), `lean` (which way the range leans and why). The script writes the count and dates of the sales and the method line naming each kind of adjustment used, with its amounts.

At the comps-only stage (the gut check, or the first run to set the range) a card needs only `address`, `sold_price`, `seller_concessions` and `adjustments`.

## scatter (standard)

Optional `heading`; `subject_label_pos` and each callout's `side` (`left`, `right`, `above` or `below`); `callouts` (1–3 `{address, side}`, each a home the chart plots: a sale or an active listing); judgment `takeaway` (what the chart shows for this home); optional `min_size_ratio`/`max_size_ratio`/`fit_size_ratio` (defaults 0.6/1.4/1.6). The script writes what the chart plots, how many homes were left off, the caption with where the home sits against the size-only line, and how much of the price differences size explains.

## competition

Judgment `intro`; `rows`: `[address, status, price, sqft, pool ("Yes"/"No"), days, note]`: `price`, `sqft` and `days` plain numbers from the export, `note` judgment (why it matters to this buyer, figure-free). Optional `adjustments`: `{address as in rows: [{label, amount}]}` to adjust a listing's price to this home: the script adds the adjusted price and where it sits in the range to that row's note.

## market

`bullets` (3–5, each a `<strong>` finding plus what it means for the offer): judgment, figure-free. The script builds the market table (homes sold, median price, sale to original asking, days on market, seller-paid costs, before and since the split) and its counts (sales, listings, months of supply) from the export, leaving out the home's own rows.

## costs

- This home's own cost numbers, when you have them (see `local-costs.md`): `transfer_tax_rate`, `transfer_tax_payer`, `title_payer`, `title_estimate_pct`, `title_fees`, `buyer_closing_cost_pct`, `tax_rate`, `insurance_rate` (fractions: `0.007` for 0.7%).
- `buyer_cash`: optional *number*, what the buyer has for the down payment and closing. compute.py warns, and the report flags the figure, wherever cash to close is more than that.
- `taxes`: `current_bill` and `current_year` (optional: leave out when there's no bill for the home), `purchase_price` (optional: the payment's price by default), `homestead`, `jurisdictions` (1–2 of `{label, short, district}` or `{label, short, school_mills, total_mills}`; `label` completes "Your Bill if the Home Is …" and `short` fills "If … Instead", both Title Case names; `short` is required with two). The script writes the heading, the current bill and the reassessment rule, the table, the escrow warning, and the notes (millage, assessed at the price, homestead filing, portability, an unconfirmed district).
- `insurance`: `drivers`: judgment, the drivers for this house (roof age, wiring and plumbing era, wind mitigation, pool, flood zone), figure-free. The premium the payment uses is the script's note.
- `payment`: `price` (optional: the offer plan's target by default), `rate` (percent), `rate_week` (optional `YYYY-MM-DD`: the Freddie Mac survey's week, named with the rate), `insurance_annual` (optional: a quote or the agent's figure; left out, compute.py estimates it, `costs.md`), `tax_jurisdiction_index` (optional), `scenarios` (`{type, down_pct, assumed}`: the script names each one, "Conventional, 5% Down"; `down_pct` a fraction; `assumed: true` when the buyer hasn't confirmed the financing, said once in the notes; the buyer's own program first), optional `hoa_cdd_monthly`, `flood_zone`, `flood_insurance_annual` (a quote; without one the Flood Insurance row reads "Get a Quote" and the total leaves it out), optional `note` (judgment, figure-free, added to the notes).
- `credit_scenarios`: `loan_type`, `down_pct` (fraction), `closing_costs` or `closing_cost_pct` (fraction; the lender's figure, taxes included; without either, the shared estimate), `scenarios` (2–4 `{price, credit}`), judgment `takeaway` (the trade-off for this buyer), optional `buydown` `{price, credit}`, optional `buyer_broker_agreement_pct` and `seller_pays_buyer_broker_pct` (fractions). See `offer-plan.md`.

Every cost table is a ledger: each line rounded once to the dollar, each total the sum of the printed lines. Every assumption and estimate behind them is said once, in the notes block at the end of the cost section.

## watch

`items` (each with a `<strong>` lead) and 5–7 `questions`: judgment, figure-free.
