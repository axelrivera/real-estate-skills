# Costs: taxes, insurance, payments

## Property taxes

The buyer's bill is based on the purchase price, not the seller's bill: in Florida a capped assessment (Save Our Homes, the 10% non-homestead cap) resets on sale. Other states differ; the market profile's `property_tax.reassessed_on_sale` says which.

- **Millage:** the market profile lists final rates by county and district (built in for seven Central Florida counties). In each `jurisdictions` entry, name the `district` and compute.py looks it up, or give `school_mills` and `total_mills` yourself from the county property appraiser. When you can't confirm whether the parcel is inside city limits, show both jurisdictions and ask the agent to check the parcel's taxing district.
- **Exemptions** come from the market profile (Florida homestead: the first $25,000 off every levy, the second $25,000 off non-school levies). The file-by date goes in the note.
- **Without millage**, compute.py estimates from the market's fallback rate and warns. Say it's an estimate, and find the real rates if you can.
- The estimate assumes the appraiser values the home at the purchase price. It often values it lower, so the estimate runs high: say so. Flat non-ad valorem assessments are excluded: say that too.
- Always include the first-year escrow warning: lenders often escrow on the seller's lower bill, then the payment jumps.

## Insurance

Don't quote a premium. Name the drivers for this house (roof age, wiring and plumbing era, wind mitigation, pool, flood zone), use a clearly labeled placeholder in the payment table, and tell the buyer to get a quote during the inspection period (in Florida, after the 4-point and wind-mitigation inspections).

Era flags worth raising when the year fits: 1965–1973 aluminum branch wiring; before about 1975 cast-iron drains (sewer camera inspection); 1978–1995 polybutylene supply lines; Federal Pacific or Zinsco panels in any year. A roof over about 15 years old makes insuring hard; if its age is unknown, or a claimed new roof disappears from later remarks, make it the first watch item.

## Payments

- **Rate:** the latest Freddie Mac weekly 30-year average. Cite the week in the chat reply and state it in the report.
- **Scenarios:** default Conventional 5%, FHA 3.5%, Conventional 20% (`type`: `conventional`, `fha`, `va`, `usda`). Mortgage insurance, FHA upfront premium and program limits come from the shared lending estimates; the report's note states them. The lender's numbers always win.
- `tax_jurisdiction_index` picks the jurisdiction the table uses; with two, the other appears as a comparison row.
- The script computes the table and "every $10,000 off the price lowers the payment by about…". Never hand-calculate payments.
