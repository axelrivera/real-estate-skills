# report.json

`assets/example-report.json` is a complete, approved report: copy it and replace every value. report.json holds two kinds of fields:

- **Data** copied from the sources: prices, dates, the comps and their adjustments, the competition rows, the costs and the payment inputs. Money fields marked *number* are plain numbers (no `$` or commas).
- **Judgment** in your words: why this price, what it means for the seller, which way the range leans, what to prepare and what you need from the seller. Judgment fields carry **no figures**: no digits, `$`, `%`, months, seasons or weekdays (`{placeholders}` neither), and never describe the people who own or live in the home (vacant, a tenant, relocating, their family): compute.py stops on either. The script writes every count, price, percent, date and comparison itself, from the numbers, in its own sentences next to yours; a figure typed into a judgment field stops compute.py and render.py, naming each field. Write "the earlier sales", "repeated price cuts", "the four-point inspection", never "April", "the spring sales" or "4 cuts". Body text may contain `<strong>` and `<em>`, nothing else.

Fields the script now writes itself (`recommendation.paragraph`, `summary_page.key_stats` and `first_steps`, `comps.summary_paragraph`, a card's `meta`, a strategy's `label`, `scatter.intro`, `market.intro`, `columns` and `rows`, `pricing.net_intro` and `net_note`, `buyer_payment.note`, `method`, `labels`) stop the run with a note saying where your judgment goes instead.

## Contents

- Top level · subject · summary_page · recommendation · range_override · price_override · means · comps · scatter · competition · market · pricing · costs · buyer_payment · prep, needs, sources · deck

## Top Level

