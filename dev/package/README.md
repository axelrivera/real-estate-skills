# Real Estate Skills {{VERSION}}

Claude skills for real estate agents: buyer and seller CMAs, offer strategy, offer reviews and contract timelines, all with your name, brokerage and brand colors.

This folder holds two files:

- `{{PLUGIN_FILE}}`: the plugin you install in the Claude desktop app.
- `README.md`: this guide.

## Contents

1. Install the Plugin
2. Set Up Your Profile (Once)
3. Set Up Your MLS Export (Once)
4. Pull the Comps for a Property
5. Download the Property Report
6. Using the Skills
7. Best Practices
8. Other MLS Systems
9. Updating

The MLS steps use **Stellar MLS (Matrix)** as the example. Other MLS systems work the same way: see section 8.

## 1. Install the Plugin

1. Unzip this archive.
2. Open the Claude desktop app and go to the plugin settings.
3. Choose **Upload local plugin**.
4. Drag `{{PLUGIN_FILE}}` onto the upload area (or click **browse** and pick it), then click **Upload**.

Upload the `.plugin` file itself, not this zip or the unzipped folder. The skills then appear as `real-estate:agent-profile`, `real-estate:buyer-cma` and so on. You don't need to type those names: ask in plain words ("run a CMA on this listing") and Claude picks the right skill.

**Install from GitHub instead (Cowork):** add the marketplace `axelrivera/real-estate-skills`, then install the `real-estate` plugin. Updates then come from GitHub.

## 2. Set Up Your Profile (Once)

Do this first. It takes about two minutes and every report after it carries your name, brokerage, license, contact details and brand colors, and every client note sounds like you.

1. In Cowork, select a working folder for your real estate work (for example a folder named "Real Estate"). Your profile is saved there, so every session finds it.
2. Type: **"Set me up."**
3. Answer two short rounds of questions. Skip anything you like. Have these handy:
   - Your name as it appears on documents and your brokerage's licensed name.
   - Team name, phone, email, website and license number (any or none).
   - Your logo, business card or website, for your brand colors (or say "pick for me").
   - Any disclaimer your brokerage requires.
   - How clients would describe the way you talk, or an email you've written.
4. You get two files:
   - **profile.md**: who you are. The other skills read it.
   - **project-instructions.md**: a short prompt for a Claude Project.
5. Follow the steps Claude gives you to create a **Project** with both files. From then on, start your real estate work inside that Project and Claude knows who you are without being asked.

To change something later, just say it: "My new number is 407-555-0100", "I moved to LPT Realty", "Use navy for my reports."

## 3. Set Up Your MLS Export (Once)

The CMA skills read a spreadsheet (CSV) of nearby listings and sales. Set up a custom export once and reuse it for every property.

1. In Matrix, go to **My Matrix**, then **Settings**, then **Custom Exports**.
2. Click **Add Export** and name it **Basic CMA Export**.
3. In **Available Fields** (left), find each field in the table below and click **Add** to move it to **Export Fields** (right). The order doesn't matter.
4. At the bottom, set **Separator** to **Comma** and **Include Column Names** to **Name**.
5. Click **Save**.

### Recommended Columns

Add these fields, shown here as Matrix labels them. Only the five marked **Required** are needed; the rest sharpen the comp ranking, the adjustments and the market read.

