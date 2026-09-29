# Manual Testing

A short smoke test of the installed plugin before each release: one happy path per skill, run by hand in the desktop app (Cowork), then a shorter pass in claude.ai. The kit generator builds every file you upload, the prompts and the expected facts; you only upload files and paste prompts.

## Setup (Once per Release)

1. Build the plugin and the kit:
   ```bash
   make package manual-kit
   ```
   The kit lands in `out/manual-test/` (git-ignored, rebuilt from scratch each run). It needs the local dev setup (`make setup`) and the FR/BAR PDFs in `sources/` for the contract packages ([mock-contracts.md](mock-contracts.md)).
2. In the desktop app, uninstall the old `core` and `transactions` plugins if they're still there, install `dist/real-estate-<version>.plugin`, and confirm the six `real-estate:*` skills are listed and nothing else from this repo.
3. Create a fresh Cowork working folder for the run.

## The Kit

`out/manual-test/` has one folder per case, and each case runs on its own:

- `prompt.md`: what to upload and the exact prompt to paste (with the "Today is" date the expected dates assume).
- The files to upload: mock MLS 360 reports, a listing flyer, CMA exports and seller notes (Casselberry, Seminole County), a buyer CMA handoff, mock FR/BAR packages, and a made-up Ohio purchase agreement. Streets, names, brokerages and MLS numbers are fictional.
- `expected.md`: the facts to check, computed by the skills' own scripts when the kit was built. Value ranges and prices are Claude's judgment, so those come with a sanity band instead of an exact number.

Never upload `expected.md`. Case 1 builds your real profile; every later case uses it.

## Cases

| # | Skill | Upload | Prompt to Paste | Pass Checks |
|---|---|---|---|---|
| 1 | agent-profile | Nothing | "Set up my profile.", then answer with your own details | At most two rounds of questions; saves `.claude/real-estate/profile.md`; no placeholders or made-up details |
| 2 | seller-cma | 360 report, CMA export, seller notes (new session) | "What should we list at?", then "build the listing presentation", then "add that the home is perfect for young families" | Uses the saved profile without an upload; PDF in the profile's colors; flags the 2017 expired listing; net sheet marks the 5% brokerage "Assumed"; PPTX opens with the same numbers; the fair-housing request is declined in one sentence |
| 3 | buyer-cma | Listing flyer, 360 report, CMA export | "Is it priced right and what should we offer?" | PDF with the range, the history with both price cuts and the scatterplot; facts and tax match expected.md |
| 4 | buyer-offer-strategy | The `.cma.json` handoff; the buyer's limits are in the prompt | "Help me write the offer" with cash, max price, loan and payment cap | Offer Options and Offer Package Worksheet PDFs; stays inside every limit; riders named by letter; worksheet shows offer terms only |
| 5 | seller-offer-review | Step 1: the first offer; step 2: a second offer on the same listing | "Should my seller accept?", then "compare both and give me a plan" | Single-offer net and counter; AGA-1 handled; ranking and plan; no past dates in next steps |
| 6 | contract-timeline | Executed FHA package (`asis-fha-executed`) | "Give me every deadline as a PDF and a calendar file" | Deadlines match expected.md; the ICS imports into a calendar with the right dates |
| 7 | contract-timeline | Executed short sale package (`asis-short-sale-rent-back`) | Same as 6 | Two-phase timeline ("N days after short sale approval" rows); the PDF builds with no closing date |
| 8 | contract-timeline | Made-up Ohio purchase agreement | Same as 6 | Timeline from the contract's own dates and rules; the best-effort disclaimer in chat only, not in the PDF or ICS |

The exact prompts are in each case's `prompt.md`; `expected.md` repeats the checks for that case.

## claude.ai Pass

Shorter, to confirm the uploaded skills work outside Cowork:

1. Run `make package-skills` and upload each zip in `dist/skills/` in claude.ai's skill settings.
2. Run case 1: with no working folder, the profile is handed over in chat or as a file to keep.
3. Run case 2 (upload the case 1 profile with the inputs) and case 6.

## Results

Fill in `out/manual-test/results.md` as you go (one row per check, a Cowork and a claude.ai column, a note for every failure) and share it back.
