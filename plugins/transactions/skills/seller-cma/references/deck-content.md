# Listing presentation: slides and `deck` wording

The deck is the conversation piece for the appointment; the PDF is the leave-behind. It shows only the findings that drive the price, in the order a seller follows the logic. Every number on a slide comes from compute.py (the same numbers as the PDF), and every color from the agent's brand palette. `deck` in report.json holds only condensed wording and speaker notes; start from `assets/example-deck-content.json`.

## Slide map (fixed order)

| # | Slide | Numbers from | Wording from `deck` |
|---|---|---|---|
| 1 | Title (dark) | agent profile, date | `title`, `subtitle` |
| 2 | Our recommendation | recommendation, `summary_page.expected_sale` | `recommendation_why` |
| 3 | How we priced it (5 steps) | sales in the export, comps, adjusted min/max/median, list price | optional `sold_line` |
| 4 | What buyers will pay for | — | `value_drivers`, `document_items` |
| 5 | Comparable sales (dot plot, range band, price line) | comp cards' adjusted values | `comp_lines`, `comps_takeaway` |
| 6 | Where your home fits (native scatter; left out when there's no MLS export) | export + `scatter.renovated` | `scatter_takeaway` |
| 7 | The market | — | `market_title`, `market_periods`, `market_period_labels`, `market_stats`, `market_takeaway` |
| 8 | Your competition (1–3 cards; fewer when there are fewer real competitors) | prices from the report's competition table | `competition`, `competition_takeaway` |
| 9 | Three ways to price it | strategies | `strategy_takeaway` |
| 10 | What you walk away with (native column chart) | computed nets | `strategy_takeaway` |
| 11 | How buyers see your price | computed payments | `payment_takeaway` |
| 12 | Launch plan (6 cards) | — | `launch_plan` |
| 13 | Next steps (dark) | agent contact | `needs_short`, `timeline` |
| A1 | Appendix: net proceeds table and its notes | computed net sheet | — |
| A2 | Appendix: comparable sales | `comps.summary_rows` | `adjustments_summary` |

## Fields

| Field | Format |
|---|---|
| `title`, `subtitle` | "Pricing 517 Hickorywood Ave"; "Listing presentation · City, Subdivision" |
| `recommendation_why` | One sentence, ≤ ~25 words |
| `value_drivers` | Exactly 4 `[heading, one line]`: the features the adjustments credit |
| `document_items` | Exactly 2 `[heading, one line]`: upgrades that need paperwork to count |
| `comp_lines` | `{comp card address: "why it matters, under 45 characters"}` |
| `*_takeaway` | One or two short sentences: the single point of that slide |
| `sold_line` | Optional; default "sales within a mile since April", from the export's distances and dates |
| `market_title` | Optional; default "How the market has changed" |
| `market_periods` | Optional `[earlier, recent]` for the subtitle ("April–June"); default from the split date |
| `market_period_labels` | Optional short tags on each card; default "Earlier" / "Now" |
| `market_stats` | Exactly 4 `[label, earlier value, recent value]` from stats.py (plus the rate change) |
| `competition` | Exactly 3 `[address, status line, one-line why]`; the address must be in the report's competition rows (the price comes from there) |
| `launch_plan` | Exactly 6 `[short heading, one line]` |
| `needs_short` | Up to 5 short items from `needs` |
| `timeline` | Exactly 4 `[when, what]`, including the price-review point |
| `adjustments_summary` | One sentence with the adjustment rates used (from `method_note`) |
| `notes` | Speaker notes keyed `recommendation, method, drivers, comps, scatter, market, competition, strategies, nets, payments, launch, next`: where each number comes from and what the agent should say |

**Placeholders.** Never type a computed number. Write `{list_price}`, `{per_10k}`, `{net_spread}`, `{recommended_net}`, `{median_adjusted}`, `{trend_at_subject}`, `{low}` or `{high}` and the builder fills them in ("Every $10,000 is about {per_10k} a month").

Keep every line short: the builder uses fixed boxes, and long text overflows. Cut words rather than shrink fonts.

## Checking the deck

The deck is built with pptxgenjs (native, editable charts; speaker notes on every content slide). When LibreOffice is available, convert and look at every slide:

```
soffice --headless --convert-to pdf <file>.pptx
pdftoppm -jpeg -r 80 <file>.pdf slide
```

Look for text overflowing its box (shorten that field in `deck` and rebuild), dot-plot labels colliding, and the "Expected sale" card fitting. Never hand-edit the .pptx. LibreOffice draws the scatter's hollow "for sale now" markers without their outline; PowerPoint draws them correctly.