| Field | Used For |
|---|---|
| MLS Number | Telling listings apart |
| Address | **Required.** Matching the home and removing duplicates |
| Unit Number | Condos and townhomes |
| Zip | Location |
| Legal Subdivision Name | Same-neighborhood comps |
| Status | **Required.** Sold, active, pending, expired, canceled |
| Latitude | Distance from the home |
| Longitude | Distance from the home |
| Original List Price | Price cuts and list-to-sale ratios |
| List Price | **Required.** Active and pending prices |
| Close Price | **Required.** Sold prices |
| Contract Date | How fast homes go under contract |
| Close Date | How recent a sale is |
| CDOM | Days on market across relists |
| Sold Terms | Cash vs. loan sales |
| Sold Remarks | What happened at the sale |
| Seller Paid Buyer Costs | Seller credits in past sales |
| Special Sale Provision(s) | Short sales, foreclosures, estate sales |
| New Construction YN | Builder sales |
| Property Style | Single family, townhouse, condo |
| Heated Area | **Required.** Size and price per square foot |
| Beds | Bedroom adjustments |
| Full Baths | Bathroom adjustments |
| Half Baths | Bathroom adjustments |
| Floors in Unit/Home | One vs. two story |
| Floor Number | Condo floor |
| Year Built | Age |
| Exterior Construction | Block vs. frame |
| Garage Spaces | Garage adjustments |
| Pool Private Y/N | Pool adjustments |
| Furnishings | Furnished sales |
| Lot Size Acres | Lot adjustments |
| Water Frontage Y/N | Waterfront premium |
| Water Frontage | Type of waterfront |
| Water Access | Water access |
| Water View Y/N | Water views |
| Water View | Type of water view |
| Sewer | Septic vs. public sewer |
| Water | Well vs. public water |
| Flood Zone Code | Flood risk and insurance |
| Housing for Older Persons Y/N | 55+ communities |
| Land Lease Y/N | Land lease homes |
| Total Annual Association Fees | HOA costs (the yearly total) |
| HOA Fee | Reference (the yearly total above is what's used) |
| Public Remarks | Condition and updates |

## 4. Pull the Comps for a Property

Do this for each CMA. It takes a few minutes.

1. Go to **Search**, then **Residential**, then **Quick**.
2. **Statuses:** check **Active**, **Pending**, **Sold**, **Expired** and **Canceled**. For Sold, Expired and Canceled, enter **0-180** days (the last 6 months).
3. **Location:** use the map search to search within **1 mile** of the property's address.
   - In a rural area with few sales, widen to 2 or 3 miles.
   - In a dense area or a big subdivision, 0.5 mile is often enough.
4. **Property style:** select the styles that match the home (for example Single Family Residence, or Townhouse and Villa for a townhome, or Condominium for a condo). Single-family homes and townhouses can go together when they're similar in size and price.
5. Check the count. **It must be under 500.** If it's over, narrow it until it's under:
   - Shrink the radius (1 mile to 0.5 mile).
   - Add a heated square footage range, about 30% above and below the home.
   - Add a year built range or a minimum number of bedrooms.
   - Shorten the days to 0-90.
6. Go to **Results** and click **Select All**.
7. Click **Export**, pick **Basic CMA Export**, and download the CSV.

Upload the file exactly as downloaded. Opening and saving it in Excel can change dates and numbers.

## 5. Download the Property Report

The property report is the home's full record in one PDF: the listing, public records, taxes, the full listing history across MLS numbers, flood data and photos. In Stellar it's the **360 Property View**.

**For a buyer** (a home for sale now):

1. Search for the active listing by MLS number or address and open it.
2. Click **Print** and choose the **360 Property View** format.
3. Select **Print All Tabs**.
4. Save as PDF.

**For a seller** (your listing appointment):

1. Go to **Search**, then **Public Record**, and search by the address.
2. Open the home's most recent MLS listing (usually from when the seller bought it).
3. Click **Print**, choose **360 Property View**, and select **Print All Tabs**.
4. Save as PDF.

For a seller the report is usually years old, so Claude uses it for the facts that don't change (size, lot, taxes, history) and asks what the seller has updated since.

The report includes owner names, mortgage history and agent-only remarks. The skills use these for your own read and never put them in anything a client sees.

## 6. Using the Skills

Ask in plain words and attach the files. Claude asks for anything missing, and every question can be skipped: you'll get a report marked Preliminary instead of a stop.

**Keep a deal together.** A CMA and the offer work after it share numbers when they're in the same chat. In a new chat, upload the CMA PDF (or keep it in the deal's Project, section 7) and Claude reads the value range from it.

### Buyer CMA

What a home is worth, how the asking price compares, your buyer's real monthly cost, and a suggested opening offer with a target and a walk-away.

- **Upload:** the 360 Property View PDF for the listing and the comps CSV.
- **Tell Claude:** the buyer's timeline, how they're financing (loan type, down payment) and how much they want this house.
- **Example:** "Run a buyer CMA on 123 Oak St. My buyer is FHA with 3.5% down, their lease ends in March, and they love it."
- **You get:** a PDF report to send, or a short summary in chat.

### Buyer Offer Strategy

The strongest offer inside your buyer's limits, up to two alternatives, and how it stacks up against other offers.

- **Best inputs:** a buyer CMA from the same chat; the buyer's max price, cash available, reserves they want to keep and max monthly payment; and what the listing agent told you (other offers, deadline, what the seller cares about).
- **Minimum:** the list price and the buyer's cash.
- **Example:** "What should we offer? My buyer can go to $450,000, has $40,000 cash and wants to keep $10,000. The listing agent says there are two other offers and they want to close in 30 days."
- **You get:** an Offer Options report and an Offer Package Worksheet (the contract entries, riders and a checklist).

### Seller CMA

A recommended list price, three pricing strategies with the seller's estimated net at each, and a launch plan.

- **Upload:** the 360 Property View PDF from the last sale and the comps CSV.
- **Tell Claude:** what the seller has updated since they bought (with years, roof first), known issues, their timeline, and their mortgage payoff if you have it.
- **Example:** "Seller CMA for 456 Pine Ave. They replaced the roof in 2023 and redid the kitchen in 2021. Payoff is about $210,000. They'd like to be moved by June."
- **You get:** a PDF report. Ask for a **listing presentation** too and you also get an editable PowerPoint with the same numbers.

