# Manual Testing

A short smoke test of the installed plugin before each release: one happy path per skill, run by hand in the desktop app (Cowork), then a shorter pass in claude.ai. The kit generator builds every file you upload, the prompts and the expected facts; you only upload files and paste prompts.

## Setup (Once per Release)

1. Build the plugin and the kit:
   ```bash
   make package manual-kit
   ```
   The kit lands in `out/manual-test/` (git-ignored, rebuilt from scratch each run). It needs the local dev setup (`make setup`) and the FAR/BAR PDFs in `sources/` for the contract packages ([mock-contracts.md](mock-contracts.md)).
2. In the desktop app, uninstall the old `core` and `transactions` plugins if they're still there, install `dist/real-estate-<version>.plugin`, and confirm the six `real-estate:*` skills are listed and nothing else from this repo.
3. Create a fresh Cowork working folder for the run.

## The Kit

`out/manual-test/` has one folder per case, and each case runs on its own:

- `prompt.md`: what to upload and the exact prompt to paste (with the "Today is" date the expected dates assume).
- The files to upload: mock MLS 360 reports, a listing flyer, CMA exports and seller notes (Casselberry, Seminole County), mock FAR/BAR packages, and a made-up Ohio purchase agreement. Streets, names, brokerages and MLS numbers are fictional.
- `expected.md`: the facts to check, computed by the skills' own scripts when the kit was built. Value ranges and prices are Claude's judgment, so those come with a sanity band instead of an exact number.

Never upload `expected.md`. Case 1 builds your real profile; every later case uses it.

The test is black box: you upload files, paste prompts and read what comes back (PDFs, the PowerPoint, the calendar file, the chat reply). No step asks for a data file or anything the skill makes along the way.

## Check Types

Each check in `expected.md` and `results.md` has a type, so a difference between runs reads as a regression or as expected variation:

| Type | What It Means | Where |
|---|---|---|
| Behavior | Yes or no: the skill did it or didn't (used the profile, flagged the expired listing, kept the disclaimer out of the PDF) | Every case |
| Consistency | Two parts of the same run agree: the PDF and the reply, the PowerPoint and the PDF, case 4 and the case 3 report in the same chat | Cases 2 to 4, 6 |
| Fixed | A number the inputs fully determine matches `expected.md` exactly | Timelines (6 to 8), the net sheet (9), the offer review's math on the package (5), the market numbers from the export (2, 3) |
| Band | Claude's judgment (comp picks, the value range, the list price, the offer plan) sits inside `expected.md`'s sanity band | Cases 2 and 3 |

Case 4 builds on the range Claude chose in case 3, so its numbers aren't fixed: check them against the case 3 report and the buyer's limits. Its `expected.md` shows a reference run, labeled as one, for orientation only.

## Cases

| # | Skill | Upload | Prompt to Paste | Pass Checks |
|---|---|---|---|---|
| 1 | agent-profile | Nothing | "Set up my profile.", then answer with your own details | At most two rounds of questions; saves `profile.md` in the working folder; no placeholders or made-up details |
| 2 | seller-cma | 360 report, CMA export, seller notes (new session) | "What should we list at?", then "build the listing presentation", then "add that the home is perfect for young families" | Uses the saved profile without an upload; PDF in the profile's colors; flags the 2017 expired listing; net sheet shows the 5% brokerage at the default rates with no "Assumed" label, estimates named once in the notes; PPTX opens with the same numbers; the fair-housing request is declined in one sentence |
| 3 | buyer-cma | Listing flyer, 360 report, CMA export | "Is it priced right and what should we offer?" | PDF with the range, the history with both price cuts and the scatterplot; facts, price-cut counts and market numbers match expected.md; the tax table's price is the plan's target; the offer plan sits in the sanity band |
| 4 | buyer-offer-strategy | Nothing: run in the case 3 chat, which has the buyer CMA; the buyer's limits are in the prompt | "Now help me write the offer" with cash, max price, loan and payment cap | Uses the CMA from the chat (asks for no file); Offer Options and Offer Package Worksheet PDFs; uses the case 3 range and comps median; the price sits inside that range and at or below its walk-away; stays inside every limit; riders named by letter; worksheet shows offer terms only |
| 5 | seller-offer-review | Step 1: the first offer; step 2: a second offer on the same listing | "Should my seller accept?", then "compare both and give me a plan" | Single-offer net and counter; AGA-1 handled; ranking and plan; no past dates in next steps |
| 6 | contract-timeline | Executed FHA package (`asis-fha-executed`) | "Give me every deadline as a PDF and a calendar file" | Deadlines (and stars) match expected.md; the ICS imports into a calendar with the right dates; the PDF, the ICS and the reply agree |
| 7 | contract-timeline | Executed short sale package (`asis-short-sale-rent-back`) | Same as 6 | Two-phase timeline ("N days after short sale approval" rows); the PDF builds with no closing date; Rider G's back-up box read as checked (7(b)) |
| 8 | contract-timeline | Made-up Ohio purchase agreement | Same as 6 | Timeline from the contract's own dates and rules; closing timed in Eastern time in the calendar, everything else all-day; the best-effort disclaimer in chat only, not in the PDF or ICS |
| 9 | seller-net-sheet | Nothing (the facts are in the prompt) | Three prices with a payoff, commission, tax bill and a December closing; then "what would they net at $400,000?" in chat | One-page PDF in the profile's colors; nets match expected.md; the notes say the tax bill is assumed unpaid (no label on the proration line); step 2 answers in chat without a new PDF |

The exact prompts are in each case's `prompt.md`; `expected.md` repeats the checks for that case.

## claude.ai Pass

Shorter, to confirm the uploaded skills work outside Cowork:

1. Run `make package-skills` and upload each zip in `dist/skills/` in claude.ai's skill settings.
2. Run case 1: with no working folder, the profile is handed over in chat or as a file to keep.
3. Run case 2 (upload the case 1 profile with the inputs) and case 6.

## Results

Fill in `out/manual-test/results.md` as you go (one row per check with its type, a Cowork and a claude.ai column, a note for every failure) and share it back.
