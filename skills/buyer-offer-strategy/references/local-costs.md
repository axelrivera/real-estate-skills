# Local Costs

Where a report's local numbers come from, and how the agent improves them. Convention over questions: build the report first with good defaults, label what's estimated, and let the agent correct it afterward.

## Where Each Number Comes From

The scripts take the location from the property (state and county from the listing or the address) and use the first of:

1. **This deal's own numbers:** what the agent put in the first message or sent after the first report (a title quote, the listing agreement's commission, the tax bill), and what you looked up (the state's transfer tax). They go in the data file's `costs` block.
2. **Built-in local values:** Florida state rates and county customs, Stellar MLS formats.
3. **National estimates,** labeled "Estimate" on the report: transfer tax 0.4%, owner's title 0.5% of price, title and settlement fees $1,200, a buyer's closing costs 3%, property tax 1.1% of price when there's no bill, insurance and utilities for holding costs.

Never use Florida's numbers for another state.

## Before the First Report

- **Don't ask about costs up front.** Build the report with what's there.
- **Read the listing first:** the tax bill, HOA dues, county, property type and flood zone are usually on the MLS sheet.
- **Transfer tax outside Florida:** search for the state's deed transfer tax. Use a rate only from a trusted source (the state's revenue department, the statute, or the county recorder or clerk) and cite it in your reply. Put it in `costs` as `transfer_tax_rate` (0 where there is none, as in Texas), with `transfer_tax_payer` when the buyer pays or it's split, and `transfer_tax_label` for its local name in Title Case. When the sources disagree, the tax is layered or tiered, or no trusted source turns up, leave it out and let the national estimate stand, labeled.
- **Commission:** without terms from the agent, reports assume 5% in total (2.5% listing, 2.5% buyer's agent), labeled "Assumed".

## After the First Report

End the reply with the few estimates that move the numbers most, in plain words, and what replaces each one:

> Estimated: transfer tax (0.4%), title and settlement fees ($1,200), commission (5% total). Send a title quote or your listing agreement's terms and I'll update the report.

When the agent sends numbers, put them in the same data file's `costs` and render again. The fields each skill accepts are in its data reference.

Contract deadlines and time rules are the exception: they come from the contract, never from an estimate.
