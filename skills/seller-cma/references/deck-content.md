# Listing Presentation: Slides and `deck` Wording

The deck is the conversation piece for the appointment; the PDF is the leave-behind. It shows only the findings that drive the price, in the order a seller follows the logic. Every number on a slide comes from compute.py (the same numbers as the PDF), and every color from the agent's brand palette. `deck` in report.json holds only condensed wording and speaker notes; start from `assets/example-deck-content.json`.

## Slide Map (Fixed Order)

| # | Slide | Numbers from | Wording from `deck` |
|---|---|---|---|
| 1 | Title (dark) | agent's profile, date | `title`, `subtitle` |
| 2 | Our Recommendation | recommendation, `summary_page.expected_sale` | `recommendation_why` |
| 3 | How We Priced It (5 steps) | sales in the export, comps, adjusted min/max/median, list price | optional `sold_line` |
| 4 | What Buyers Will Pay For | — | `value_drivers`, `document_items` |
| 5 | What Comparable Homes Sold For (dot plot, range band, price line) | comp cards' adjusted values | `comp_lines`, `comps_takeaway` |
| 6 | Where Your Home Fits in the Neighborhood (native scatter; left out when there's no MLS export) | export + the comp cards | `scatter_takeaway` |
| 7 | How the Market Has Changed (or `market_title`) | — | `market_title`, `market_periods`, `market_period_labels`, `market_stats`, `market_takeaway` |
| 8 | Your Competition (1–3 cards; fewer when there are fewer real competitors) | prices from the report's competition table | `competition`, `competition_takeaway` |
| 9 | Three Ways to Price It | strategies | `strategy_takeaway` |
| 10 | What You Walk Away With (native column chart) | computed nets | `strategy_takeaway` |
| 11 | How Buyers See Your Price | computed payments | `payment_takeaway` |
| 12 | Launch Plan (6 cards) | — | `launch_plan` |
| 13 | Next Steps (dark) | agent contact | `needs_short`, `timeline` |
| A1 | Appendix: Estimated Net Proceeds (table and its notes) | computed net sheet | — |
| A2 | Appendix: Comparable Sales | `comps.summary_rows` | `adjustments_summary` |

## Fields

| Field | Format |
|---|---|
| `title`, `subtitle` | "Pricing 517 Hickorywood Ave"; "Listing Presentation · City, Subdivision" (Title Case) |
| `recommendation_why` | One sentence, ≤ ~25 words |
| `value_drivers` | Exactly 4 `[heading, one line]`, headings in Title Case: the features the adjustments credit |
| `document_items` | Exactly 2 `[heading, one line]`, headings in Title Case: upgrades that need paperwork to count |
| `comp_lines` | `{comp card address: "why it matters, under 45 characters"}` |
| `*_takeaway` | One or two short sentences: the single point of that slide |
| `sold_line` | Optional; default "sales within a mile since April", from the export's distances and dates |
| `market_title` | Optional slide title in Title Case; default "How the Market Has Changed" |
| `market_periods` | Optional `[earlier, recent]` for the subtitle ("April–June"); default from the split date |
| `market_period_labels` | Optional short tags on each card; default "Earlier" / "Now" |
| `market_stats` | Exactly 4 `[label, earlier value, recent value]`, labels in Title Case, from stats.py (plus the rate change) |
| `competition` | Exactly 3 `[address, status line, one-line why]`; the address must be in the report's competition rows (the price comes from there) |
| `launch_plan` | Exactly 6 `[short heading, one line]`, headings in Title Case |
| `needs_short` | Up to 5 short items from `needs` |
| `timeline` | Exactly 4 `[when, what]` ("This Week", "Week 2"), including the price-review point |
| `adjustments_summary` | One sentence with the adjustment rates used (from `method_note`) |
| `notes` | Speaker notes keyed `recommendation, method, drivers, comps, scatter, market, competition, strategies, nets, payments, launch, next`: where each number comes from and what the agent should say |

**Placeholders.** Never type a computed number. Write `{list_price}`, `{per_10k}`, `{net_spread}`, `{recommended_net}`, `{median_adjusted}`, `{trend_at_subject}`, `{low}` or `{high}` and the builder fills them in ("Every $10,000 is about {per_10k} a month").

Keep every line short: the builder uses fixed boxes, and long text overflows. Cut words rather than shrink fonts.

## Checking the Deck

The deck is built with pptxgenjs (native, editable charts; speaker notes on every content slide). When LibreOffice is available, convert and look at every slide:

```
soffice --headless --convert-to pdf <file>.pptx
pdftoppm -jpeg -r 80 <file>.pdf slide
```

Look for text overflowing its box (shorten that field in `deck` and rebuild), dot-plot labels colliding, and the "Expected sale" card fitting. Never hand-edit the .pptx. LibreOffice draws the scatter's hollow "for sale now" markers without their outline; PowerPoint draws them correctly.
