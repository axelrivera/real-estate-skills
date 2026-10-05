# report.json

`assets/example-report.json` is a complete, approved report: copy it and replace every value. Body-text strings may contain `<strong>` and `<em>`, nothing else. Fields marked *number* are plain numbers (no `$` or commas).

## Contents

- Top level · subject · summary_page · recommendation · means · comps · scatter · competition · market · pricing · costs · buyer_payment · prep, needs, method · deck

## Top Level

| Field | Notes |
|---|---|
| `prepared_date` | Written out ("September 22, 2026"). Default: today |
| `as_of` | `YYYY-MM-DD`: the date the export was pulled (also stats.py's `--as-of`), used for the handoff, months of supply and date rules. Default: today |
| `export` | Path to the MLS export CSV (absolute, or relative to report.json's folder; keep them together in the temporary folder) (chart, trend line, deck method step, handoff market stats) |
| `split_date` | The `--split-date` you used with stats.py |
| `mls` | The MLS name: stats.py's `mls` (same as `--mls`). Without it compute.py assumes the one built in for the county |
| `export_columns` | For an MLS that isn't built in: `{field name: export header}` for `address`, `status`, `living_area`, `close_price`, `current_price` and any others the export has (same as stats.py `--columns`) |
| `deck` | The listing presentation's wording, as an object inside report.json (a path to a JSON file also works, relative to where you run the scripts). See `deck-content.md`; `competition` takes 1–3 cards, `scatter_takeaway` only when there is an export |
| `preliminary` | Optional: mark the report Preliminary yourself with the reason as a short sentence ("the home's condition and the tax bill are still to be confirmed, so the figures may change."), or `true` for a general reason. compute.py also sets it when a cost has no value at all, with that reason; page 1 and the chat reply use `preliminary_reason` |
| `labels` | Optional overrides of fixed wording |
| `reprice` | Only for the agent's own current listing, priced again: stats.py's `reprice`, `{current_price, days_on_market}` (*numbers*) and optional `original_price` (the price it started at; compute.py also finds it in the export). The report and reply show its price history (`price_history`). Adds the Stay at Current Price check, "New List Price" wording and the "Before We Reprice" headings. The other options must be price cuts; `allow_increase: true` only when the agent asked to price it higher. Never for another brokerage's listing. compute.py gives Stay's expected sale by the rule in `method.md` (`reprice.stay_expected_sale`), and fills it when Stay's `expected_sale` is left out |
| `listing_history` | Every listing of the home that ended unsold (expired, withdrawn, canceled), however long ago, from the property report: `[{status, price, original_price, ended, days_on_market}]` (`price`, `original_price` *numbers*; `ended` `YYYY-MM-DD`, `YYYY-MM` or `YYYY`). Page 1, the deck and the reply name each one ("Expired in March 2017 after 184 days at $229,900, first listed at $239,900."). Left out, the export's own rows fill it |
| `relist` | When the home's own earlier listing expired, was canceled or withdrawn within the last 12 months (or undated), or the agent chose to treat a live listing as failed: stats.py's `relist` (`failed_price` *number*, optional `status`, `days_on_market`, `original_price`). No option may list above `failed_price` unless `reason_above` gives the agent's reason (`method.md`, A Relist); compute.py also finds it in the export when this is left out |

The agent's name, team, brokerage, license and contact come from the agent's profile (`--profile`), never from report.json; only the fields the profile has are shown.

## subject

| Field | Notes |
|---|---|
| `address` | Display form ("1438 Buttonbush Dr") |
| `property_type` | `single_family`, `condo`, `townhouse`, `multifamily` or `land`. Needed in Miami-Dade, where every type but single-family owes the 0.45% deed surtax |
| `mls_address` | Exactly as in the export's address column. Every row with it is left out of stats, chart and deck |
| `city`, `state`, `county` | `state` and `county` pick the market's closing costs, tax rules, millage and MLS format |
| `locality` | "City, ST ZIP · Subdivision · County". No MLS number: this isn't a listing yet. Keep the parts in this order, separated by " · ": page 1 puts the city line under the address and the rest at the right |
| `sqft` | *number*, heated area from the seller or public record |
| `latitude`, `longitude` | Optional *numbers*: the home's location, for distances when the export has no Distance column and no row for the home |
| `beds`, `baths`, `year_built`, `pool`, `hoa`, `subdivision` | For the handoff, the comp ranking and the estoppel line (`pool`, `hoa` true/false) |
| `roof_year` | Optional, for the handoff: the offer review's insurance check. The handoff also carries `costs.annual_tax`, `costs.hoa_monthly`, the buyer-payment millage and the flood zone (a FEMA code only) |
| `facts` | Ten `[label, value]`, labels in Title Case: Beds / Baths, Living Area, Lot, Built, Pool, Garage, HOA / CDD, Flood Zone, Current Taxes, Recent Updates |
| `summary` | 2–3 sentences: the home and its updates "as described by you", and what the report does |
| `summary_facts` | One line for page 1 ("4 bed · 2 bath · 1,849 sq ft · pool · built 1972") |

## summary_page (write it last)

`label` (default "Seller Summary"), `headline` (about 20 words at most), optional `key_stats` (3 `[value, label]`, labels in Title Case; leave them out: with an export page 1 shows the median adjusted comp, the recent sale-to-list ratio and days to contract now, without one the median adjusted value, the adjusted span and the number of comps. A value you write is a placeholder such as `{sale_to_list_recent}`: a typed market number that disagrees with the export stops the render), `why` (exactly 3, about 25 words at most each: the comps, the market, the competition), `first_steps` (exactly 3 `[heading, one line]` from `prep`, headings in Title Case), `next_step`. The expected sale ("About $382,000", the recommended option's), the dot plot, the options table and the net tile are computed; never type those numbers here.

## recommendation

`list_price`, `low`, `high` (*numbers*), optional `midpoint` (*number*; default the middle of low and high, used for the handoff), `paragraph` (4–5 sentences: the range, the price and why, and why a higher first price is a risk).

## means

3–5 bullets, each opening with a `<strong>` finding: expected negotiation, the first-weeks window, the appraisal ceiling, the value of documentation.

## comps

`intro`, `method_note`, `cards` (3–6, written to the seller: `address`, `sold_price` *number*, `seller_concessions` *number* (what the seller paid toward the buyer's costs, 0 if none), `adjustments` (`[{label, amount, kind}]`, Title Case labels, signed dollars: `{"label": "Renovation", "amount": 45000, "kind": "condition"}`; `kind` is one of `size`, `pool`, `garage`, `condition`, `age`, `lot`, `view`, `location`, `time`, `credits`, `other`, and the deck lists what was adjusted by kind in fixed words; left out, it's taken from the label), `meta`, `bullets` that explain the same adjustments in words, naming every adjustment over $1,000 with its amount (a size adjustment of -$1,100 is named too, or the card's adjusted value doesn't add up for the seller); the cards and the summary table share a page, so up to 5 cards take 2–3 sentences of about 20 words each, and 6 cards take 2 of about 15, still full sentences: five strong comps beat six squeezed ones), `summary_paragraph` (quote the median as `{median_adjusted}` and the span as `{adjusted_min}` to `{adjusted_max}`, never typed). compute.py computes each adjusted value (sale price − concessions + adjustments) and builds the summary table (plus the "Your Home (Recommended List)" row); never type `adjusted` or `summary_rows`. It warns when a comp's adjustments pass 15% net or 25% gross of its sale price.

## scatter

`heading` (Title Case), `intro` (may use `{trend_at_subject}`), `subject_label` (default "Your Home"), `subject_label_pos` and each callout's `side` (`left`, `right`, `above` or `below`), `callouts` (1–3 `{address, label, side}`, labels in Title Case: the street address as on the cards and in the competition table, street type included, plus a short tag when needed: "1471 Sedgefield Ct (For Sale)", never "1471 Sedgefield (For Sale)"), optional `after_paragraph` (may use `{trend_at_subject}`, `{r2_share}`), optional `min_size_ratio`/`max_size_ratio`/`fit_size_ratio` (0.6/1.4/1.6). The dashed line is fit to sales from subject size ÷ `fit_size_ratio` to × `fit_size_ratio`; sales priced far off it (and listings wildly off it) are left out of the line and off the chart, never a comp card, and the script adds a note with the count. The script adds a caption under the chart that explains the dashed line and says how far above or below it the home sits; don't repeat that in `intro` or `after_paragraph`.

## competition

`intro`, `rows`: `[address, status, price` *number*`, sqft` *number*`, "Yes"/"No", days, notes]`. Never the subject.

## market

`intro`, `bullets` (3–5, each tied to price or timing), and with an export no table: leave `columns` and `rows` out and the script builds it from the export's two periods. Without an export, `columns` and `rows` from the sales you were given (headers and row names in Title Case), and optional `sale_to_list` (*number*, a fraction: what those sales got against their final asking price after seller-paid costs) for the expected sales (also used with an export whose sold rows don't carry the final list price); without it 97% is assumed and stated. In wording, a market number is its placeholder (`{sale_to_list_recent}`, `{days_recent}`, `{credit_share_recent}`, `{credit_amount_recent}`, `{median_price_recent}`, `{sold_recent}`, each also `_early`); a typed one that disagrees with the export stops the render, and so does a sentence that puts the recent period at another month than the split's (write `{split_month}`; a time adjustment's own cutoff, in `comps.method_note` or a sentence about adjusting, is its own date and isn't checked). Months of supply is always `{months_supply}` ("about {months_supply} of supply", stats.py's recent pace), never typed or turned into words like "a month and a half": compute.py warns `months_supply_typed`.

## pricing

| Field | Notes |
|---|---|
| `intro` | Frames the options as estimates; says whether the nets are close |
| `strategies` | 3 of `{label, list_price, time, seller_credit, note}` (*numbers* for the money), plus `expected_sale` only when the agent gave their own figure (it's marked as ours in the report): left out, compute.py sets it to the list price times the recent sale-to-final-list ratio, plus that option's seller credit, to $500, never below the range, never above list (but the competing-offer option) or the range, and an option above the recommended price expects the recommended one's sale, in order: top of the range, recommended, competing-offer (a reprice has no top-of-range option: "Stay at Current Price" first, at `reprice.current_price`, then the recommended cut and the competing-offer price, all below the current price; a relist caps the top-of-range option at `relist.failed_price` or drops it). `time` is a range with its unit ("3–6 weeks"); optional `months_to_contract` (a number) overrides it for holding costs. Only the competing-offer option may have `expected_sale` above its list price. A higher list price never expects a lower sale than a lower one (compute.py warns `expected_sale_order`): its cost is time and holding costs. A reprice's Stay leaves `expected_sale` out: compute.py fills it by the rule |
| `recommended_index` | The recommended row (usually 1); its `list_price` must equal `recommendation.list_price` |
| `competing_offer_upside` | `true` when the competing-offer option nets more than the recommended one and `note` says that net depends on competing offers showing up (clears compute.py's `bottom_nets_more` warning). Page 1's options note then adds that caveat on its own (`competing_offer_caveat`) |
| `note` | The assumption behind any difference between options (shown after "*Before paying off any mortgage.") |
| `net_intro` | Optional sentence above the net sheet |
| `net_note` | What the net sheet leaves out: repairs, carrying costs. The standard-terms, commission, tax and title-fee notes are added automatically |

## costs

All optional; see `costs.md`. `listing_fee_pct`, `buyer_broker_fee_pct` (fractions: `0.025` for 2.5%; without them 2.5% each is assumed and labeled), `transfer_tax_rate` (the state's rate from a trusted source; `0` where there is none), `transfer_tax_payer` (`seller`, `buyer` or `split`), `transfer_tax_label`, `title_payer`, `title_estimate_pct`, `annual_tax`, `expected_closing_date` (`YYYY-MM-DD`, the seller's goal: each option's tax proration runs to it, or to its time to contract plus a month when that's later, so a slow option closing next year owes this year's whole bill; or `closing_date` on a pricing option; with neither, the time alone dates it), `current_tax_bill_paid` (true only when the agent says the seller paid this year's bill; leave it out otherwise: after bills go out it's assumed unpaid and labeled so), `mortgage_payoff` (*number*, from a payoff statement, or a figure the seller gave, labeled "Your Estimate") or `mortgage_balance` + `mortgage_rate` (percent; an estimate: a month's interest and a $500 cushion are added; `mortgage_rate` also sets the holding costs' loan interest, else 4.5% is assumed and stated), `title_fees` (the title company's quote: a total or `{name: amount}`; replaces the built-in fees), `hoa` (true/false), `hoa_monthly` (for holding costs), `other` (`[{label, amount}]`).

## buyer_payment

`rate` (percent), `loan_type` (default `conventional`), `down_pct` (fraction, default 0.05), `insurance_annual` (optional: a quote or the agent's figure; left out, compute.py estimates it, `costs.md`), `district` (looked up in the built-in millage) or `school_mills` + `total_mills`, `homestead` (default true), optional `hoa_monthly`, optional `flood_zone` (else the Flood Zone fact), optional `flood_insurance_annual` (a quote; without one the payment leaves flood out and the note says to get a quote, never $0), optional `note` (assumptions and the rate's week; a default is written when it's missing; the flood rule is added to it).

## prep, needs, method

`prep`: `intro` plus 5–7 `items`, each with a `<strong>` lead (shown as "Before We List"). `needs`: 5–8 specific requests to the seller. `method`: two paragraphs, sources with dates, then the not-an-appraisal statement, the estimate caveats and the shelf life.

## deck

See `deck-content.md`.
