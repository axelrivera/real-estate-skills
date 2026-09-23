---
name: agent-profile
description: Creates or updates the real estate agent's profile, a short markdown file the other real estate skills read for the agent's name, team, brokerage, license, contact details, writing voice, disclaimers and brand colors. Use it whenever the agent says "set up my profile", "save my info", "use my brand colors", "update my phone / license / brokerage", "change my report colors", shares a logo or website for their branding, or another skill needs their name or brokerage and no profile exists. Brand colors can come from color codes, a website, or an image (logo, business card, flyer).
---

# Agent profile

Writes `agent-profile.md`: who the agent is and how their documents should look. Other skills read it when it's available and still work without it, so this is a convenience, never a gate.

The agent is usually not technical. Keep YAML, JSON and color codes out of replies unless they ask, and talk about colors by name ("Navy").

## 1. Find an existing profile

Look in the conversation, Project files and uploads for a file that starts with `profile: agent`. If there is one, this is an update: read it, change only what the agent asks, and keep the rest.

## 2. Ask for what's missing

Only **name** and **brokerage** are required. Ask for everything missing in one message and make clear the rest is optional:

- Required: name as it should appear on documents; brokerage.
- Optional: team name, license number, phone, email, website; writing voice (a sentence, or a sample of their writing); disclaimers for documents; brand colors.

Don't ask about brokerage or compliance rules; that's the agent's call. Don't fill in anything they skipped, because a guessed license number or phone ends up on client documents.

## 3. Brand colors (optional)

Read `references/brand-colors.md` before this step. In short: take color codes, a website or an image; run `scripts/extract_colors.py` for websites and images; confirm the result by name before saving.

## 4. Write the file

Fill in `assets/agent-profile-template.md`:

- Leave out every line and section the agent didn't give (team, license, contact, brand, voice, disclaimers). Missing fields are skipped on documents, never shown empty.
- In `brand`, keep either `primary` (one color) or `buyer_primary` and `seller_primary` (two), with the color name as the comment.
- Keep values in double quotes; write a double quote inside a value as `\"`.
- The "Brand colors" line says it in words: "Navy for all reports." or "Navy for buyer reports, Gold for seller reports."

Save it as `agent-profile.md` in the outputs folder (`/mnt/user-data/outputs/` when it exists), then check it:

```
python3 scripts/check_profile.py <path to agent-profile.md>
```

Fix anything under `problems` and check again. Pass on `warnings` in plain words.

## 5. Hand it over

Present the file with a short summary in plain words (who, which details are saved, which colors). Then one line on keeping it:

- claude.ai Projects: "Add this file to your Project files so every chat can use it."
- Cowork: save it in their working folder.
- Otherwise: "Keep this file and share it at the start of a chat when you want your details used."
