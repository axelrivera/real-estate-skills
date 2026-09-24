# report.json

`assets/example-report.json` is a complete, approved report: copy it and replace every value. Body-text strings may contain `<strong>` and `<em>`, nothing else. Fields marked *number* are plain numbers (no `$` or commas).

## Contents

- Top level · subject · summary_page · recommendation · means · comps · scatter · competition · market · pricing · costs · buyer_payment · prep, needs, method · deck

## Top level

| Field | Notes |
|---|---|
| `prepared_date` | Written out ("September 22, 2026"). Default: today |
| `as_of` | `YYYY-MM-DD` for the handoff. Default: today |
| `export` | Path to the MLS export CSV (chart, trend line, deck method step, handoff market stats) |
| `split_date` | The `--split-date` you used with stats.py |
| `deck` | The listing presentation's wording, as an object inside report.json (a path to a JSON file also works, relative to where you run the scripts). See `deck-content.md`; `competition` takes 1–3 cards, `scatter_takeaway` only when there is an export |
| `preliminary` | Optional `true` to mark the report Preliminary yourself (compute.py also sets it when a local cost is missing) |
| `labels` | Optional overrides of fixed wording |

The agent's name, team, brokerage, license and contact come from the agent profile (`--agent`), never from report.json; only the fields the profile has are shown.

## subject

| Field | Notes |
|---|---|
| `address` | Display form ("517 Hickorywood Ave") |
| `mls_address` | Exactly as in the export's address column. Every row with it is left out of stats, chart and deck |
| `city`, `state`, `county` | `state` and `county` pick the market's closing costs, tax rules, millage and MLS format |
| `locality` | "City, ST ZIP · Subdivision · County". No MLS number: this isn't a listing yet |
| `sqft` | *number*, heated area from the seller or public record |
| `beds`, `baths`, `year_built`, `pool`, `hoa`, `subdivision` | For the handoff, the comp ranking and the estoppel line (`pool`, `hoa` true/false) |
| `facts` | Ten `[label, value]`, labels in Title Case: Beds / Baths, Living Area, Lot, Built, Pool, Garage, HOA / CDD, Flood Zone, Current Taxes, Recent Updates |
| `summary` | 2–3 sentences: the home and its updates "as described by you", and what the report does |
| `summary_facts` | One line for page 1 ("4 bed · 2 bath · 1,849 sq ft · pool · built 1972") |

## summary_page (write it last)

`label` (default "Seller Summary"), `expected_sale` (short phrase, "Low-to-mid $460,000s"; the deck uses it too), `headline` (≤ ~20 words), `key_stats` (exactly 3 `[value, label]`, labels in Title Case: the median adjusted comp, the recent sale-to-list ratio, days to contract now), `why` (exactly 3, ≤ ~25 words each: the comps, the market, the competition), `first_steps` (exactly 3 `[heading, one line]` from `prep`, headings in Title Case), `next_step`. The dot plot, the options table and the net tile are computed; never type those numbers here.

## recommendation

`list_price`, `low`, `high` (*numbers*), `paragraph` (4–5 sentences: the range, the price and why, and why a higher first price is a risk).

## means

3–5 bullets, each opening with a `<strong>` finding: expected negotiation, the first-weeks window, the appraisal ceiling, the value of documentation.

## comps

`intro`, `method_note`, `cards` (3–6 of `{address, adjusted` *number*`, meta, bullets}`, written to the seller), `summary_rows` (`[address, sold, seller_paid, adjusted]` *numbers*, highest adjusted first; the "Your Home (Recommended List)" row is added), `summary_paragraph`.

## scatter

`heading` (Title Case), `intro` (may use `{trend_at_subject}`), `renovated` (export addresses), `subject_label` (default "Your Home"), `subject_label_pos` and each callout's `side` (`left`, `right`, `above` or `below`), `callouts` (1–3 `{address, label, side}`, labels in Title Case), optional `after_paragraph` (may use `{trend_at_subject}`, `{r2_share}`), optional `min_size_ratio`/`max_size_ratio`/`fit_size_ratio` (0.6/1.4/1.6).

## competition

`intro`, `rows`: `[address, status, price` *number*`, sqft` *number*`, "Yes"/"No", days, notes]`. Never the subject.

## market

`intro`, `columns` and `rows` (column headers and row names in Title Case; cell strings you format from stats.py's numbers: "95.2%", "22 days"; without an export, from the sales you were given), `bullets` (3–5, each tied to price or timing).

## pricing

| Field | Notes |
|---|---|
| `intro` | Frames the options as estimates; says whether the nets are close |
| `strategies` | 3 of `{label, list_price, expected_sale, time, seller_credit, note}` (*numbers* for the money) |
| `recommended_index` | The recommended row (usually 1); its `list_price` must equal `recommendation.list_price` |
| `note` | The assumption behind any difference between options (shown after "*Before paying off any mortgage.") |
| `net_intro` | Optional sentence above the net sheet |
| `net_note` | What the net sheet leaves out: tax proration, repairs, carrying costs. The placeholder and title-fee notes are added automatically |

## costs

All optional; see `costs.md`. `listing_fee_pct`, `buyer_broker_fee_pct` (fractions: `0.025` for 2.5%), `mortgage_payoff` (*number*), `title_fees` (the title company's quote: a total or `{name: amount}`; replaces the built-in fees), `hoa` (true/false), `other` (`[{label, amount}]`).

## buyer_payment

`rate` (percent), `loan_type` (default `conventional`), `down_pct` (fraction, default 0.05), `insurance_annual` (placeholder), `district` (looked up in the market profile) or `school_mills` + `total_mills`, `homestead` (default true), optional `hoa_monthly`, optional `note` (assumptions and the rate's week; a default is written when it's missing).

## prep, needs, method

`prep`: `intro` plus 5–7 `items`, each with a `<strong>` lead (shown as "Before We List"). `needs`: 5–8 specific requests to the seller. `method`: two paragraphs, sources with dates, then the not-an-appraisal statement, the estimate caveats and the shelf life.

## deck

See `deck-content.md`.
