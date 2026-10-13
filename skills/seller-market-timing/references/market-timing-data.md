# Market Timing Data

Every field of `market-timing.json`, the working file compute.py and render.py read. Write it in a temporary folder (`references/saved-files.md`, Working Files). Copy `assets/example-market-timing.json` and replace the values. Only `export` and the state are needed. Dates are `YYYY-MM-DD`.

Everything on the chart is data from the export, counted by the script. The only judgment fields are `area` (a name) and `season_override` (the agent's own season).

| Field | What it is |
|---|---|
| `export` | Path to the MLS export (CSV) of closed sales: as written, or beside `market-timing.json` (required) |
| `area` | The neighborhood or subdivision name for the subtitle, in Title Case ("Sample Ridge"). A name only: no figures, no description |
| `state`, `county` | Where the area is. They pick the built-in MLS (Stellar for its Florida counties) and so the export's column names. Never guess them from a subdivision name |
| `mls` | The MLS name, when the county doesn't settle it |
| `export_columns` | For an MLS that isn't built in: `{field: header}` for at least `address`, `status`, `close_price`, `close_date`, plus `contract_date` and `days_on_market` when the export has them (example below) |
| `as_of` | Today's date as the agent gave it; without it, the computer's date |
| `lookback_months` | `12`, `24` (default) or `36`. Whole years only, so every month is counted the same number of times |
| `season_override` | The agent's busy season as month numbers in a row (`[2, 3, 4, 5]`, or `[11, 12, 1, 2]` across the new year). Replaces the season the sales show; the run says so |
| `sample` | `true` only for mock data: marks the page Sample Data |

## What the Script Does With the Export

- **Which sales:** closed sales with a sold price. Listings, pending sales and rows without a price are left off and counted in a warning.
- **Which date:** the contract date when at least half the sales have one (when buyers committed); otherwise the close date, with a warning that the pattern runs about a month late. A sale without a contract date in a contract-date export is placed by its close date and counted.
- **The window:** whole months ending before the current month, and before last month too when placed by contract date (last month's contracts are still closing). When the export starts later than the window, the chart covers what's there and a warning says how many months to export.
- **Busy season:** a month is busy when its sales per year are at or above the average month's. Two to seven busy months in a row make a season (December runs into January), when they hold well over their share of the year's sales. Up to two seasons are boxed. The busiest month gets its own box when it has at least half again the average month's sales.
- **Too few sales:** under 20 in the window, the chart shows the dots without boxes and a warning says why.
- **When to list:** the main season's first day less the median days on market (CDOM), as early, mid or late in a month. Only with contract dates and CDOM.

## An MLS That Isn't Built In

Map the export's headers to the field names, for example:

```json
"export_columns": {
  "address": "Address",
  "status": "Status",
  "close_price": "Sold Price",
  "close_date": "Closing Date",
  "contract_date": "Pending Date",
  "days_on_market": "DOM"
}
```

A status of Sold, Closed or SLD counts as a closed sale.
