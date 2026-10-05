# Manual Testing

A smoke test of the installed plugin, once per release: about ten yes/no checks in about twenty minutes, in the desktop app (Cowork) and then a shorter pass in claude.ai. It covers only what automation can't reach: the plugin installs, the profile is saved and found, uploads are read, a chat carries the buyer CMA into the offer, and the files are delivered and open (the PowerPoint in PowerPoint or Keynote, the calendar file in a calendar app).

Content, numbers and layout are never reviewed by hand. The math is pinned by the golden snapshots, every page and slide is checked over generated inputs (`make fuzz`), and what Claude reads, asks and writes is graded by the evals ([development.md](development.md#tests)). A wrong number seen during the smoke pass is still a bug: write it in the results and reproduce it with the case's mirroring eval.

## Setup (Once per Release)

1. Build the plugin and the kit:
   ```bash
   make package manual-kit
   ```
   The kit lands in `out/manual-test/` (git-ignored, rebuilt from scratch each run). It needs the local dev setup (`make setup`) and the FAR/BAR PDFs in `sources/` for the contract packages ([mock-contracts.md](mock-contracts.md)).
2. In the desktop app, uninstall any older copy of the plugin and install `dist/real-estate-<version>.plugin`.
3. Create a fresh Cowork working folder for the run.

## The Kit

`out/manual-test/` has one folder per case:

- `prompt.md`: what to upload and the exact prompt to paste (with the "Today is" date).
- The files to upload: mock MLS 360 reports, a listing flyer, CMA exports and seller notes (Casselberry, Seminole County), mock FAR/BAR packages and a made-up Ohio purchase agreement. Streets, names, brokerages and MLS numbers are fictional.
- `expected.md`: the case's yes/no checks and only the reference facts needed to answer them (the expired listing's MLS number, the closing date the calendar should show). Never upload it.

Case 1 builds your real profile; every later case uses it. The test is black box: you upload files, paste prompts and look at what comes back. No step asks for a data file or anything the skill makes along the way.

## Checks

| # | Skill | Upload | Yes or No |
|---|---|---|---|
| 1 | agent-profile | Nothing | The plugin installs and every skill is listed; `profile.md` is saved in the working folder (claude.ai: it comes back as a file to keep) |
| 2 | seller-cma | 360 report (PDF), CMA export (CSV), seller notes; new session | The saved profile is used without an upload (claude.ai: the uploaded one); the uploads are read (the expired listing and the export's sales appear); the listing presentation opens in PowerPoint or Keynote |
| 3 | buyer-cma | Listing flyer, 360 report, CMA export | The buyer CMA PDF is delivered and opens |
| 4 | buyer-offer-strategy | Nothing: same chat as case 3 | The offer uses the buyer CMA without asking for an upload, and both PDFs are delivered |
| 5 | seller-offer-review | The step-1 offer package | The package is read and the offer review PDF is delivered |
| 6 | contract-timeline | Executed FHA package | The calendar file imports into a calendar app with closing on the right date |
| 7 | contract-timeline | Made-up Ohio purchase agreement | The best-effort line is in the chat reply only, never in the PDF or the calendar file |
| 8 | seller-net-sheet | Nothing (the facts are in the prompt) | The net sheet PDF is delivered on one page |

Case 5's `step-2/` folder holds a second offer on the same listing for the evals; the smoke pass doesn't use it.

## claude.ai Pass

1. Run `make package-skills` and upload each zip in `dist/skills/` in claude.ai's skill settings.
2. Run case 1: with no working folder, the profile comes back as a file to keep.
3. Run case 2 (upload the case 1 profile with the inputs) and case 6.

## Results

Fill in `out/manual-test/results.md` as you go (one row per check, a Cowork and a claude.ai column, a note for every No) and share it back. A No is fixed and its case re-run before the release.

## Evals That Mirror a Case

Cases 2 to 8 each have an eval with the same inputs (`"manual_case"` in `dev/evals/<skill>/evals.json`): the kit's own files, read straight from `out/manual-test/<case>/` (so run `make manual-kit` before setting them up), or for case 6 the same mock package. The evals check what the smoke pass doesn't: the facts read from the files, the questions asked, the judgment and the chat reply ([development.md](development.md#evals)).