### Seller Offer Review

Each offer's net to the seller, how likely it is to close, the risks, and a counter. With several offers, a ranking and a plan.

- **Upload:** each offer (the contract with its addenda), plus pre-approval letters or proof of funds.
- **Best inputs:** a seller CMA from the same chat, the seller's payoff, and what matters most to them (price, speed, certainty).
- **Minimum:** list price, offer price and financing type.
- **Example:** "We got two offers on 456 Pine Ave. Which is better and what should we counter?"
- **You get:** a seller-ready PDF, or the review in chat. When another offer comes in, upload it in the same chat to add it to the comparison.

### Contract Timeline

Every deadline in an executed contract: who owes what, by when, and what happens if it's missed.

- **Upload:** the fully executed contract with every rider, addendum and counteroffer.
- **Tell Claude:** whether you represent the buyer or the seller.
- **Example:** "Here's the executed contract for 789 Elm St. I'm the buyer's agent. Give me the timeline."
- **You get:** a PDF timeline and a calendar file you or your client can add to any calendar app. Quick questions work too: "When does the inspection period end?"
- When an amendment or extension is signed, upload it and ask to re-run the dates.

### How They Fit Together

- **Buyer side:** Buyer CMA, then Buyer Offer Strategy, then Contract Timeline once the contract is executed.
- **Seller side:** Seller CMA, then Seller Offer Review when offers arrive, then Contract Timeline.

## 7. Best Practices

### Keep Each Transaction in Its Own Project

A Project can hold a whole deal. Every chat in it starts with the files already there, so you don't upload the same documents again.

1. Create a Project for the transaction, named for the property and side (for example "123 Oak St, Buyer").
2. Add your **profile.md** and paste **project-instructions.md** into its instructions, as in section 2.
3. Add the deal's files as they come in:
   - The property report (360 Property View PDF) and the comps CSV.
   - The **CMA PDF** once it's made. Later chats read the value range from it, so the offer work starts from the same numbers.
   - Offers, pre-approval letters and proof of funds.
   - The executed contract with every rider, addendum and counteroffer, then each amendment or extension.
   - Any report you've sent the client (offer options, offer review, timeline), so the next chat knows what was already recommended.
4. Ask in a new chat inside the Project whenever the deal moves: "We got a counter, what now?" or "The inspection extension is signed, update the timeline."

In Cowork, put the files in the project's folder. Keep your main "Real Estate" Project for everything else.

### Name Files So They're Easy to Find

Start with the address, then what it is and the date: "123 Oak St, Buyer CMA, 2026-09-25.pdf", "123 Oak St, Offer B, Smith.pdf". When a newer version replaces a file, remove the old one from the Project so it isn't read by mistake.

### Keep the Numbers Current

- **Comps go stale.** Pull a fresh export when the last one is more than two or three weeks old, and always before an offer or a price change.
- **Download a fresh property report** when the listing's price or status has changed.
- **Give your own costs** when you have them. Closing costs, taxes and commission are estimated from the property's location and labeled "Estimate" or "Assumed". Say your numbers in the request: "Title quote is $2,150", "Listing side is 3%, buyer side 2.5%." Florida's costs are built in; other states use national estimates until you give local numbers.
- **Keep your profile current.** Say "My new number is..." and replace profile.md in your Projects.

### Review Before You Send

The reports are a strong first draft, and you know the home. Check condition calls, the tax district and anything marked for review before a client sees it. Ask for changes in the same chat.

### Share Only What the Deal Needs

- **Fair housing.** Reports describe the property, the numbers and the terms, never people. If you ask for wording that could read as steering (for example about schools, safety or who a home suits), Claude writes a compliant version and says why.
- **Leave out buyer letters and personal details.** Offer reviews don't use them, and they can raise fair housing issues.
- **Agent-only information stays with you.** Owner names, mortgage history and private remarks from the property report shape Claude's advice to you but never appear in client reports.

## 8. Other MLS Systems

Everything above works with other MLS systems. The names of the menus change, not the steps:

- **The export:** make a saved or custom export with the columns in section 3 (or as many as your MLS has). Claude matches the columns by name. When it doesn't recognize some, it matches them to what it needs and tells you.
- **The comps search:** the same statuses (active, pending, sold, expired, canceled), the last 6 months, about a 1 mile radius, the matching property types, and under your MLS's export limit.
- **The property report:** the fullest single report your MLS prints for a property: listing details, tax and public records, and the full listing history. If there isn't one, a listing sheet plus a screenshot of the history and the tax record works too.

## 9. Updating

Upload the new `.plugin` file the same way. If the app keeps the old version, remove the plugin first and upload the new one. Your profile and Project stay as they are.

Source, documentation and license: https://github.com/axelrivera/real-estate-skills
