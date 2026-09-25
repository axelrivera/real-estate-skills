---
name: agent-profile
description: Sets up the real estate agent in a short, friendly interview and saves one file, profile.md, that every other real estate skill reads for who they are and how their documents look and sound (name, brokerage, license, contact details, brand colors, writing voice and disclaimers). Local costs, taxes and commissions aren't part of it; each report works them out from the listing. Use it whenever the agent says "set me up", "get started", "set up my profile", "save my info", "use my brand colors", "change my report colors", "update my phone / license / brokerage", shares a logo, business card or website for their branding, or another skill needs their name or brokerage and no profile exists.
---

# Agent Profile

Sets the agent up in about two minutes and saves one file, `profile.md`: who they are and how their documents look and sound. Every other skill reads it when it's there and still works without it, so this is a convenience, never a gate.

It holds nothing about markets or costs. Each skill takes the location from the listing and uses built-in local values or labeled estimates, and the agent corrects them on the report if they want to.

The agent is usually not technical and often a little nervous about setup. Keep YAML, JSON, field names and color codes out of replies unless they ask; talk about colors by name ("Navy").

## Guardrails

These apply to everything this skill writes: files, chat replies, and text the agent may forward to a client.

- **Fair housing.** Every other skill writes in the voice saved here, so the voice and disclaimers never target or exclude people by a protected class ("first-time buyers" or "relocation" is fine; "young families" is not). Describe the property, the numbers and the terms, never people: not who the home suits, who should buy, or who lives nearby. No claims about safety, crime, school quality or who makes up an area. The protected classes are race, color, religion, sex, disability, familial status and national origin, plus sexual orientation, gender identity and any state or local class the agent mentions. Read `references/fair-housing.md` before saving a voice or disclaimers. If the agent asks for wording that breaks this, write the compliant version and say why in one sentence; don't lecture or flag innocent wording like "family room".
- **No em dashes in prose,** chat included: use a comma, colon, parentheses or a new sentence. A lone em dash for an empty value (a table cell with nothing in it) is fine.
- **Labels in Title Case:** headings, column headers, row names, tiles, legend entries, card and slide titles. Sentences, notes and table values stay sentence case.

## 1. Find an Existing Profile

Look for a file that starts with `profile: agent` in the places `references/saved-files.md` lists: the conversation, Project files, then the saved folder in the agent's Cowork working folder.

If there is one, this is an update, not an interview. Change only what the agent asks, keep the rest (and their formatting, such as how they write their phone), then go to step 5. A move to a new brokerage often changes the team name, email, website and disclaimers too: ask about those in one line instead of changing them.

## 2. The Interview

Two rounds, one message each, at most three questions per round. Short rounds feel easy, and the second can react to the first.

- **Every question can be skipped,** and "not sure" is an answer. Say so once, in the opener.
- **Fill-in-the-blank with examples in the question,** so it's close to multiple choice and answerable from memory in one line.
- **Messy answers are fine.** Take what they give, never ask the same thing twice, and drop any question they already answered (in their first message, an upload, or a file).
- **No jargon in the questions:** not "brand voice", "value proposition" or "profile fields".
- **Fast path.** When the agent says "just do it", "skip the rest" or stops answering, stop asking and save what you have.

**Round 1: The Basics.** When the agent's first message already covers some of this, thank them for it and ask only for the rest.

> I'll set you up so every report carries your name, your look and your voice. Two quick rounds, about two minutes. Skip anything you like.
>
> 1. Your name as it should appear on documents, and your brokerage's licensed name (for example "Keller Williams Realty Heathrow", not a team name): ____
> 2. Team name, if you're on one: ____
> 3. What should show on your reports: phone, email, website, license number. Any or none: ____
>
> One reply is perfect, short and messy is fine.

Once name and brokerage are known, write the file (step 5) before sending Round 2, and say so in one line ("Saved. One more quick round."). A profile they can use now beats a finished questionnaire.

**Round 2: Your Look and Sound.**

> 4. Want your reports in your brand colors? Drop your logo, a business card or your website. Or say "pick for me", or skip it (buyer reports are blue, seller reports orange): ____
> 5. Anything your brokerage requires on documents? (for example "Each office independently owned and operated"). Skip if not sure: ____
> 6. How would a client describe the way you talk? Direct, no fluff | warm and patient | calm and numbers-first | high-energy | like a friend who knows the business. Pick one or say it your way. If you like, paste an email you've written: ____

If they sent colors, read them first (step 3) and confirm them in your reply.

## 3. Brand Colors

Read `references/brand-colors.md` before this step. In short: take an image, a website or color codes; run `scripts/extract_colors.py` for images and websites; propose one direction and confirm it by name. Offer at most one alternative. When they say "pick for me" with no logo, suggest Navy or Charcoal, which read well on white, and say why in one line.

## 4. Voice

Write the Voice section from their Round 2 pick, how they actually typed their answers, and the email they pasted, in their words over marketing words: two to four lines covering the tone, a phrase or two they really use, and anything to avoid. Skipped means no Voice section; the skills then write plainly.

## 5. Write the File

Fill in `assets/profile-template.md`:

- Leave out every line and section the agent didn't give. Missing fields are skipped on documents, never shown empty, and a guessed license number or phone would end up on client documents. Never leave placeholders.
- Only **name** and **brokerage** are required. Client files refuse to print the agent's name without the brokerage's licensed name (Florida rule 61J2-10.025 and most states). For an agent licensed in more than one state, or in a state that wants more on client materials, read `references/licensing.md`.
- Write every number (license, phone) in double quotes: unquoted, `0123456` would be read as a different number. Write a double quote inside a value as `\"`.
- The line under the heading is `Team · Brokerage`; without a team it's just the brokerage.
- In `brand`, keep either `primary` (one color) or `buyer_primary` and `seller_primary` (two), with the color name as the comment. The Brand Colors section says it in words: "Navy for all reports."
- Keep the template's headings as written (Title Case): the other skills find the sections by heading.

Save it as `profile.md` where `references/saved-files.md` says. Then check it:

```
python3 scripts/check_profile.py <path to profile.md>
```

Fix anything under `problems` and check again. Pass on `warnings` in plain words.

## 6. Hand It Over

Present the file with a short summary in plain words: who, which details are saved, which colors. Then say where it's kept, or give the one line on keeping it, as `references/saved-files.md` describes, and end with one next step: "Try it: send me a listing and ask for a CMA."

If the agent asks to save local costs or commission terms here, say they don't need to: every report estimates them from the listing, labels the estimates, and takes their numbers when they share them on that report.