| Field | Notes |
|---|---|
| `prepared_date` | The date the agent gave as today (`YYYY-MM-DD` or written out). Default: `as_of` |
| `as_of` | `YYYY-MM-DD`: the date the export was pulled (also stats.py's `--as-of`), used for the handoff, months of supply, holding costs and date rules. Default: today |
| `export` | Path to the MLS export CSV (absolute, or relative to report.json's folder; keep them together in the temporary folder). The chart, the market table, each comp's sale line and the handoff's market stats come from it |
| `split_date` | The `--split-date` you used with stats.py: the market table's two periods and the time adjustment's cutoff |
| `launch_date` | Optional `YYYY-MM-DD`: the go-live date, when the agent gives one. Left out, it's two weeks after `as_of`. Page 1, the deck's timeline and each option's closing use this one date |
| `mls` | The MLS name: stats.py's `mls` (same as `--mls`). Without it compute.py assumes the one built in for the county |
| `export_columns` | For an MLS that isn't built in: `{field name: export header}` for `address`, `status`, `living_area`, `close_price`, `current_price` and any others the export has (same as stats.py `--columns`) |
| `deck` | The listing presentation's wording, as an object inside report.json (a path to a JSON file also works, beside report.json). See `deck-content.md` |
| `preliminary` | Optional: mark the report Preliminary yourself with the reason as a short sentence, figure-free ("the home's condition and the tax bill are still to be confirmed, so the figures may change."), or `true` for a general reason. compute.py also sets it when a cost has no value at all, or the state isn't known; page 1 and the chat reply use `preliminary_reason` |
| `reprice` | Only for the agent's own current listing, priced again: stats.py's `reprice`, `{current_price, days_on_market}` (*numbers*) and optional `original_price` (compute.py also finds it in the export). The report and reply show its price history (`price_history`). Adds the Stay at Current Price option, "New List Price" wording and the "Before We Reprice" headings. The other options are price cuts of at least 1%; `allow_increase: true` only when the agent asked to price it higher. Never for another brokerage's listing. compute.py gives Stay's expected sale by the rule in `method.md` (`reprice.stay_expected_sale`); an agent's own figure goes in `pricing.options.stay.expected_sale` |
| `listing_history` | Every listing of the home that ended unsold (expired, withdrawn, canceled), however long ago, from the property report: `[{status, price, original_price, ended, days_on_market}]` (`price`, `original_price` *numbers*; `ended` `YYYY-MM-DD`, `YYYY-MM` or `YYYY`). compute.py writes `history_line` ("Expired in March 2017 after 184 days at $229,900, first listed at $239,900."), for page 1, the deck and the reply. Left out, the export's own rows fill it |
| `relist` | When the home's own earlier listing expired, was canceled or withdrawn within the last 12 months (or undated), or the agent chose to treat a live listing as failed: stats.py's `relist` (`failed_price` *number*, optional `status`, `days_on_market`, `original_price`). compute.py caps every option at `failed_price` unless `reason_above` gives the agent's reason, figure-free (`method.md`, A Relist); compute.py also finds it in the export when this is left out |
| `sources` | Optional: other sources by name, figure-free ("the property details and tax bill you provided"). The script lists the export's sales and listings and the rate's survey itself |

The agent's name, team, brokerage, license and contact come from the agent's profile (`--profile`), never from report.json; only the fields the profile has are shown.

## subject

| Field | Notes |
|---|---|
| `address` | Display form ("1438 Buttonbush Dr") |
| `property_type` | `single_family`, `condo`, `townhouse`, `multifamily` or `land`. Needed in Miami-Dade, where every type but single-family owes the 0.45% deed surtax |
| `mls_address` | Exactly as in the export's address column. Every row with it is left out of stats, chart and deck |
| `city`, `state`, `county` | `state` and `county` pick the market's closing costs, tax rules, millage and MLS format. The deck's cover names the city and subdivision |
| `locality` | "City, ST ZIP · Subdivision · County". No MLS number: this isn't a listing yet. Keep the parts in this order, separated by " · " |
| `sqft` | *number*, heated area from the seller or public record |
| `latitude`, `longitude` | Optional *numbers*: the home's location, for distances when the export has no Distance column and no row for the home |
| `beds`, `baths`, `year_built`, `pool`, `hoa`, `subdivision` | Page 1's facts line, the Beds / Baths and Living Area facts, the comp ranking and the estoppel line (`pool`, `hoa` true/false) |
| `roof_year` | Optional, for the handoff: the offer review's insurance check |
| `facts` | The home's own facts as `[label, value]`, copied from the property report and the seller, labels in Title Case: Lot, Built, Pool, Garage, HOA / CDD, Flood Zone, Current Taxes (when `costs.annual_tax` isn't given), Recent Updates. The script puts Beds / Baths, Living Area and, from `costs.annual_tax`, Current Taxes first |
| `condition` | The home's level on the condition ladder (`condition-ladder.md`), from the seller's described updates: each comp is adjusted by the difference between its level and this one |
| `summary` | Judgment, 2–3 sentences: the home and its updates "as described by you", and what the report does, figure-free |

## summary_page (write it last)

All judgment, figure-free: `label` (default "Seller Summary"), `headline` (about 20 words at most), `why` (exactly 3, about 25 words at most each: the comps, the market, the competition), `next_step`. Page 1's recommended price, range, expected sale, key numbers, dot plot, options table, net tile, its first three steps (the first three `prep.items`) and the go-live date are the script's.

## recommendation

`why`: judgment, 2–3 sentences on why this price and why a higher first price is a risk. The range and the list price are the script's (`method.md`): run compute.py first with only `subject` and `comps` (no `pricing` or `buyer_payment`) and it prints the range, the median and the stance the market data suggests, with each stance's price; never type `list_price`, `low`, `high` or `midpoint` (compute.py stops on them). The script states the range, the median adjusted value and where the list price sits against both.

## range_override

Only when the agent chose the range themselves: `{low, high, reason}` (*numbers*, and judgment: why, in words, no figures). The report uses it and says beside it that it's the agent's judgment, with the method's range for comparison; compute.py still warns when it's wider than the cap, too narrow or set by one comp.

## price_override

Only when the agent chose the list price themselves: `{list_price, reason}` (*number*, and judgment: why, in words, no figures). The report shows it as the agent's (Our Price), beside the stance's price, and it is the recommended option: on a new listing it takes the place of the stance option nearest it and the other two stay; on a reprice or relist the other options are built around it. On a reprice it must be a cut of at least 1% (unless `reprice.allow_increase`); on a relist, at or under the failed price (unless `relist.reason_above`). compute.py warns when it's outside the range.

## means

3–5 bullets, each opening with a `<strong>` finding, figure-free: expected negotiation, the first-weeks window, the appraisal ceiling, the value of documentation.

## comps

- `cards` (3–6): `address` (as the export spells the street), `sold_price` *number*, `seller_concessions` *number* (0 if none), `condition` (its level on the condition ladder, `condition-ladder.md`: `original`, `cosmetic`, `baths_only`, `kitchen_only`, `kitchen_and_baths`, `full_renovation` or `new`), `adjustments` (`[{label, amount, kind}]`, Title Case labels, signed dollars: `{"label": "Pool", "amount": 25000, "kind": "pool"}`; `kind` is one of `size`, `pool`, `garage`, `age`, `lot`, `view`, `location`, `time`, `credits`, `other`; left out, it's taken from the label; never a condition amount: the script adds the condition line from the levels, and stops on a typed one), optional `close_date` (`YYYY-MM-DD`, when the export doesn't have the sale), and 1–3 `bullets`: judgment, why the sale is a comp and what its adjustments are about, in words. The card's sale line (price, date, size, beds and baths, pool, lot, distance) comes from the export, and each adjustment prints with its amount, adding up to the adjusted value. compute.py computes each adjusted value and the summary table (plus the "Your Home (Recommended List)" row); never type `adjusted` or `summary_rows`. It warns when a comp's adjustments pass 15% net or 25% gross of its sale price.
- Optional `condition_values`: `{level: dollars over an original home}`, from paired sales or the agent's rates, scaled to the price: needed outside the built-in market (and for a home outside `cma.calibrated_for` when the agent has better rates).
- `time_adjustment` (optional, `method.md`): `{rate_per_quarter, prices, cutoff}`. The script adds each card's time line and names the rate and cutoff in the method line.
- Judgment: `intro` (how the comps were chosen), `method_note` (caveats the method line doesn't say), `lean` (which way the range leans and why). The script writes the count and dates of the sales, the method line naming each kind of adjustment with its amounts, the adjusted span and median, the strongest match (the smallest adjustments inside the range, tagged on its card and on the deck) and the highest sale (the appraisal ceiling).

## scatter

Optional `heading` (Title Case); `subject_label_pos` and each callout's `side` (`left`, `right`, `above` or `below`); `callouts` (1–3 `{address, side}`, each a home the chart plots: a sale or an active listing; the script labels it from its address, "(For Sale)" on a listing); judgment `takeaway`; optional `min_size_ratio`/`max_size_ratio`/`fit_size_ratio` (0.6/1.4/1.6). The script writes what the chart plots, how many homes were left off, the caption with where the home sits against the size-only line, and how much of the price differences size explains.

## competition

Judgment `intro`; `rows`: `[address, status, price, sqft, pool ("Yes"/"No"), days, note]`: `price`, `sqft` and `days` plain numbers from the export, `note` judgment (why it matters to this seller, figure-free). Never the subject.

## market

`bullets` (3–5, each a `<strong>` finding plus what it means for price or timing): judgment, figure-free. The script builds the market table (homes sold, typical price, sale to original asking, days to contract, seller-paid costs, before and since the split) and its counts from the export, leaving out the home's own rows. Without an export there's no table. Optional `sale_to_list` (*number*, a fraction: what the sales you were given got against their final asking price after seller-paid costs) for the expected sales; without it (and without final list prices in the export) 97% is assumed and stated.

## pricing

| Field | Notes |
|---|---|
| `intro` | Judgment: frames the options as estimates and what really differs. The script adds how far apart the nets are |
| `stance` | `draw_offers`, `market` or `premium` (`method.md`, Pricing Stance). Left out, the one the market data suggests. The script sets the list price from it and builds the options: a new listing's are the three stances at fixed points of the range, high to low, the picked one recommended, named for it ("Market Price at $470,000"; the agent's own price "Our Price at $472,500"), merging any within 1% of another; a reprice's "Stay at Current Price" first, then cuts; a relist's top of the range, recommended and competing-offer, capped under the failed price ("List at $470,000") |
| `stance_reason` | Judgment, figure-free: why this home takes a different stance than the suggestion (required then; shown beside the stance either way) |
| `options` | Optional, only for the agent's own figures, keyed by role (a new listing: `draw_offers`, `market`, `premium`, the agent's own price under the key of the stance it replaced; a reprice: `stay`, `recommended`, `competing`; a relist: `top`, `recommended`, `competing`; another kind's key stops compute.py): `time` (a range with its unit, "3–6 weeks"), `months_to_contract` (a number), `seller_credit` (*number*), `note` (judgment), `expected_sale` (*number*: only the competing-offer option may sit above its list price), `closing_date` (`YYYY-MM-DD`). Left out, each is the script's: time from recent days on market, the credit from recent seller-paid costs, a note per option. An option of this kind the script didn't build (merged in a narrow range) is ignored |
| `note` | Judgment: the assumption behind any difference between options |

**One closing per option.** Each option closes on its own `closing_date`, else the later of `costs.expected_closing_date` and the launch date plus its time to contract plus a month to close. That one date sets its tax proration and its holding costs (from the report date to that closing); the net sheet shows it as Expected Closing.

**The net sheet** is one ledger per option: each line rounded once, each total the sum of the printed lines. Every assumption behind it is said once, in the notes block after the buyer payments.

## costs

All optional; see `costs.md`. `listing_fee_pct`, `buyer_broker_fee_pct` (fractions: `0.025` for 2.5%; without them the 2.5% default each, with no label), `transfer_tax_rate` (`0` where there is none), `transfer_tax_payer` (`seller`, `buyer` or `split`), `transfer_tax_label`, `title_payer`, `title_estimate_pct`, `annual_tax`, `expected_closing_date` (`YYYY-MM-DD`, the seller's goal), `current_tax_bill_paid` (true only when the agent says the seller paid this year's bill; otherwise after bills go out it's assumed unpaid and the notes say so), `mortgage_payoff` (*number*: a payoff the seller or agent states, used exactly as given) or `mortgage_balance` + `mortgage_rate` (only a loan BALANCE: compute.py adds a month's interest at `mortgage_rate`, else 4.5%, and the notes call it an estimate). `mortgage_rate` (percent) also sets the holding costs' loan interest, else 4.5% is assumed and stated, `title_fees` (the title company's quote: a total or `{name: amount}`), `hoa` (true/false), `hoa_monthly` (for holding costs), `other` (`[{label, amount}]`).

## buyer_payment

`rate` (percent), `rate_week` (optional `YYYY-MM-DD`: the Freddie Mac survey's week, named with the rate in the sources), `loan_type` (default `conventional`), `down_pct` (fraction, default 0.05), `insurance_annual` (optional; left out, compute.py estimates it, `costs.md`), `district` (looked up in the built-in millage) or `school_mills` + `total_mills`, `homestead` (default true), optional `hoa_monthly`, optional `flood_zone` (else the Flood Zone fact), optional `flood_insurance_annual` (a quote; without one the payment leaves flood out and the notes say to get a quote, never $0). The script writes the payment basis note from these.

## prep, needs, sources

`prep`: `intro` (judgment) plus 5–7 `items`, each `{step, detail, short, icon}`, all figure-free: `step` the step in a few words ("Document the new roof"), `detail` the report's sentence or two under "Before We List", `short` the one line page 1 (the first three items) and the deck's launch plan (the first six) show, `icon` one of the deck's icon names (`deck-content.md`). `needs`: 5–8 specific requests to the seller, figure-free. The method section (the sources, the rate's survey, the shelf life) and the closing notices are the script's.

## deck

See `deck-content.md`.
