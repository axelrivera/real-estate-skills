# Net Sheet Data

Every field of `net-sheet.json`, the working file compute.py and render.py read. Write it in a temporary folder (`references/saved-files.md`, Working Files). Copy `assets/example-net-sheet.json` and replace the values. Only `property.address`, the state and one price are needed; everything else is optional, and a missing value is either left out with a note or filled with a labeled estimate.

Amounts are plain numbers (`214000`, never `"$214,000"`). Every `*_pct` field is a fraction of price: `0.025` means 2.5%. The mortgage rate is a percent: `6.5`. Dates are `YYYY-MM-DD`.

## Top Level

| Field | What it is |
|---|---|
| `prepared_date` | Today's date as the agent gave it (`2026-10-01`); without it, the computer's date |
| `prepared_for` | The seller's name for the header ("Dana Morgan"), when the agent gives it |
| `closing_date` | The expected closing date: it sets the property tax proration |
| `closing_date_assumed` | `true` when the agent gave only a rough time ("mid-December"): the date is listed in `assumptions` and marked Assumed on the page |
| `mls` | The MLS name, when known (Stellar is built in) |
| `foreign_seller` | `true` when the agent says the seller is a foreign person: adds the FIRPTA note |
| `sample` | `true` only for mock data: marks the page Sample Data |

## property

| Field | What it is |
|---|---|
| `address` | Street address (required) |
| `city`, `county`, `state` | The location sets every local cost. The state is a two-letter code or name. Never guess the county or state from a subdivision or the MLS: ask |
| `property_type` | `single_family`, `condo`, `townhouse`, `multifamily` or `land`. Miami-Dade's 0.45% surtax applies to every type but single-family, so it's needed there. A unit number means `condo` unless the agent says otherwise |
| `property_type_assumed` | `true` when the type was inferred (a condo from a unit number): listed in `assumptions` and marked Assumed |
| `hoa` | `true` when there's an HOA or condo association (adds the estoppel or HOA documents fee); `false` for none |
| `hoa_monthly` | Monthly dues, shown in the fact row (implies `hoa`) |

## scenarios

One to three prices, each a column on the page. Three is the most that fits on one page: compute.py refuses a fourth.

| Field | What it is |
|---|---|
| `price` | The sale price (required) |
| `label` | The column's name in Title Case, when the price alone doesn't say it ("Current List Price", "After a Price Cut"). Default: the price, plus "with $9,000 Credit" when there's a credit |
| `seller_credit` | Seller-paid buyer closing costs or concessions in this scenario |
| `home_warranty` | A home warranty the seller pays for |
| `repairs` | Repairs or a repair credit the seller has agreed to or expects |
| `closing_date` | This scenario's own closing date, when it differs from the top-level one |
| `closing_date_assumed` | `true` when this scenario's own date is a rough one |

## costs

This sale's own numbers. Each one replaces a built-in value or an estimate (`references/local-costs.md`).

| Field | What it is |
|---|---|
| `listing_fee_pct`, `buyer_broker_fee_pct` | The listing agreement's terms (`0` when the seller won't pay the buyer's agent). Without them, 2.5% each, labeled Assumed |
| `mortgage_payoff` | The first mortgage payoff from a payoff letter or the seller's figure. `0` when the home is owned free and clear |
| `mortgage_balance`, `mortgage_rate` | A monthly statement's balance and rate, when there's no payoff figure: compute.py adds a month's interest and $500 of fees, labeled "Estimate from Balance" |
| `other_payoffs` | `[{label, amount}]`: a second mortgage, a HELOC, a solar loan or lease buyout. Each is its own row |
| `annual_tax` | This year's tax bill (the MLS sheet or the property report has it). With a closing date it adds the proration |
| `current_tax_bill_paid` | `true` only when the agent says the seller already paid this year's bill; `false` when the agent says it's unpaid |
| `tax_bill_due_date` | When this year's bill is due (`10-15` or `2026-10-15`): as the agent gives it, else from the county tax office's site when the closing is late in the year. A closing after it assumes the bill paid: the buyer credits the seller from closing to Dec 31, labeled Bill Assumed Paid. Without it, a closing after the bills go out assumes the bill unpaid |
| `other` | `[{label, amount}]` of other seller costs in every scenario: a survey, a permit closeout, an attorney's fee |
| `transfer_tax_rate`, `transfer_tax_payer`, `transfer_tax_label` | Outside Florida, the state's deed transfer tax from a trusted source (`references/local-costs.md`) |
| `title_payer`, `title_estimate_pct` | Who pays the owner's title policy here, and its rate when the market has no rate table |
| `title_fees` | A title company's quote: a total, or `{name: amount}` to itemize it |
| `hoa_estoppel_fee` | The association's actual estoppel or resale certificate fee |
