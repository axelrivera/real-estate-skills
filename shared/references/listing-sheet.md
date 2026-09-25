# Reading the Subject's Property Report

The usual subject input is the MLS property report PDF. In Stellar it's the **Cross Property 360 Property View**: the listing, public records, full history, maps and flood data in one file. It replaces the separate listing sheet, history screenshot and tax bill. It's the preferred input, not the only one. A plain listing sheet, screenshots, a public-records printout or typed facts all work; read what's there and ask only for what's missing.

## Contents

- Reading the file · What's in it · Photos · Cross-checks · What stays with the agent · Buyer side · Seller side · Other inputs

## Reading the File

Read the text, not the page images, so every number is copied exactly: `pdftotext -layout report.pdf -` (fall back to reading the PDF directly if the command isn't there). The text has no photos: look at the photo pages separately (see Photos).

## What's in It

| Section | Use it for |
|---|---|
| Listing header (status, list price, DOM, CDOM, beds, baths, heated area, pool, garage, fees, flood zone) | `subject` facts, `list_price`, `sqft`; the status line tells you whether the home is on the market now |
| Public remarks | Condition and updates *as the listing claims them* (a claim, not a fact: "new HVAC 2025" needs a permit or invoice) |
| Land, Site and Tax (legal, zoning, tax ID, taxes, homestead, CDD, flood zone and panel, lot size) | Lot, CDD, flood zone; the MLS's tax figure is a starting point only (see Cross-checks) |
| Interior, Exterior, Community (rooms, construction, roof type, pool features, HOA fee and schedule, in-law suite) | Facts and watch items. Annual HOA = `Total Annual Assoc Fees`; the HOA fee field is per payment period (quarterly here) |
| Realtor Information (list agent and office, original price, occupancy, financing accepted, As-Is, private remarks) | Negotiation context for the agent, never quoted in client files (see below) |
| Tax tab: Location Information | Subdivision (`subject.subdivision`, and stats.py's `--subdivision` when the home has no export row), `Tax Area` code (picks the millage district), census data (ignore) |
| Tax tab: Tax Information, Assessment and Taxes | The current bill: the latest year's `Total Tax` and its year (`current_bill`, `current_year`); exemptions (homestead); just and assessed value by year |
| Tax tab: Characteristics, Building Features | The county's record of beds, baths, heated and total area, year built and effective year, construction, lot size, pool and patio years |
| Estimated Value (RealAVM) | Never a comp and never an input to the range. At most a one-line cross-check in the chat reply, with its confidence score |
| History: Listing History from MLS | Every listing across MLS numbers (see below) |
| History: Sale History from Public Records, Mortgage History | Past sale prices and dates; recorded loans (agent context only) |
| Flood Map | Zone, panel date, and whether a higher-risk zone is nearby (a lake's AE zone next to an X lot is worth a line) |
| Foreclosure | A filing is a distress fact for the agent; an empty section means none was found |

### The History Grid

One block per MLS number, newest listing first and newest change first within each: read bottom to top, block by block. Each row is `Eff Date · Change Type · Change Info · Current Price · DOM`:

- **Change Info** is either a status move (`->ACT` new listing, `ACT->PND` under contract, `PND->SLD` closed, `ACT->TOM` held off market, `TOM->ACT` back on, `ACT->CAN`, `ACT->EXP`, `ACT->WDN`) or a price move (`895000.00->839000`: a cut when the second number is lower). A blank Change Type with a price move is a price change.
- **DOM** is that listing's days on market at the change; it restarts with each MLS number. Total active days = each earlier listing's last DOM plus the current listing's ADOM from the header. The header's CDOM resets after a long enough gap off the market, so it can undercount: add it up yourself.
- The block's status line gives the outcome: Sold, Active, Pending, Expired, `Canceled (WDN-U)` and so on.
- `PND` followed by anything other than `SLD` is a failed contract. A closing far below the list price (`$550,000` listed, `$325,000` sold) usually means condition, an off-market or investor sale, or a distressed seller: match it to the public-record sale and the next sale's price, and name what the data shows, not a guess.

The public-record sale history fills in sales the MLS didn't carry (older or off-market ones). Check each MLS closing against it: the recorded price is the one that counts.

## Photos

The photo pages are the only look at the home's condition besides the remarks, and condition drives the biggest comp adjustment (renovated, partially updated, dated). Look at them once, at a low resolution: when the PDF's pages aren't already visible, render just those pages (`pdftoppm -r 60 -png -f <first> -l <last> report.pdf photos`, if the command is there).

- **Useful for:** the condition tier (kitchen cabinets and counters, baths, flooring, paint); whether a remarks claim shows (a "renovated kitchen" that looks original is a watch item); spaces the text only mentions (a kitchenette or separate entrance behind an in-law suite claim, a garage conversion); the outside (roof wear, pool surface and screen enclosure, fencing, drainage, neighbors' uses visible in aerials).
- **Not useful for:** anything with a date or a number (a roof's age, an AC's year, square footage) or anything hidden (permits, systems, what's behind the walls). Listing photos are staged, wide-angle and edited: they show the best case.
- **Say where it came from:** "from the listing photos" in the condition judgment and the method note, and treat it as a judgment, like condition read from remarks.
- **Describe the property, never people or belongings** that hint at who lives there (religious items, flags, photos of occupants, accessibility equipment, children's rooms as such). A room is a bedroom, not a nursery.
- **Never copy the photos into a report or deck.** They belong to the listing broker or photographer. The report describes; the agent can send the listing link.
- **Old photos** (a report from the last sale) show the home then, not now: use them to ask the seller what changed ("the 2022 photos show the original kitchen; has it been updated?"), never as today's condition.

## Cross-Checks

The report puts the MLS side (what the listing agent typed) next to the county side (the appraiser's record). When they disagree, use the county figure for the facts the county measures, say which you used, and turn the gap into a watch item or a question:

- **Heated area and lot:** public-record sq ft is the default `sqft` (the MLS usually cites it as `Heated Area Source`). A different MLS lot size is common (0.55 vs 0.462 acre); give the county's and note the other.
- **Bedrooms and bonus space:** an in-law suite, a converted garage or "5 bedrooms in total" in the remarks, when the county records 4, is unpermitted or non-conforming space until a permit shows otherwise. Value it as the county records it; the extra space is a question, not a bedroom.
- **Homestead:** the MLS's Homestead field is often wrong. Use the Tax Information `Exemptions` and `Tax Exempt Amount`.
- **Construction, roof, year built:** a later `Effective Year Built` means updates the county recognized; it doesn't date the roof or systems.
- **Remarks vs. records:** a claimed update the building features, permits or photos don't back up is a watch item.

## What Stays with the Agent

The report is built from MLS data, and some of it isn't for consumers. These can shape the agent's questions and the chat reply, but never appear in a client-facing file (report, deck, markdown summary meant to forward):

- Owner names, mailing address, owner phone; buyer and seller names in the sale history. Say "an individual", "an LLC", "a trust" or "an investor" when the owner type matters.
- Mortgage history (lenders, amounts, dates). In chat it can hint at the seller's room to negotiate or, on the seller side, remind the agent to get a payoff statement. Never estimate a payoff from it.
- Realtor Remarks, Confidential Info, showing instructions, lockbox, the listing agent's contact details and private notes.
- The AVM figure.

Past sale prices and dates, list prices, price changes and days on market are fine to show: they're the history the report explains.

## Buyer Side

The report should be current: the status line Active (or Pending, for a backup offer) at the list price the agent is looking at. It covers the listing sheet and the full history, so don't ask for a history screenshot. If it's more than a few days old, ask whether the price or status has changed since.

For taxes: `current_bill` and `current_year` come from the latest Total Tax; `Tax Area` goes in the jurisdiction's `district` (compute.py matches the appraiser's code), which settles city vs. unincorporated even when the mailing city says otherwise. Some counties reuse a code across districts (Orange): compute.py then warns instead of guessing, so name the district. A current bill carrying the owner's homestead exemption says nothing about the buyer's bill, which resets at the purchase price.

## Seller Side

For a listing appointment the report is often from the **last sale** (the seller's purchase) or an old listing, not today. Use it for what doesn't change: the county's characteristics, lot, legal, flood zone, tax bill, and the full listing history. Never treat old remarks, photos or condition as today's home. Ask the seller what changed since that date (updates with dates and permits, repairs, anything added or removed) and skip the intake questions the report already answers (beds, baths, sq ft, lot, year built, construction, pool, garage, HOA, taxes, flood zone).

If the report shows the home **listed right now** (Active or Pending), follow the skill's rule for a current listing: say so first and ask whose listing it is before going further. Expired, withdrawn and canceled listings in the history are the most important pricing fact: say at what price they failed and for how long.

## Other Inputs

- **Another MLS's property report or listing sheet:** the same sections under other names; read its history grid by its own legend.
- **Screenshots** of the listing or history: read them the same way; ask for anything cut off.
- **Only an address or typed facts:** work from what you have, ask for the rest in one message (the skill's intake list), and note in the method which facts came from the agent or seller.
