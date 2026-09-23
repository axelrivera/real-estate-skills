---
name: market-profile
description: Creates or updates a real estate market profile, a markdown file the other real estate skills read for local closing costs, transfer taxes, who pays title, commission defaults, property tax rules and millage, contract deadline rules, CMA adjustments and MLS export formats. Florida and Stellar MLS are built in; any other state or MLS is set up from what the agent provides. Use it whenever the agent says "set up my market", "I work in Texas / Puerto Rico / Miami-Dade", "my title company charges…", "our commission split is…", "use these closing costs", uploads a net sheet or closing cost worksheet to save, or a skill reports missing local costs or rules.
---

# Market profile

Writes a market profile: the local numbers and rules behind net sheets, CMAs, offers and contract timelines. It stores only the agent's own values. Everything else comes from the built-in layers, which keeps profiles short and lets updates to the built-in data reach the agent.

The agent is usually not technical. Talk in money and plain words ("title settlement fee $850"), never field names or YAML.

## 1. Find an existing profile

Look in the conversation, Project files and uploads for files that start with `profile: market`. An agent can have one per market, so match on state and area. If there's a match, this is an update: change only what the agent asks.

## 2. Where do they work?

Ask for the state, the county or area, and the MLS if they know it. Then see what's already known:

```
python3 scripts/check_market.py --state <state> --county <county> [--mls <mls>]
```

For each group of settings it shows the values, where they come from (`state` or `mls` = built in, `county` = a county exception), and what's `missing`. `notes` explains any assumption (for example which MLS was assumed) and should be passed on.

## 3. Fill the gaps, or confirm the built-ins

- **Built-in market (Florida, Stellar):** summarize the defaults the agent is most likely to have opinions on, in plain words: commission split, title fees, who pays title in their county, and whether their city has millage. Ask what they'd like to change. Most agents change one or two things or nothing.
- **Anything else:** go through the `missing` groups in the order the agent's work needs them. Closing costs and brokerage matter for net sheets, contract dates for timelines, CMA for pricing. Ask in plain words, a group at a time.
- **Documents help most.** A net sheet, a title company quote or a closing cost worksheet answers most closing cost questions at once. Read it and confirm what you took from it.
- **Published figures** (a state's transfer tax, a county's millage) can be looked up when web search is available. Cite the source in the profile's notes and confirm with the agent.
- **Unknown stays unknown.** Leave out anything the agent doesn't know. Skills will ask at the time or mark the output Preliminary, which is better than a wrong number on a seller's net sheet.

Read `references/fields.md` when you need the exact meaning or format of a setting.

## 4. Write the file

Fill in `assets/market-profile-template.md`:

- `state` is required; `name`, `area` and `mls` when known.
- Keep only the sections and settings that are the agent's own. Delete every other placeholder line and empty section. Don't copy built-in values into the profile.
- Formats: see `references/fields.md` (rates as decimals, money as whole dollars).
- "What's customized" lists the agent's values in plain words. "Notes" holds sources and dates.

Save it as `market-profile-<area>.md` (for example `market-profile-seminole.md`) in the outputs folder (`/mnt/user-data/outputs/` when it exists), then check it:

```
python3 scripts/check_market.py <path> --county <county>
```

Fix anything under `problems`, then confirm the values show `profile` as their source.

## 5. Hand it over

Present the file with a short plain summary: which market, what's customized, and anything still missing that some skills will ask about later. Then one line on keeping it:

- claude.ai Projects: "Add this file to your Project files so every chat can use it."
- Cowork: save it in their working folder.
- Otherwise: "Keep this file and share it at the start of a chat when you want these numbers used."
