---
name: market-profile
description: Creates or updates a real estate market profile, a markdown file the other real estate skills read for local closing costs, transfer taxes, who pays title, commission defaults, property tax rules and millage, contract deadline rules, CMA adjustments and MLS export formats. Florida and Stellar MLS are built in; any other state or MLS is set up from what the agent provides. Use it whenever the agent says "set up my market", "I work in Texas / Puerto Rico / Miami-Dade", "my title company charges…", "our listing and buyer-side fees are…", "use these closing costs", uploads a net sheet or closing cost worksheet to save, or a skill reports missing local costs or rules.
---

# Market Profile

Writes a market profile: the local numbers and rules behind net sheets, CMAs, offers and contract timelines. It stores only the agent's own values. Everything else comes from the built-in layers, which keeps profiles short and lets updates to the built-in data reach the agent.

The agent is usually not technical. Talk in money and plain words ("title settlement fee $850"), never field names or YAML.

## Guardrails

These apply to everything this skill writes: files, chat replies, and text the agent may forward to a client.

- **Fair housing.** A market profile holds costs and rules, never descriptions of an area's people, safety or schools. When the agent names a state or local protected class beyond the federal list, save it to `fair_housing.extra_protected_classes` so every skill applies it. If the agent asks for wording that breaks this, write the compliant version and say why in one sentence; don't lecture or flag innocent wording like "family room".
- **No em dashes in prose,** chat included: use a comma, colon, parentheses or a new sentence. A lone em dash for an empty value (a table cell with nothing in it) is fine.
- **Labels in Title Case:** headings, column headers, row names, tiles, legend entries, card and slide titles. Sentences, notes and table values stay sentence case.

## 1. Find an Existing Profile

Look in the conversation, Project files and uploads for files that start with `profile: market`. An agent can have one per market, so match on state and area. If there's a match, this is an update: change only what the agent asks.

## 2. Where Do They Work?

Skip this for an update: the existing profile already says.

Ask for the state, the county or area, and the MLS if they know it. Then see what's already known:

```
python3 scripts/check_market.py --state <state> --county <county> [--mls <mls>]
```

For each group of settings it shows the values, where they come from (`state` or `mls` = built in, `county` = a county exception), and what's `missing`. `notes` explains any assumption (for example which MLS was assumed) and should be passed on.

## 3. Fill the Gaps, or Confirm the Built-Ins

- **The agent named the values** ("3% listing, 2% to buyer agents"): save exactly those, then offer the summary below in one line. Commission wording is ambiguous: "3% listing" usually means the listing side only, with the buyer's agent paid on top. If it could mean a 3% total that includes the buyer's agent, say how you read it in the hand-over.
- **Built-in market (Florida, Stellar):** summarize the defaults the agent is most likely to have opinions on, in plain words: title fees, who pays title in their county, and whether their city has millage. Commissions aren't built in (they're negotiable and not set by law): ask for the agent's standard listing and buyer-side terms if they want nets without typing them each time. Ask what they'd like to change. Most agents change one or two things or nothing.
- **Anything else:** go through the `missing` groups in the order the agent's work needs them. Closing costs and brokerage matter for net sheets, contract dates for timelines, CMA for pricing. Ask in plain words, a group at a time.
- **Documents help most.** A net sheet, a title company quote or a closing cost worksheet answers most closing cost questions at once. Read it and confirm what you took from it.
- **Published figures** (a state's transfer tax, a county's tax rates, a promulgated title rate table) can be looked up when web search is available. Cite the source in the profile's notes and confirm with the agent. A saved title quote wins over a rate table in every net sheet, so save the quote the agent gives; add a table as well only when they want it for other prices.
- **Contract time rules** (how days count, when a day ends, weekend rollover) come only from the agent's contract form or the agent, never from a web search: forms differ and a wrong rule moves every deadline.
- **Several counties:** one profile with `area` listing them, and what differs by county in `county_overrides`. Asking for the county mostly matters in built-in markets, where county exceptions and millage exist.
- **Local protected classes.** Once per profile, ask whether their state, county or city protects anyone beyond the federal fair housing list (for example age, marital status or source of income). Save what they confirm to `fair_housing.extra_protected_classes`; skip it when they don't know.
- **Unknown stays unknown.** Leave out anything the agent doesn't know. Skills will ask at the time or mark the output Preliminary, which is better than a wrong number on a seller's net sheet.

Read `references/fields.md` when you need the exact meaning or format of a setting.

## 4. Write the File

Fill in `assets/market-profile-template.md`:

- `state` is required; `name`, `area` and `mls` when known.
- Keep only the sections and settings that are the agent's own. Delete every other placeholder line and empty section. Don't copy built-in values into the profile.
- Formats: see `references/fields.md` (rates as decimals, money as whole dollars).
- "What's Customized" lists the agent's values in plain words. "Notes" holds sources and dates. Keep the template's headings as written (Title Case).
- A cost name the agent gives (a transfer tax name saved as `deed_transfer_tax_label`, for example) shows as a row name on net sheets, so save it in Title Case: "Documentary Stamp Tax on the Deed", not "documentary stamp tax on the deed".

Save it as `market-profile-<area>.md` (for example `market-profile-seminole.md`) in the outputs folder (the runtime provides it; never the skill's own folder), then check it:

```
python3 scripts/check_market.py <path> --county <county>
```

Fix anything under `problems`, then check `from_profile`: it lists every setting the profile changes, and each should be one the agent gave you. A `mixed` source means a group of values (title fees) where some come from the profile and the rest are built in.

## 5. Hand It Over

Present the file with a short plain summary: which market, what's customized, and anything still missing that some skills will ask about later. Then one line on keeping it:

- **claude.ai inside a Project** (the conversation has Project files or instructions): "Add this file to your Project files so every chat can use it."
- **Cowork** (you're working in a folder on the agent's computer): save it in that working folder and say where.
- **Otherwise** (a plain claude.ai chat): "Keep this file and share it at the start of a chat when you want these numbers used."
