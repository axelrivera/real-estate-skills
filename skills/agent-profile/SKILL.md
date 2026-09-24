---
name: agent-profile
description: Creates or updates the real estate agent's profile, a short markdown file the other real estate skills read for the agent's name, team, brokerage, license, contact details, writing voice, disclaimers and brand colors. Use it whenever the agent says "set up my profile", "save my info", "use my brand colors", "update my phone / license / brokerage", "change my report colors", shares a logo or website for their branding, or another skill needs their name or brokerage and no profile exists. Brand colors can come from color codes, a website, or an image (logo, business card, flyer).
---

# Agent Profile

Writes `agent-profile.md`: who the agent is and how their documents should look. Other skills read it when it's available and still work without it, so this is a convenience, never a gate.

The agent is usually not technical. Keep YAML, JSON and color codes out of replies unless they ask, and talk about colors by name ("Navy").

## Guardrails

These apply to everything this skill writes: files, chat replies, and text the agent may forward to a client.

- **Fair housing.** Every other skill writes in the voice saved here, so the voice and disclaimers never target or exclude people by a protected class ("first-time buyers" or "relocation" is fine; "young families" is not). Describe the property, the numbers and the terms, never people: not who the home suits, who should buy, or who lives nearby. No claims about safety, crime, school quality or who makes up an area. The protected classes are race, color, religion, sex, disability, familial status and national origin, plus sexual orientation, gender identity and any listed in the market profile's `fair_housing.extra_protected_classes`. Read `references/fair-housing.md` before saving a voice or disclaimers. If the agent asks for wording that breaks this, write the compliant version and say why in one sentence; don't lecture or flag innocent wording like "family room".
- **No em dashes in prose,** chat included: use a comma, colon, parentheses or a new sentence. A lone em dash for an empty value (a table cell with nothing in it) is fine.
- **Labels in Title Case:** headings, column headers, row names, tiles, legend entries, card and slide titles. Sentences, notes and table values stay sentence case.

## 1. Find an Existing Profile

Look for a file that starts with `profile: agent` in the places `references/saved-files.md` lists: the conversation, Project files, then the saved folder in the agent's Cowork working folder. If there is one, this is an update: edit that file in place, change only what the agent asks, keep the rest (and their formatting, such as how they write their phone), then go to step 4's check. A move to a new brokerage often changes the team name, email, website and disclaimers too: ask about those in one line instead of changing them.

## 2. Ask for What's Missing

Only **name** and **brokerage** are required. Ask for everything missing in one message and make clear the rest is optional:

- Required: name as it should appear on documents; brokerage.
- Optional: team name, license number, phone, email, website; writing voice (a sentence, or a sample of their writing); disclaimers for documents (what the brokerage requires, such as "Each office independently owned and operated" or "Equal Housing Opportunity"): every file the skills make prints them verbatim at the end; brand colors.
- **Brokerage:** ask for the brokerage's licensed name (as on the license), not a trade name or team name. Client files refuse to print the agent's name without it (Florida rule 61J2-10.025 and most states).
- **Licenses and brokerage details** (optional): an agent licensed in more than one state, or in a state that wants more on client materials (a license number, the broker's office address and phone), lists them as `licenses` and `brokerage_license`, `brokerage_address`, `brokerage_phone`. Read `references/licensing.md` when the agent works outside Florida or asks what their documents must show.

Don't ask about brokerage or compliance rules; that's the agent's call. Don't fill in anything they skipped, because a guessed license number or phone ends up on client documents. Write every number (license, phone) in quotes: unquoted, `0123456` would be read as a different number, and the check refuses it.

If they already sent a logo, website or color codes, read the colors first (step 3) and put the color confirmation in this same message, so the agent answers once. Skip the colors question when they already named their colors.

Once name and brokerage are known, write the file in this same turn (steps 4 and 5) rather than waiting: the optional details and a color confirmation go in the hand-over message, and the file is updated when the agent replies. A profile they can use now beats a questionnaire.

## 3. Brand Colors (Optional)

Read `references/brand-colors.md` before this step. In short: take color codes, a website or an image; run `scripts/extract_colors.py` for websites and images; confirm the result by name before saving. Confirming colors and asking for the optional details in one message is preferred.

## 4. Write the File

Fill in `assets/agent-profile-template.md`:

- Leave out every line and section the agent didn't give (team, license, contact, brand, voice, disclaimers). Missing fields are skipped on documents, never shown empty.
- The line under the heading is `Team · Brokerage`; without a team it's just the brokerage.
- In `brand`, keep either `primary` (one color) or `buyer_primary` and `seller_primary` (two), with the color name as the comment.
- Keep values in double quotes; write a double quote inside a value as `\"`.
- Keep the template's headings as written (Title Case); the other skills find the sections by heading.
- The "Brand Colors" section says it in words: "Navy for all reports." or "Navy for buyer reports, Gold for seller reports."

Save it as `agent-profile.md` where `references/saved-files.md` says: the saved folder in Cowork, otherwise the outputs folder. Then check it:

```
python3 scripts/check_profile.py <path to agent-profile.md>
```

Fix anything under `problems` and check again. Pass on `warnings` in plain words.

## 5. Hand It Over

Present the file with a short summary in plain words (who, which details are saved, which colors). Then say where it's kept, or give the one line on keeping it, as `references/saved-files.md` describes.
