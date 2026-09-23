# report.json

`assets/example-report.json` is a complete, approved report: copy it and replace every value. Body-text strings may contain `<strong>` and `<em>`, nothing else. Money fields marked *number* are plain numbers (no `$` or commas).

## Contents

- Top level · subject · summary_page · bottom_line · history · offer_plan · offer · comps · scatter · competition · market · costs · watch · method

## Top level

| Field | Notes |
|---|---|
| `language` | `en` or `es` |
| `prepared_date` | Written out ("September 22, 2026"; Spanish "22 de septiembre de 2026"). Default: today |
| `as_of` | `YYYY-MM-DD` for the handoff. Default: today |
| `export` | Path to the MLS export CSV (used for the chart and the handoff's market stats) |
| `split_date` | The `--split-date` you used with stats.py |
| `labels` | Optional overrides of fixed wording |

The agent's name, brokerage, license and contact come from the agent profile (`--agent`), never from report.json.

## subject

| Field | Notes |
|---|---|
| `address` | Display form ("517 Hickorywood Ave") |
| `mls_address` | Exactly as in the export's address column |
| `city`, `state`, `county` | `state` and `county` pick the market's tax rules, millage and MLS format |
| `locality` | "City, ST ZIP · Subdivision · County · MLS #" |
| `list_price`, `sqft` | *numbers* |
| `beds`, `baths`, `year_built`, `pool` | For the handoff (`pool` true/false) |
| `subdivision` | As in the export (improves the handoff's comp ranking) |
| `facts` | Ten `[label, value]` in this order: List price, Price per sq ft, Beds / baths, Living area, Lot, Built, Pool, Garage, HOA / CDD, Flood zone |
| `summary` | 2–3 sentences: what the home is and anything unusual about the sale |
| `summary_facts` | Short line for page 1 ("4 bed · 2 bath · 1,849 sq ft · pool · built 1972") |

## summary_page

`label` (default "Buyer summary"), `headline`, `key_stats` (exactly 3 `[value, label]`), `why` (exactly 3), `check_first` (exactly 3 `[heading, one line]`), `next_step`. The dot plot and the cost table are computed.

## bottom_line

`low`, `high`, `midpoint` (*numbers*), `paragraph`.

## history (whenever there's more than the current listing)

`heading` (a finding), `intro`, `rows` (`[date, event, price]` strings, price like "$474,500" or "—"), `after`.

## offer_plan

`intro`; `opening`, `target_low`, `target_high`, `walk_away` (*numbers*); `why_opening`, `why_target`, `why_walk_away`; optional `credit_alt` `{price, credit}`; `conditions` (lowercase clause completing "This assumes: …").

## offer

`heading` ("Negotiating points") and 2–4 `bullets`, each starting with a `<strong>` lead-in.

## comps

`intro`, `method_note`, `cards` (3–6: `address`, `adjusted` *number*, `meta`, 2–3 `bullets`), `summary_rows` (`[address, sold_price, seller_paid, adjusted]` *numbers*, highest adjusted first; the subject row is added), `summary_paragraph`.

## scatter (standard)

`heading`, `intro` (may use `{trend_at_subject}`), `renovated` (export addresses of sold, renovated private-pool homes), `subject_label`, `subject_label_pos` and each callout's `side` (`left`, `right`, `above` or `below`), `callouts` (1–3 `{address, label, side}`), `after_paragraph` (may use `{trend_at_subject}` and `{r2_share}`, which reads like "most" or "only about a third"), optional `min_size_ratio`/`max_size_ratio`/`fit_size_ratio` (defaults 0.6/1.4/1.6).

## competition

`intro`, `rows`: `[address, status, price, sqft, pool ("Yes"/"No"), days, notes]`.

## market

`intro`, `columns`, `rows` (strings you format from stats.py's numbers: "95.2%", "22 days"), `bullets` (3–5, each a `<strong>` finding plus what it means for the offer).

## costs

- `taxes`: `heading`, `intro`, `current_bill`, `current_year`, `purchase_price`, `homestead`, `jurisdictions` (1–2 of `{label, short, district}` or `{label, short, school_mills, total_mills}`), `note`, `after_paragraph` (escrow warning).
- `insurance`: `paragraph`.
- `payment`: `intro`, `price`, `rate` (percent), `insurance_annual` (placeholder), `tax_jurisdiction_index`, `scenarios` (`{label, type, down_pct}`, `down_pct` a fraction: 0.05 for 5%), optional `hoa_cdd_monthly`, optional `note`.
- `credit_scenarios`: `intro`, `loan_type`, `down_pct` (fraction), `closing_costs` or `closing_cost_pct` (fraction), `scenarios` (2–4 `{price, credit}`), `after_paragraph`, optional `buydown` `{price, credit}`. See `offer-plan.md`.

## watch

`items` (each with a `<strong>` lead) and 5–7 `questions`.

## method

Two paragraphs: sources with dates; the not-an-appraisal statement and shelf life.
