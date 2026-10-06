# Real Estate Skills {{VERSION}}

Claude skills for real estate agents: buyer and seller CMAs, seller net sheets, offer strategy, offer reviews and contract timelines, all with your name, brokerage and brand colors.

The download holds four files:

- `{{PLUGIN_FILE}}`: the plugin you install in the Claude desktop app.
- `README.md`: this guide.
- `Real-Estate-Skills-Manual.pdf`: the manual, this guide with screenshots.
- `LICENSE`: the license.

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

1. Unzip the download.
2. Open the Claude desktop app and click **Customize** in the sidebar.
3. On the **Plugins** tab, click **Add**, then **Upload plugin**.

   <!-- figure: images/install-customize.png | Open Customize in the sidebar. -->
   <!-- figure: images/install-upload-plugin.png | On the Plugins tab, click Add, then Upload plugin. -->

4. Drag `{{PLUGIN_FILE}}` onto the upload area (or click **browse** and pick it), then click **Upload**.

   <!-- figure: images/install-pick-file.png | Pick the .plugin file inside the unzipped folder, not the .zip. -->
   <!-- figure: images/install-upload.png | The plugin file and its preview. Click Upload. -->

Upload the `.plugin` file itself, not the zip or the unzipped folder. The skills then appear as `real-estate:agent-profile`, `real-estate:buyer-cma` and so on. To use one, type **/** and its name in a chat (for example **/buyer-cma**) and select it from the list. Section 6 gives each skill's name.

<!-- figure: images/install-skills-tab.png | Once installed, the plugin's Skills tab lists every skill with its / name. -->

## 2. Set Up Your Profile (Once)

Do this first. It takes about two minutes and every report after it carries your name, brokerage, license, contact details and brand colors, and every client note sounds like you.

1. Start a new chat.
2. Type **/agent-profile** and select it from the list, then type **"Set me up."**
3. Answer two short rounds of questions. Skip anything you like. Have these handy:
   - Your name as it appears on documents and your brokerage's licensed name.
   - Team name, phone, email, website and license number (any or none).
   - Your logo, business card or website, for your brand colors (or say "pick for me").
   - Any disclaimer your brokerage requires.
   - How clients would describe the way you talk, or an email you've written.
4. You get two files:
   - **profile.md**: who you are. The other skills read it.
   - **project-instructions.md**: a short prompt for a Claude Project.
5. Claude's reply explains how to use profile.md. It works any of these ways:
   - in a **Project**'s files (the easiest: follow the steps Claude gives you, and every chat in that Project knows who you are),
   - in your Cowork working folder,
   - uploaded or pasted at the start of any chat.

To change something later, just say it: "My new number is 407-555-0100", "I moved to LPT Realty", "Use navy for my reports."

## 3. Set Up Your MLS Export (Once)

The CMA skills read a spreadsheet (CSV) of nearby listings and sales. Set up a custom export once and reuse it for every property.

1. In Matrix, click **Hello, [Your Name]** at the top right, then **Settings**, then **Custom Exports**.

   <!-- figure: images/export-hello-menu.png | Click Hello, [Your Name], then Settings. -->
   <!-- figure: images/export-settings.png | On the Settings page, open Custom Exports. -->

2. Click **Add Export** and name it **Basic CMA Export**.

   <!-- figure: images/export-manage.png | Manage Custom Exports: click Add Export. -->

3. For each field in the table below, type its name in the **Search** box under **Available Fields** (left), then click **Add** to move it to **Export Fields** (right). The order doesn't matter.

   <!-- figure: images/export-add-field.png | Search for the field (here, Heated Area), select it, then click Add. -->

4. At the bottom, set **Separator** to **Comma** and **Include Column Names** to **Name**.
5. Click **Save**.

   <!-- figure: images/export-finished.png | The finished export: named Basic CMA Export, fields added, Comma and Name selected, then Save (top right). -->

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

   <!-- figure: images/comps-quick.png | Search, then Residential, then Quick. -->

2. **Statuses:** check **Active**, **Pending**, **Sold**, **Expired** and **Canceled (WDN-U)**. Matrix fills in **0-180** days (the last 6 months) for each one except Active; leave it as is.
3. **Location:** in **Within [1] miles of [address]**, keep **1** and enter the property's address. You don't need to draw on the map.
   - In a rural area with few sales, widen to 2 or 3 miles.
   - In a dense area or a big subdivision, 0.5 mile is often enough.

   <!-- figure: images/comps-statuses.png | The five statuses checked (Matrix fills in 0-180), and Within 1 miles of the address. -->
   <!-- figure: images/comps-map.png | The Map tab shows the 1-mile radius Matrix draws for you. -->

