# Listing Presentation: Slides and `deck` Wording

The deck is the conversation piece for the appointment; the PDF report is the leave-behind, so slides carry only the notices they must, and the detail behind a table goes in its speaker notes. It shows only the findings that drive the price, in the order a seller follows the logic. Every number on a slide comes from compute.py (the same numbers as the PDF), and every color from the agent's brand palette. `deck` in report.json holds only condensed wording and speaker notes; start from `assets/example-deck-content.json`.

## Slide Map (Fixed Order)

| # | Slide | Numbers from | Wording from `deck` |
|---|---|---|---|
| 1 | Title (dark) | agent's profile, date | `title`, `subtitle` |
| 2 | Our Recommendation | recommendation, `summary_page.expected_sale` | `recommendation_why`, optional `expected_sub` |
| 3 | How We Priced It (4 numbered steps and the recommendation card) | sales in the export, comps, adjusted min/max/median, list price | optional `sold_line`, `comps_basis` |
| 4 | What Buyers Will Pay For (the paperwork box only when there are `document_items`) | — | `value_drivers`, `document_items` |
| 5 | What Comparable Homes Sold For (dot plot, range band, price line) | comp cards' adjusted values | `comp_lines`, `comps_takeaway` |
| 6 | Where Your Home Fits in the Neighborhood, or `scatter_title` (native scatter; left out when there's no MLS export) | export + the comp cards | `scatter_takeaway`, optional `scatter_title` |
| 7 | How the Market Has Changed (or `market_title`) | — | `market_title`, `market_periods`, `market_period_labels`, `market_stats`, `market_takeaway` |
| 8 | Your Competition (1–3 cards; fewer when there are fewer real competitors) | prices from the report's competition table | `competition`, `competition_takeaway` |
| 9 | Three Ways to Price It (the title follows the number of strategies) | strategies | `strategy_takeaway` |
| 10 | What You Walk Away With (native column chart) | computed nets | `strategy_takeaway` |
| 11 | How Buyers See Your Price | computed payments | `payment_takeaway` |
| 12 | Launch Plan (3–6 cards) | — | `launch_plan` |
| 13 | Next Steps (dark) | agent contact | `needs_short`, `timeline` |
| A1 | Appendix: Estimated Net Proceeds (table, a short note; the full notes in speaker notes) | computed net sheet | — |
| A2 | Appendix: Comparable Sales (table, the disclaimer and notices; the rest in speaker notes) | `comps.summary_rows` | `adjustments_summary` (speaker notes) |

## Fields

| Field | Format |
|---|---|
| `title`, `subtitle` | "Pricing 1438 Buttonbush Dr"; "Listing Presentation · City, Subdivision" (Title Case) |
| `recommendation_why` | One sentence, about 25 words at most |
| `value_drivers` | 2–4 `[heading, one line, icon]`, headings in Title Case: the features the adjustments credit for this home. A dollar figure in a driver must be one of this report's comp adjustments ("Worth $30,000 to $45,000 against the partly updated and dated sales" only when those adjustments are on the comp cards); when every comp shares the feature, there's no adjustment, so say what it does without a number. compute.py warns `driver_amount` on any other figure |
| `document_items` | 0–2 `[heading, one line, icon]`, headings in Title Case: upgrades this home has that need paperwork to count (a roof or permits the seller controls). None is fine: the box is left out |
| `comp_lines` | `{comp card address: "why it matters, under 45 characters"}` |
| `*_takeaway` | One or two short sentences: the single point of that slide |
| `sold_line` | Optional; default "sales within a mile since April", from the export's distances and dates. Without an export the slide starts at the comps (no separate "sales reviewed" step); write `sold_line` only when you reviewed more sales than you used |
| `comps_basis` | Optional; what the comps were matched on, for step 2 ("size, pool, age and neighborhood"; "size, floor, view and building" for a condo). Default "closest matches to your home" |
| `expected_sub` | Optional line under the expected sale. Default: "After the negotiating that is normal now" when the expected sale is below list, "With competing offers likely at this price" when it's at or above |
| `scatter_title` | Optional scatter slide title in Title Case ("Where Your Unit Fits in the Building") |
| `market_title` | Optional slide title in Title Case; default "How the Market Has Changed" |
| `market_periods` | Optional `[earlier, recent]` for the subtitle ("April–June"); default from the split date |
| `market_period_labels` | Optional short tags on each card; default "Earlier" / "Now" |
| `market_stats` | 2–4 `[label, earlier value, recent value, icon]`, labels in Title Case, from stats.py (plus the rate change only when you found a sourced earlier rate; otherwise leave that card out). Without an export there are no two periods: write 2–4 one-value cards, `[label, value, icon]`, from the sales you were given (median adjusted value, price per sq ft, the share with seller credits), never a split you'd have to invent |
| `competition` | 1–3 `[address, status line, one-line why]`, only real competitors; the address must be in the report's competition rows (the price comes from there) |
| `launch_plan` | 3–6 `[short heading, one line, icon]`, headings in Title Case |
| `needs_short` | Up to 5 short items from `needs` |
| `timeline` | 2–5 `[when, what]` ("This Week", "Week 2"), including the price-review point |
| `adjustments_summary` | One sentence with the adjustment rates used (from `method_note`); it goes in the appendix's speaker notes |
| `notes` | Speaker notes keyed `recommendation, method, drivers, comps, scatter, market, competition, strategies, nets, payments, launch, next`: where each number comes from and what the agent should say |

**Placeholders.** Never type a computed number. Write `{list_price}`, `{per_10k}`, `{net_spread}` (or `{net_spread_about}`, which already reads "about $5,000"), `{recommended_net}`, `{median_adjusted}`, `{adjusted_min}`, `{adjusted_max}`, `{trend_at_subject}`, `{low}`, `{high}`, and `{current_price}` on a reprice or `{failed_price}` on a relist, and the builder fills them in ("Every $10,000 is about {per_10k} a month"). They're the same placeholders as the report's (`report-data.md`). `{net_spread}` and the net slide's bars compare the options after holding costs when they're counted (the subtitle says so), matching the net sheet's last row; `{recommended_net}` is the recommended option's net on the same basis, as page 1 shows it.

**Icons.** The last element of a driver, paperwork item, market stat or launch step names its icon, so the picture matches what the text says: `kitchen`, `renovation`, `repairs`, `tools`, `paint`, `pool`, `bedroom`, `bath`, `water`, `waterfront`, `view`, `parking`, `garage`, `lot`, `yard`, `location`, `size`, `layout`, `building`, `home`, `roof`, `solar`, `energy`, `ac`, `heating`, `security`, `insurance`, `document`, `permit`, `contract`, `inspection`, `photos`, `marketing`, `sign`, `showings`, `staging`, `cleaning`, `price`, `money`, `dollar`, `percent`, `time`, `calendar`, `trend`, `chart`, `inventory`, `negotiation`, `star`, `check`. Left out, it's a neutral star, document, chart or check.

**This home only.** The example file is a single-family pool home in Florida. Write the drivers, paperwork items, comps basis and launch steps from this home's features and this market; never keep the example's pool, roof or permits when the home doesn't have them (a condo's roof usually belongs to the association). Use fewer items rather than filler.

Keep every line short: the builder uses fixed boxes, and long text overflows. Cut words rather than shrink fonts.

## Checking the Deck

The deck is built with pptxgenjs (native, editable charts; speaker notes on every content slide). Every text is measured and set at the largest size that fits its box; text that doesn't fit even at the smallest size is printed as `Check: slide N (...): deck.<field> "..." doesn't fit its box`. Shorten that field in `deck` and rebuild.

The script also writes `<address>-Listing-Presentation.pdf`, a copy of the slides made with LibreOffice, next to the PPTX. Deliver it with the PPTX as a backup, and use it to look at every slide:

```
pdftoppm -jpeg -r 80 <address>-Listing-Presentation.pdf slide
```

Look for text crowding its box, dot-plot labels colliding, and the "Expected sale" card fitting. Never hand-edit the .pptx. When LibreOffice isn't available the script says so and delivers the PPTX alone.
