---
name: agent-profile
description: Creates or updates the real estate agent's profile, a short markdown file the other real estate skills read for the agent's name, team, brokerage, license, contact details, writing voice, disclaimers and brand colors. Use it when the agent says "set up my profile", "save my info", "use my brand colors", "update my phone number / license / brokerage", "change my report colors", shares a logo or website for their branding, or when another skill needs the agent's name or brokerage and no profile exists. Brand colors can come from hex codes, a website, or an image (logo, business card, flyer). Markdown output only.
---

# Agent profile

Writes `agent-profile.md`: who the agent is and how their documents should look. Every other skill reads it when it's available and works without it, so this skill is a convenience, never a requirement.

The agent is usually not technical. Never show YAML, JSON or hex codes unless they ask. Talk about colors by name ("Navy").

Paths below are relative to this skill's folder.

## 1. Look for an existing profile

Check the conversation, the Project files and uploads for a file starting with `profile: agent`. If there is one, this is an update:

```
python3 scripts/read_profile.py <path>
```

Save the profile to a file first if it's only in the conversation. Change only what the agent asks to change and keep everything else.

## 2. Ask for the details

Only **name** and **brokerage** are required. Ask for everything that's missing in one message, and make clear the rest is optional:

- Required: full name as it should appear on documents, brokerage.
- Optional: team name, license number, phone, email, website.
- Optional: writing voice (a sentence or two, or a sample of their writing) and any disclaimers they want on documents.
- Optional: brand colors (step 3).

Don't ask about brokerage or compliance rules. Don't invent anything, and don't fill optional fields they skipped.

## 3. Brand colors (optional)

Offer three ways, in plain words: "If you want your reports in your brand colors, send your logo or another image, your website, or the color codes if you know them. Or skip this and reports use blue for buyers and orange for sellers."

- **Hex codes:** use them as given.
- **Website or image:**
  ```
  python3 scripts/extract_colors.py <image path or website>
  ```
  It returns the main colors by name, a suggested primary, a suggested buyer/seller split when there are two strong colors, and notes. If the website can't be opened, ask for an image instead.

Confirm in words before saving, for example: "Your logo is mostly Navy with Gold accents. Use Navy for all your reports?" Ask about separate buyer and seller colors only when the result has a `split`. Pass on its notes (a color too light for text, a mostly black logo) in plain words. The image is only used to read colors: it's not saved and doesn't go on reports.

## 4. Write the profile

Write the data to a JSON file (fields as in `scripts/render.py`), then:

```
python3 scripts/render.py profile.json
```

It saves `agent-profile.md` to the outputs folder, checks it with the same reader every skill uses, and prints any warnings. Fix and re-run if it reports an error.

## 5. Hand it over

Present the file and give a short summary of what's in it, by name and in plain words. Then tell them how to keep it, in one line:

- **claude.ai Projects:** "Add this file to your Project files so every chat can use it."
- **Cowork:** save it in their working folder.
- **Otherwise:** "Keep this file and share it at the start of a chat when you want your details used."