4. **Property style:** select the styles that match the home (for example Single Family Residence, or Townhouse and Villa for a townhome, or Condominium for a condo). Single-family homes and townhouses can go together when they're similar in size and price.
5. Check the count. **It must be under 500.** If it's over, narrow it until it's under:
   - Shrink the radius (1 mile to 0.5 mile).
   - Add a heated square footage range, about 30% above and below the home.
   - Add a year built range or a minimum number of bedrooms.
   - Shorten the days to 0-90.

   <!-- figure: images/comps-style.png | Property Style selected; the match count shows at the bottom left (47 here). -->

6. Go to **Results** and click **All** next to "Checked".
7. Click **Export** in the action bar at the bottom, pick **Basic CMA Export**, and download the CSV.

   <!-- figure: images/comps-results.png | Every row checked (Checked 47); Export is in the action bar at the bottom. -->
   <!-- figure: images/comps-export.png | Choose Basic CMA Export and click Export. -->

Upload the file exactly as downloaded. Opening and saving it in Excel can change dates and numbers.

## 5. Download the Property Report

The property report is the home's full record in one PDF: the listing, public records, taxes, the full listing history across MLS numbers, flood data and photos. In Stellar it's the **360 Property View**.

**For a buyer** (a home for sale now):

1. Search for the active listing by MLS number or address and open it.
2. Check only this home. **Print** uses every checked listing, so if you came from search results, click **None** first, then check this one.

   <!-- figure: images/report-checked-all.png | Coming from search results, every listing is checked (Checked 47). Click None, then check this home. -->

3. Click **Print** and choose the **360 Property View** format.
4. Select **Print All Tabs**.
5. Click **Print to PDF** and save the file.

   <!-- figure: images/report-one-checked.png | Only this home checked (Checked 1). Print is in the action bar at the bottom. -->
   <!-- figure: images/report-print.png | 360 Property View with Print All Tabs checked, then Print to PDF. -->

**For a seller** (your listing appointment):

1. Go to **Search**, then **Public Record**. This opens **Tax Search**; search by the address.

   <!-- figure: images/seller-public-record.png | Search, then Public Record. -->
   <!-- figure: images/seller-tax-search.png | Tax Search: enter the street number, street name and zip under Location. -->

2. Click the result's **Folio/PID** link to open its **360 Property View**.
3. The **Last Listing** tab has the home's most recent MLS listing (usually from when the seller bought it), so you don't need to find it separately.

   <!-- figure: images/seller-folio.png | Click the Folio/PID link (owner name hidden here). -->
   <!-- figure: images/seller-last-listing.png | The Last Listing tab already has the home's most recent MLS listing. -->

4. Click **Print**, choose **360 Property View**, select **Print All Tabs**, then click **Print to PDF** and save the file.

   <!-- figure: images/seller-tax-only.png | By default only the Tax tab is checked, -->
   <!-- figure: images/seller-all-tabs.png | so check Print All Tabs before Print to PDF. -->

For a seller the report is usually years old, so Claude uses it for the facts that don't change (size, lot, taxes, history) and asks what the seller has updated since.

The report includes owner names, mortgage history and agent-only remarks. The skills use these for your own read and never put them in anything a client sees.

## 6. Using the Skills

