---
name: agent-profile
description: Sets up the real estate agent in a short, friendly interview and saves profile.md, which every other real estate skill reads for who they are and how their documents look and sound (name, brokerage, license, contact details, brand colors, writing voice and disclaimers), plus ready-to-paste project instructions and the steps to set up a claude.ai or Cowork Project with both. Local costs, taxes and commissions aren't part of it; each report works them out from the listing. Use it whenever the agent says "set me up", "get started", "set up my profile", "save my info", "set up a project", "project instructions", "make Claude remember me", "use my brand colors", "change my report colors", "update my phone / license / brokerage", shares a logo, business card or website for their branding, or another skill needs their name or brokerage and no profile exists.
---

# Agent Profile

Sets the agent up in about two minutes and saves `profile.md`: who they are and how their documents look and sound. Every other skill reads it when it's there and still works without it, so this is a convenience, never a gate. Alongside it goes `project-instructions.md`, a short prompt the agent pastes into a claude.ai or Cowork Project, so every chat there starts knowing who they are and which skills to use.

It holds nothing about markets or costs. Each skill takes the location from the listing and uses built-in local values or estimates (named once in each report's notes), and the agent corrects them on the report if they want to.

**Costs and commission.** When the agent asks to save costs, fees or commission terms here, save none of them. Add one line at the end of the reply: the profile never holds costs, because they change with each deal and area; each report assumes 5% total commission and local estimates, labels them, and takes their own numbers when they give them on that report. When that's the whole request, that line is the answer, plus one line offering to set up the profile if none exists.

The agent is usually not technical and often a little nervous about setup. Keep YAML, JSON, field names and color codes out of replies unless they ask; talk about colors by name ("Navy").

## Guardrails

These apply to everything this skill writes: files, chat replies, and text the agent may forward to a client.

- **Fair housing.** Every other skill writes in the voice saved here, so the voice and disclaimers never target or exclude people by a protected class ("first-time buyers" or "relocation" is fine; "young families" is not). Describe the property, the numbers and the terms, never people: not who the home suits, who should buy, or who lives nearby. No claims about safety, crime, school quality or who makes up an area. The protected classes are race, color, religion, sex, disability, familial status and national origin, plus sexual orientation, gender identity and any state or local class the agent mentions. Read `references/fair-housing.md` before saving a voice or disclaimers. If the agent asks for wording that breaks this, propose the compliant version, say why in one sentence, and save it only once they confirm (step 4); don't lecture or flag innocent wording like "family room".
- **No em dashes in prose,** chat included: use a comma, colon, parentheses or a new sentence. A lone em dash for an empty value (a table cell with nothing in it) is fine.
- **Labels in Title Case:** headings, column headers, row names, tiles, legend entries, card and slide titles. Sentences, notes and table values stay sentence case.

## 1. Find an Existing Profile

Look for a file that starts with `profile: agent` in the places `references/saved-files.md` lists: the conversation (pasted or uploaded), Project files, then the agent's Cowork working folder.

If there is one, this is an update, not an interview. Change only what the agent asks and keep the rest. Write new values in the style the saved file already uses, not as typed: a new phone typed 321-555-0142 goes in as "(321) 555-0142" when the saved phone reads "(407) 555-0100". Then go to step 5. When they only ask how to set up a Project, skip the profile and go to step 6, which still writes `project-instructions.md` (step 5) when the conversation doesn't have one. A move to a new brokerage often changes the team name, email, website and disclaimers too: ask about those in one line instead of changing them, with the new brokerage's licensed name in the same line when the name given is a brand (no example name there).

## 2. The Interview

Two rounds, one message each, at most three questions per round. Short rounds feel easy, and the second can react to the first.

- **The cap counts everything you ask in the message:** Round 1 leftovers, a color confirmation, a voice confirmation, the licensed-name check. Fold leftovers into the next round; merge related ones into one numbered line (team with contact details; the licensed name with the documents question). Order, both for what makes the cut and how it reads: confirmations first (a color, a Voice rewrite, the licensed-name check for a franchise brand), then Round 1 leftovers, then the Round 2 questions by number; hold the rest for a third message, the last one. A merged numbered line counts as one question, and a detail folded into a confirmation (her tone into the Voice confirmation) adds none. Never exceed the cap.
- **Every question can be skipped,** and "not sure" is an answer. Say so once, in the opener.
- **Fill-in-the-blank with examples in the question,** so it's close to multiple choice and answerable from memory in one line.
- **Messy answers are fine.** Take what they give, never ask the same thing twice, and drop any question they already answered (in their first message, an upload, or a file).
- **No jargon in the questions:** not "brand voice", "value proposition" or "profile fields".
- **Fast path.** When the agent says "just do it", "skip the rest" or stops answering, stop asking and save what you have.

**Round 1: The Basics.** When the agent's first message already covers some of this, thank them for it and ask only for the rest.

> I'll set you up so every report carries your name, your look and your voice. Two quick rounds, about two minutes. Skip anything you like, and "not sure" is an answer too.
>
> 1. Your name as it should appear on documents, and your brokerage's licensed name (for example "Lakeshore Realty Group, LLC", not a team name): ____
> 2. Team name, if you're on one: ____
> 3. What should show on your reports: phone, email, website, license number. Any or none: ____
>
> One reply is perfect, short and messy is fine.

**Brokerage name.** A franchise brand or short form ("Keller Williams", "Coldwell Banker", "RE/MAX", "Premier Sotheby's") is often not the licensed name. Save it as given, never guess the entity, and confirm the licensed name in the next round, merged with question 5, using the neutral example from question 1 ("for example 'Lakeshore Realty Group, LLC'"), not a guessed name.

Once name and brokerage are known, write the file (step 5) before sending Round 2. This mid-interview reply is one short thanks when their first message covered a lot, then "Saved. One more quick round." plus the Round 2 questions, then the one line on keeping the file from `references/saved-files.md` for where the agent is (in Cowork with a working folder, the path instead). No Project steps and no project instructions yet; those come with the final hand-over. A profile they can use now beats a finished questionnaire.

**Round 2: Your Look and Sound.**

> 4. Want your reports in your brand colors? Drop your logo, a business card or your website. Or say "pick for me", or skip it (buyer reports are blue, seller reports orange): ____
> 5. Anything your brokerage requires on documents? (for example "Each office independently owned and operated"). Skip if not sure: ____
> 6. How would a client describe the way you talk? Direct, no fluff | warm and patient | calm and numbers-first | high-energy | like a friend who knows the business. Pick one or say it your way. If you like, paste an email you've written: ____

If they sent a logo, card or website, read the colors first (step 3) and confirm them in your reply; the confirmation takes question 4's place. A color they named themselves ("navy, #1B2A4A") is already confirmed: save it and drop question 4.

## 3. Brand Colors

Read `references/brand-colors.md` before this step. In short: take an image, a website or color codes; run `scripts/extract_colors.py` for images and websites; propose one direction and confirm it by name. Offer at most one alternative. When they say "pick for me" with no logo, suggest Navy or Charcoal, which read well on white, and say why in one line.

## 4. Voice

Write the Voice section from their Round 2 pick, how they actually typed their answers, and the email they pasted, in their words over marketing words: two to four lines covering the tone, a phrase or two they really use, and anything to avoid. Skipped means no Voice section; the skills then write plainly.

When their wording breaks fair housing (see Guardrails), keep what's legitimate: the niche as a kind of client or deal ("first-time and move-up buyers"), the area ("the Sanford area") and the tone ("plain-spoken"). Propose the compliant version in the reply, say why in one sentence, and ask them to confirm it (a confirmation, counted in the cap). Never save a rewritten Voice before they confirm it: save the rest of the profile without the Voice section until then.

## 5. Write the File

Fill in `assets/profile-template.md`:

- Leave out every line and section the agent didn't give. Missing fields are skipped on documents, never shown empty, and a guessed license number or phone would end up on client documents. Never leave placeholders.
- Only **name** and **brokerage** are required. Client files refuse to print the agent's name without the brokerage's licensed name (Florida rule 61J2-10.025 and most states). For an agent licensed in more than one state, or in a state that wants more on client materials, read `references/licensing.md`.
- Write every number (license, phone) in double quotes: unquoted, `0123456` would be read as a different number. Write a double quote inside a value as `\"`.
- The line under the heading is `Team · Brokerage`; without a team it's just the brokerage.
- In `brand`, keep either `primary` (one color) or `buyer_primary` and `seller_primary` (two), with the color name as the comment. The Brand Colors section says it in words: "Navy for all reports.", or with two colors "Navy for buyer reports, Burnt orange for seller reports."
- Keep the template's headings as written (Title Case): the other skills find the sections by heading.

Save it as `profile.md` where `references/saved-files.md` says. Then check it:

```
python3 scripts/check_profile.py <path to profile.md>
```

Fix anything under `problems` and check again. Pass on `warnings` in plain words.

**Project instructions.** When the interview is done (after the last round, or when they stop answering), fill in `assets/project-instructions-template.md` and save it as `project-instructions.md` next to the profile. It names only the agent; everything else comes from the profile, so the two never disagree. Keep it as written: it's what makes a Project use the skills and the profile. On an update, rewrite it only when the name changed, but write it when none exists yet (no `project-instructions.md` in the conversation and no Project instructions starting with "Real Estate Assistant for"), so the hand-over has something to paste. Don't write it after Round 1 alone: the agent is still mid-interview.

## 6. Hand It Over

This is the final hand-over, after the interview or an update. Present `project-instructions.md` (including one written just now on an update or a Project-only request) and the profile when it changed; an unchanged profile isn't handed back. Write the reply from `assets/handover-template.md`, in its order and nothing else. The reply is where the agent learns how to use the profile, so "Using your profile" is always there: where Claude finds it now (`references/saved-files.md`) and the other ways it works. The Project instructions only tell a Project's chats to use it.

- **Project steps** (`references/project-setup.md`): the steps for where the agent is now. When the conversation doesn't show where the agent is (a Cowork working folder or task, or claude.ai Project files), give the claude.ai steps and always add the Cowork line; never assume the surface. Skip them when this chat is already in a Project that has the instructions and only the profile changed; then "Using your profile" says to replace profile.md in the Project files, or that it was updated in place.
- **Try it:** leave it out on a Project-only request, and while the licensed brokerage name is still open.

Keep it to what a phone screen shows: at most about 200 words besides the numbered steps, no file contents, field names or color codes.
