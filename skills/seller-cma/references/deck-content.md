# Listing Presentation: Slides and `deck` Wording

The deck is the conversation piece for the appointment; the PDF report is the leave-behind, so slides carry only the notices they must, and the detail behind a table goes in its speaker notes. It shows only the findings that drive the price, in the order a seller follows the logic. Every figure, date and count on a slide comes from compute.py (the same figures as the PDF, already formatted), and every color from the agent's brand palette. `deck` in report.json holds only condensed judgment wording and speaker notes, figure-free like the report's (no digits, `$`, `%`, months, seasons, weekdays or `{placeholders}`, and nothing about who owns or lives in the home: compute.py names any field that has one); start from `assets/example-deck-content.json`.

## Slide Map (Fixed Order)

| # | Slide | Figures and facts from the model | Wording from `deck` |
|---|---|---|---|
| 1 | Title (dark): "Pricing" and the address, "Listing Presentation" with the city and subdivision, always | agent's profile, date | optional `tagline` (a line of your own under them) |
| 2 | Our Recommendation | the list price, the range, the expected sale and its line, the listing history | `recommendation_why` |
| 3 | How We Priced It (numbered steps and the recommendation card) | sales in the export, comps, adjusted span and median, the adjustments line | optional `comps_basis` |
| 4 | What Buyers Will Pay For (the paperwork box only when there are `document_items`) | none | `value_drivers`, `document_items` |
| 5 | What Comparable Homes Sold For (dot plot, range band, price line) | the comps' adjusted values; "Strongest match" on the script's pick | `comp_lines`, `comps_takeaway` |
| 6 | Where Your Home Fits in the Neighborhood, or `scatter_title` (native scatter, the range band, a legend drawn from the series plotted; left out without an MLS export) | the report's chart points and trend | `scatter_takeaway`, optional `scatter_title` |
| 7 | How the Market Has Changed (or `market_title`) | the export's two periods (without an export, one-value cards from the comps) | optional `market_title`, `market_takeaway` |
| 8 | Your Competition (1–3 cards) | each home's price, status and days from the report's competition table | `competition`, `competition_takeaway` |
| 9 | Three Ways to Price It (the title follows the number of strategies) | strategies | `strategy_takeaway` |
| 10 | What You Walk Away With (native column chart, each bar labeled) | nets after holding costs and their spread | `strategy_takeaway` |
| 11 | How Buyers See Your Price | payments, the per-$10,000 line | `payment_takeaway` |
| 12 | Launch Plan (the first six `prep.items`: each step, its short line and icon) | none | none (`prep.items` in report.json) |
| 13 | Next Steps (dark) | the go-live date and price in the timeline, agent contact | `needs_short`, `timeline` |
| A1 | Appendix: Estimated Net Proceeds (the report's net sheet; the commission and not-included notes under it, every note in speaker notes) | net sheet | none |
| A2 | Appendix: Comparable Sales (the report's table and the closing notices) | comps table | none |

## Fields

| Field | Format |
|---|---|
| `tagline` | Optional, one short line for the cover ("Updated pool home on a quiet street"). The cover keeps its title and "Listing Presentation" line either way |
| `recommendation_why` | One sentence, about 25 words at most |
| `value_drivers` | 2–4 `[heading, one line, icon]`, headings in Title Case: the features the adjustments credit for this home, in words (the amounts are on the report's comp cards) |
| `document_items` | 0–2 `[heading, one line, icon]`, headings in Title Case: upgrades this home has that need paperwork to count. None is fine: the box is left out |
| `comp_lines` | `{comp card address: "why it matters, under 45 characters"}`. The slide leads the strongest match's line with "Strongest match" itself |
| `*_takeaway` | One or two short sentences: the single point of that slide |
| `comps_basis` | Optional; what the comps were matched on, for step 2 ("size, pool, age and neighborhood"; "size, floor, view and building" for a condo) |
| `scatter_title`, `market_title` | Optional slide titles in Title Case ("Where Your Unit Fits in the Building") |
| `competition` | 1–3 `[address, one-line why]`, only real competitors; the address must be in the report's competition rows (price, status and days come from there) |
| `needs_short` | Up to 5 short items from `needs` |
| `timeline` | 1–4 `[when, what]`, `when` one of `now` ("This Week"), `before` ("Before Launch") or `after` ("After Launch"); the script adds the go-live step with its date and price between them, the same launch date as the report. Put the price-review point `after` |
| `notes` | Speaker notes keyed `recommendation, method, drivers, comps, scatter, market, competition, strategies, nets, payments, launch, next`: what the agent should say, figure-free (the slide shows the figures). The appendix slides' speaker notes carry the report's notes and adjustments line on their own |

**Icons.** The last element of a driver or paperwork item, and a `prep.items` step's `icon`, names its icon, so the picture matches what the text says: `kitchen`, `renovation`, `repairs`, `tools`, `paint`, `pool`, `bedroom`, `bath`, `water`, `waterfront`, `view`, `parking`, `garage`, `lot`, `yard`, `location`, `size`, `layout`, `building`, `home`, `roof`, `solar`, `energy`, `ac`, `heating`, `security`, `insurance`, `document`, `permit`, `contract`, `inspection`, `photos`, `marketing`, `sign`, `showings`, `staging`, `cleaning`, `price`, `money`, `dollar`, `percent`, `time`, `calendar`, `trend`, `chart`, `inventory`, `negotiation`, `star`, `check`. Left out, it's a neutral star, document or check.

**This home only.** The example file is a single-family pool home in Florida. Write the drivers, paperwork items, comps basis and launch steps from this home's features and this market; never keep the example's pool, roof or permits when the home doesn't have them (a condo's roof usually belongs to the association). Use fewer items rather than filler.

Keep every line short: the builder uses fixed boxes, and long text overflows. Cut words rather than shrink fonts.

## Checking the Deck

The deck is built with pptxgenjs (native, editable charts; speaker notes on every content slide). Every text is measured and set at the largest size that fits its box; text that doesn't fit even at the smallest size, or would reach the footer, is printed as `Check: slide N (...): deck.<field> "..." doesn't fit its box`. Shorten that field in `deck` (or the `prep.items` step it names) and rebuild.

The script also writes `<address>-Listing-Presentation.pdf`, a copy of the slides made with LibreOffice, next to the PPTX. Deliver it with the PPTX as a backup, and use it to look at every slide:

```
pdftoppm -jpeg -r 80 <address>-Listing-Presentation.pdf slide
```

Look for text crowding its box and dot-plot labels colliding. Never hand-edit the .pptx. When LibreOffice isn't available the script says so and delivers the PPTX alone.