Type **/** and the skill's name (shown next to each heading below), select it, then ask in plain words and attach the files. Claude asks for anything missing, and every question can be skipped: you'll get a report marked Preliminary instead of a stop.

**Same files, same numbers.** Every price, range, net and date comes from fixed rules, so the same files give the same numbers every time. Where a call takes judgment (how hard to push on price, how firm a counter should be), Claude picks one of a few named strategies from the listing and the market, tells you which and why, and the numbers follow from it. Say so to pick another ("my buyer can't lose this one", "hold firm on price"), or give your own numbers: the report shows them as yours.

**Keep a deal together.** A CMA and the offer work after it share numbers when they're in the same chat. In a new chat, upload the CMA PDF (or keep it in the deal's Project, section 7) and Claude reads the value range from it.

### Buyer CMA (/buyer-cma)

What a home is worth, how the asking price compares, your buyer's real monthly cost, and a suggested opening offer with a target and a walk-away.

The offer plan follows one of four approaches: **Leverage** (a home that has sat, had price cuts or a failed contract), **Standard**, **Competitive** (a new listing in a tight market) or **Must Win** (your buyer can't lose this house; only when you say so). Claude suggests one from the home's history and the market. A quick "is it priced right?" answer and the full report use the same rule, so with the same approach they give the same opening, target and walk-away.

- **Upload:** the 360 Property View PDF for the listing and the comps CSV.
- **Tell Claude:** the buyer's timeline, how they're financing (loan type, down payment) and how much they want this house (that sets the approach).
- **Example:** "Run a buyer CMA on 123 Oak St. My buyer is FHA with 3.5% down, their lease ends in March, and they love it."
- **You get:** a PDF report to send, or a short summary in chat.

### Buyer Offer Strategy (/buyer-offer-strategy)

The strongest offer inside your buyer's limits, up to two alternatives, and how it stacks up against other offers.

- **Best inputs:** a buyer CMA from the same chat; the buyer's max price, cash available, reserves they want to keep and max monthly payment; and what the listing agent told you (other offers, deadline, what the seller cares about).
- **Minimum:** the list price and the buyer's cash.
- **What matters most to your buyer:** winning the house, a balance, or keeping cash. Claude recommends the option that fits (balance unless you say otherwise).
- **Example:** "What should we offer? My buyer can go to $450,000, has $40,000 cash and wants to keep $10,000. The listing agent says there are two other offers and they want to close in 30 days."
- **You get:** an Offer Options report and an Offer Package Worksheet (the contract entries, the riders and addenda by name, and a checklist). The Offer Options report shows your buyer's limits and cash: it's for your buyer only, never the listing agent. Its strength scorecard rates each option as the listing agent will, from facts in the offer only (financing, approval, deposit, contingencies, timing, the property); a fact you haven't given shows as Not Scored rather than a guess.

### Seller CMA (/seller-cma)

A recommended list price, three pricing options with the seller's estimated net at each, a chart of every nearby sale and listing by size and price, and a launch plan.

The three options are always **Draw Offers** (the lower part of the supported range, to bring in competing offers), **Market Price** (the middle) and **Premium** (the upper part), each on a price buyers' search filters catch ($469,900, not $470,000). Claude recommends one from the market (supply, price cuts, how close sales come to asking) and says why. Ask for another, or give your own price. For your own listing that hasn't sold, the options are staying at the current price or a price cut.

- **Upload:** the 360 Property View PDF from the last sale and the comps CSV.
- **Tell Claude:** what the seller has updated since they bought (with years, roof first), known issues, their timeline, and their mortgage payoff if you have it.
- **Example:** "Seller CMA for 456 Pine Ave. They replaced the roof in 2023 and redid the kitchen in 2021. Payoff is about $210,000. They'd like to be moved by June."
- **You get:** a PDF report. Ask for a **listing presentation** too and you also get an editable PowerPoint with the same numbers, plus a PDF copy of the slides (a backup that opens anywhere). If you didn't ask, Claude offers it after the report.

### Seller Net Sheet (/seller-net-sheet)

What the seller walks away with at one price, or up to three side by side, without a CMA or an offer. Useful before a listing appointment, when a seller asks about a price cut, or to show what a seller credit costs.

- **Tell Claude:** the address with its city and county, the price or prices, and the mortgage payoff. The listing agreement's commission, the expected closing date and this year's tax bill sharpen it.
- **Minimum:** the address and one price. Without the payoff, the sheet stops at the net before the payoff and is marked Preliminary.
- **Example:** "What would my seller net at $450,000 and at $440,000 on 2250 Oak Hollow Ct in Oviedo? They owe about $214,000, my listing agreement is 3% plus 2.5% to the buyer's agent, and we expect to close in mid-December."
- **You get:** a one-page PDF with every cost itemized and the estimates named once in its notes, or a short table in chat. The default commission (2.5% listing, 2.5% buyer side) is used until you give yours. Send a payoff letter, a title quote or the tax bill and Claude redoes it.
- **Already have an offer?** Use Seller Offer Review: it nets the offer and also checks its terms.

### Seller Offer Review (/seller-offer-review)

Reviews the offers on your listing. It works two ways, depending on how many offers you upload.

**One offer:** the seller's net (as offered, and if the appraisal or inspection goes badly), how likely it is to close, the risks, and a counter.

- **Example:** "We got an offer on 456 Pine Ave. Should my seller accept, and what should we counter?"

**Two or more offers:** everything above for each offer, plus a side-by-side ranking and a plan: which offer to counter, which to hold as a backup and which to decline.

- **Example:** "We got three offers on 456 Pine Ave. Which is best and what should we do with each?"
- A single offer turns into a comparison when another one arrives: upload it in the same chat.

**For both:**

- **Upload:** each offer (the contract with every rider, addendum and counteroffer), plus pre-approval letters or proof of funds.
- **Best inputs:** a seller CMA from the same chat, the seller's payoff, and what matters most to them (price, speed, certainty).
- **How firm the counter is:** **Firm** (hold the price at list or your seller's last counter), **Meet Partway** or **Terms Only** (accept the price, counter the terms). Claude suggests one from the offers in hand and your seller's priority (never Firm for a seller who wants certainty or speed). Say so to change it, or name a term to counter yourself.
- **How likely it is to close:** a score from facts in the offer only (financing, approval, deposit, contingencies, appraisal risk, timing, the property). A fact the offer doesn't show is marked Not Scored, never guessed.
- **Minimum:** list price, and each offer's price and financing type.
- **You get:** a seller-ready PDF for each offer, plus a side-by-side comparison PDF when there are two or more, with a short answer in chat. When a new offer arrives, every offer's PDF is redone so they all agree. Say "just in chat" if you don't want the PDFs.

**Counters, deadlines and incomplete offers:**

- **When it was delivered.** An offer's time for acceptance usually runs from delivery, not from when the buyer signed. If the package doesn't show when it reached you, tell Claude the date and time; until then a deadline that has likely passed is raised as a question.
- **Counters back and forth.** When the buyer counters, upload it in the same chat. The review updates the terms, keeps the next counter in line with your seller's last one (never a higher price than your seller already asked), and points out anything the buyer's counter dropped.
- **Expired offers.** When the time for acceptance has passed, the review says so, shows the numbers as written, and shows what a counter with a new time for acceptance could look like, for reference.
- **Unsigned or incomplete offers.** An offer that isn't signed, is missing pages or has no price is marked **Contract Incomplete**: you see every warning and what to fix, but no accept, counter or decline, and it isn't ranked.
- **Pre-approval and proof of funds.** Claude checks the pre-approval amount and expiration against the offer, and the proof of funds against the cash the offer needs.

### Contract Timeline (/contract-timeline)

Every deadline in an executed contract: who owes what, by when, and what happens if it's missed.

- **Upload:** the fully executed contract with every rider, addendum and counteroffer.
- **Tell Claude:** whether you represent the buyer or the seller.
- **Example:** "Here's the executed contract for 789 Elm St. I'm the buyer's agent. Give me the timeline."
- **You get:** a PDF timeline and a calendar file you or your client can add to any calendar app. Quick questions work too: "When does the inspection period end?"
- When an amendment or extension is signed, upload it and ask to re-run the dates. Moved dates show what they were before.
- **The Effective Date** is when the last party signed and delivered the final acceptance or counter. If the package shows signatures but not delivery, Claude uses the last signature and asks you to confirm it: every deadline counts from it.
- **Not signed by everyone yet?** Claude says what's missing and lists the terms, and builds the timeline once it's signed. For a what-if, tell Claude the expected Effective Date.
- **Already done:** upload the escrow deposit receipt, or tell Claude what's been completed. Done items show as done and drop out of the calendar reminders.
- **Short sales:** most dates count from the lender's approval. Until you tell Claude the approval date they show as "days after short sale approval"; the report and calendar still work, and you re-run it once the approval comes in.

### Contracts and Forms

- **Fully supported:** the Florida Realtors/Florida Bar contracts (AS IS and Standard), every CR-7 rider (A to GG) and the Florida Realtors addenda and disclosures. Claude knows each form's deadlines, the defaults for blanks and what each rider changes, and checks that every rider marked on the contract is attached.
- **Every other contract** (another state's form, a builder or bank contract, an attorney-drafted agreement, the Florida Realtors CRSP) works on a best-effort basis: Claude reads the dates, time rules and terms from the contract itself, never borrows Florida's defaults, and asks when the contract doesn't say. Costs use labeled national estimates until you give local numbers.
- **What to confirm:** with any other contract, and with a Florida form on a newer revision than the one checked, Claude says so once in chat and lists what to confirm (how days are counted, deadlines, defaults it used). That note stays in the chat: it never appears in a PDF, calendar file or worksheet your client sees.
- **Blanks and defaults:** when a blank is filled from the form's default, or left for you to decide, Claude lists it in chat so you can confirm it with the other agent.

### How They Fit Together

- **Buyer side:** Buyer CMA, then Buyer Offer Strategy, then Contract Timeline once the contract is executed.
- **Seller side:** Seller CMA (or a quick Seller Net Sheet before the appointment), then Seller Offer Review when offers arrive, then Contract Timeline.

## 7. Best Practices

### Keep Each Transaction in Its Own Project

A Project can hold a whole deal. Every chat in it starts with the files already there, so you don't upload the same documents again.

1. Create a Project for the transaction, named for the property and side (for example "123 Oak St, Buyer").
2. Add your **profile.md** and paste **project-instructions.md** into its instructions, as in section 2.
3. Add the deal's files as they come in:
   - The property report (360 Property View PDF) and the comps CSV.
   - The **CMA PDF** once it's made. Later chats read the value range from it, so the offer work starts from the same numbers.
   - Offers, counters, pre-approval letters and proof of funds.
   - The executed contract with every rider, addendum and counteroffer, then each amendment or extension.
   - Any report you've sent the client (offer options, offer review, timeline), so the next chat knows what was already recommended.
4. Ask in a new chat inside the Project whenever the deal moves: "We got a counter, what now?" or "The inspection extension is signed, update the timeline."

In Cowork, put the files in the project's folder. Keep your main "Real Estate" Project for everything else.

### What Gets Saved Where

- **Your profile:** in Cowork with a working folder selected, Claude saves profile.md in that folder and finds it in every later session. Anywhere else you get the file to keep: add it to your Project files.
- **Reports:** the PDFs, the PowerPoint and the calendar file are the files you get. Download the ones you want to keep, or add them to the deal's Project.
- **Deal details:** Claude keeps the details it read from a contract or an offer only for that chat. In a new chat, upload the documents again (the executed contract and every amendment, or the offers and counters), or keep them in the deal's Project so they're already there.

### Name Files So They're Easy to Find

Start with the address, then what it is and the date: "123 Oak St, Buyer CMA, 2026-09-25.pdf", "123 Oak St, Offer B, Smith.pdf". When a newer version replaces a file, remove the old one from the Project so it isn't read by mistake.

### Keep the Numbers Current

- **Comps go stale.** Pull a fresh export when the last one is more than two or three weeks old, and always before an offer or a price change.
- **Download a fresh property report** when the listing's price or status has changed.
- **Give your own costs** when you have them. Closing costs and taxes are estimated from the property's location, and each report names its estimates once, in its notes. Commission uses the default 2.5% listing and 2.5% buyer side until you give your terms; your own agreements are confirmed with you in chat, never questioned in a client's report. Say your numbers in the request: "Title quote is $2,150", "Listing side is 3%, buyer side 2.5%." Florida's costs are built in; other states use national estimates until you give local numbers.
- **Keep your profile current.** Say "My new number is..." and replace profile.md in your Projects.

### Review Before You Send

The reports are a strong first draft, and you know the home. Check condition calls, the tax district and anything marked for review before a client sees it. Confirm every date and default Claude lists in chat, especially on a contract that isn't a Florida Realtors/Florida Bar form. Ask for changes in the same chat.

### Share Only What the Deal Needs

- **Fair housing.** Reports describe the property, the numbers and the terms, never people. If you ask for wording that could read as steering (for example about schools, safety or who a home suits), Claude writes a compliant version and says why.
- **Leave out buyer letters and personal details.** Offer reviews don't use them, and they can raise fair housing issues.
- **Agent-only information stays with you.** Owner names, mortgage history and private remarks from the property report shape Claude's advice to you but never appear in client reports. Account and loan numbers from pre-approval letters and bank statements are never copied into a report.

## 8. Other MLS Systems

Everything above works with other MLS systems. The names of the menus change, not the steps:

- **The export:** make a saved or custom export with the columns in section 3 (or as many as your MLS has). Claude matches the columns by name. When it doesn't recognize some, it matches them to what it needs and tells you.
- **The comps search:** the same statuses (active, pending, sold, expired, canceled), the last 6 months, about a 1 mile radius, the matching property types, and under your MLS's export limit.
- **The property report:** the fullest single report your MLS prints for a property: listing details, tax and public records, and the full listing history. If there isn't one, a listing sheet plus a screenshot of the history and the tax record works too.

## 9. Updating

Upload the new `.plugin` file the same way. If the app keeps the old version, remove the plugin first and upload the new one. Your profile and Project stay as they are.

Source, documentation and license: https://github.com/axelrivera/real-estate-skills
