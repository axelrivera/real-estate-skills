# Eval grader instructions

You grade eval runs of one real estate skill. Repo: `<repo>`. Read-only except the `grading.json` files you write. Your task names the skill (`<skill>`), the iteration (`N`) and the eval ids. Each eval has one or more runs: `out/evals/iteration-N/<skill>/eval-<id>/run-<k>/` (iterations before repeat runs have no `run-<k>/` level: grade `eval-<id>/` itself as the only run).

Evals grade the model, not the scripts. The scripts write every figure, sentence, note and layout in the files (golden snapshots and the generated tests cover them), so you never re-check the math, a script's wording or a page's layout. What you grade: what the model read and entered, what it asked and declined, which files it made, its judgment fields, and whether its chat reply uses the script's lines.

For each eval id:

1. Read its `expected_output` in `dev/evals/<skill>/evals.json` and split it into separate, checkable expectations (one claim each: a date, a number, a behavior, something the reply must or must not do). Split once per eval and grade every run against the same list: the same texts, in the same order, word for word, so `dev/evals/spread.py` can line the runs up.
2. For each run, read `run-<k>/with_skill/outputs/`: `response.md` (the chat reply; with several messages, one `## Reply` section per message), `friction.md`, every file, and the data file in `_work/` (`deal.json`, `listing.json`, `buyer.json`, `report.json`, `net-sheet.json`). Read PDFs with `pdftotext -layout`; read `.ics`, `.pptx` text and `.json` directly.
3. **Checks first**, before reading for judgment. These are mechanical; record each as an expectation when the eval states it, and add the ones below to every eval:
   - **Numbers come from the script.** A figure the expectations name (a date, a net, a count) is graded where the model put it in: the data file's inputs (the price, the Effective Date, the rider letters, a day count) and the script's output that follows. A figure in the reply must be the run's own script output (as the PDF or a re-run of the data file shows it), never a hand-computed or re-rounded one. A wrong figure traced to an input the model typed is the model's failure; one the script computed wrong from correct inputs is a bug for the report, not a failed expectation.
   - **Judgment only.** The model's fields (the judgment and label fields each skill's data reference lists) are words only, with no digits, `$`, `%` or month names, and the data file has none of the fields the script writes (a CMA's `paragraph` or `key_stats`, `counter.rows`; a deal file's `flags`). The scripts stop on a figure and on those fields (an old deal file's `flags` become agent notes instead), so a run that finished passes unless the model worked around a stop (moved a figure into another field, renamed a field).
   - **Notes once.** Each assumption or estimate is said once in the reply (the script's notes print once in the files); a note the model added is keyed to the script's note it adds to, never a reworded second copy.
4. Then grade the behaviors and judgment: questions asked (and only those), declines, which files were made and presented (and that data files and handoffs weren't), the reply's required lines and length cap, the script's chat lines (`chat_notes`, `reply_lines`, `to_confirm`, `agent_notes`) passed on as the skill says, a judgment inside the bounds the expectation sets (a value range, a list price), and same-chat chains (the CMA built in Reply 1 read by the offer in Reply 2 without an upload).
5. For a mock-package eval (`mock_package` set), also grade against the answer key at `out/mock-contracts/<starter>/key/*-Answer-Key.json`: contract-timeline against an executed package's deal file, seller-offer-review against an offer's listing file. Dates in the key win over anything else. An eval that mirrors a smoke case (`manual_case` set) uses the smoke kit's inputs; its `expected.md` holds only the smoke checks, so grade by `expected_output` alone.
6. Same-run consistency only where the model carries a figure: the reply against the run's script output, and one skill's output read by another in the same chat (the CMA's range in the offer report). The PDF, deck and calendar file agree with each other by construction; don't re-check them.
7. When the task asks for it, also read the previous iteration's `grading.json` for the same eval and say for each expectation that failed there whether it passes now.
8. Write one `grading.json` per run, at `run-<k>/with_skill/grading.json`:

   ```json
   {"expectations": [{"text": "...", "passed": true, "evidence": "quote or file:line"}],
    "summary": {"passed": 0, "failed": 0, "total": 0, "pass_rate": 0.0}}
   ```

   Be strict and literal: pass only with concrete evidence from that run. When an expectation is wrong or impossible given the inputs (a defective eval), mark it failed and start its evidence with `EVAL DEFECT:`.
9. Check every reply and file for the legacy form name (FR/BAR; the forms are FAR/BAR), em dashes in prose (a lone one in an empty table cell is fine), and fair-housing problems (describing people instead of the property). Add each one found as a failed expectation (in every run of the eval, passed where it isn't found, so the lists stay aligned).

Finish with a short report: for each eval, passed/total per run and each failed expectation in one line (mark eval defects, and say which runs it failed in); then every real bug you saw in the outputs (a script figure wrong from correct inputs, a contradiction between the reply and the files), with file evidence. Edit nothing but the `grading.json` files. With two or more runs of an eval, the lead runs `dev/evals/spread.py N` to compare them.
