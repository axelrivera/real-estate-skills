# Local Costs

Where a report's local numbers come from, and how the agent improves them. Convention over questions: build the report first with good defaults, say once what's estimated, and let the agent correct it afterward.

## Where Each Number Comes From

The scripts take the location from the property (state and county from the listing or the address) and use the first of:

1. **This deal's own numbers:** what the agent put in the first message or sent after the first report (a title quote, the listing agreement's commission, the tax bill), and what you looked up (the state's transfer tax). They go in the data file's `costs` block (in buyer-offer-strategy's buyer file, `property.costs`).
2. **Built-in local values:** Florida state rates and county customs, Stellar MLS formats.
3. **National estimates,** named once in the report's notes: transfer tax 0.4% (none in the 15 states with no state transfer tax, such as Texas: built in, no lookup needed), owner's title 0.5% of price, title and settlement fees $1,200, a buyer's closing costs 3%, property tax 1.1% of price when there's no bill, insurance and utilities for holding costs.

Never use Florida's numbers for another state.

## How Reports Show Estimates

- **Once, in the notes.** Each report says which figures are estimates or assumed in one notes block (the notes under the net sheet, the payment table's note, "Assumptions & Data to Confirm", the offer review's "What to Confirm"), once each, in plain words.
- **Never in a label.** No "(Estimate)", "Assumed" or "(assumed)" in a column header, row label, tile or fact chip, and no per-row marks in a table: they change the layout and repeat what the notes say. A label that names the figure ("Estimated Net") is fine.
- **Commission defaults are defaults.** The default 2.5% + 2.5% gets no label anywhere; the brokerage lines show the rates, as they do for the agent's own terms. The reply still asks for the listing agreement's terms.

## Before the First Report

- **Don't ask about costs up front.** Build the report with what's there.
- **Read the listing first:** the tax bill, HOA dues, county, property type and flood zone are usually on the MLS sheet.
- **Transfer tax outside Florida:** the states with no state transfer tax (AK, AZ, ID, IN, KS, LA, MS, MO, MT, ND, NM, OR, TX, UT, WY) are built in as none, with a note to confirm local taxes; skip the search there. Elsewhere, search for the state's deed transfer tax. Use a rate only from a trusted source (the state's revenue department, the statute, or the county recorder or clerk) and cite it in your reply. Put it in that `costs` block as `transfer_tax_rate`, with `transfer_tax_payer` when the buyer pays or it's split, and `transfer_tax_label` for its local name in Title Case. When the sources disagree, the tax is layered or tiered, or no trusted source turns up, leave it out and let the national estimate stand (the notes name it).
- **No state or county:** never infer them from a subdivision, an MLS area or the MLS itself. Use the national estimates, mark the report Preliminary, and ask for the city and county. When the export comes from an MLS built in for one state (Stellar: Florida), say in the reply what that state would change ("if this is Florida, the deed's documentary stamp tax is 0.70%, not the 0.4% estimate"), from the script's output when it gives one.
- **Property tax rates outside the built-in counties:** use the current adopted rates from the county's property appraiser or appraisal district, or its tax office or tax collector, and cite it; never a tax-protest firm, a portal or a blog. Rates go in as mills (dollars per $1,000 of value): a rate per $100 of value, as Texas publishes them, times 10 (2.0464 is 20.464 mills). With no official source, the national estimate stands (the notes name it).
- **Commission:** without terms from the agent, reports use the default 5% in total (2.5% listing, 2.5% buyer's agent), with no label: a default, not an assumption. Ask for the listing agreement's terms in the reply.
- **Homestead outside Florida:** only Florida's homestead exemptions are built in. Elsewhere a buyer's taxes assume no exemption, and the payment note says so (payments may run high where the exemption is large, as in Texas). Never estimate another state's exemption: say in the reply that payments leave it out.

## Property Tax at Closing

Where property tax is paid in arrears (Florida, Texas and most states), every net sheet follows one rule, so two runs of the same home never differ by the tax bill:

- **The seller's share only.** The net charges this year's tax from January 1 to the day before closing, credited to the buyer. Never the whole year's bill.
- **After this year's bills go out** (Florida: November 1): assume the bill is still unpaid at closing, unless the agent says the seller paid it. The report's notes say so once (never the line's label), and so does your reply.
- **The seller already paid it** (the agent says so: `current_tax_bill_paid` true): the seller paid the whole year, so the net shows the buyer's credit back to the seller from closing to December 31.
- **Past the bill's due date** (the agent gives it, or the market's `property_tax.due_date`): a closing after it assumes the bill is paid, so the buyer credits the seller from closing to December 31, and the notes say the bill is assumed paid. Florida's bills are due the next March, so this never applies there.
- **No tax bill or no closing date:** the proration is left out, the net sheet says it isn't included (nothing else claims it's in the proration), and the sheet is Preliminary.

## After the First Report

End the reply with the few estimates that move the numbers most, in plain words, and what replaces each one:

> Estimated: transfer tax (0.4%), title and settlement fees ($1,200). Commission is at the default 5% total. Send a title quote or your listing agreement's terms and I'll update the report.

When the agent sends numbers, put them in the same data file's `costs` and render again. The fields each skill accepts are in its data reference.

Contract deadlines and time rules are the exception: they come from the contract, never from an estimate.
