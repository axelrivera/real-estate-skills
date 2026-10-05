# Eval grader instructions

You grade eval runs of one real estate skill. Repo: `<repo>`. Read-only except the `grading.json` files you write. Your task names the skill (`<skill>`), the iteration (`N`) and the eval ids. Each eval has one or more runs: `out/evals/iteration-N/<skill>/eval-<id>/run-<k>/` (iterations before repeat runs have no `run-<k>/` level: grade `eval-<id>/` itself as the only run).

For each eval id:

1. Read its `expected_output` in `dev/evals/<skill>/evals.json` and split it into separate, checkable expectations (one claim each: a date, a number, a behavior, something the reply must or must not do). Split once per eval and grade every run against the same list: the same texts, in the same order, word for word, so `dev/evals/spread.py` can line the runs up.
2. For each run, read `run-<k>/with_skill/outputs/`: `response.md` (the chat reply; with several messages, one `## Reply` section per message), `friction.md`, and every file. Read PDFs with `pdftotext -layout`; read `.ics`, `.pptx` text and `.json` directly.
3. For a mock-package eval (`mock_package` set), also grade against the answer key at `out/mock-contracts/<starter>/key/*-Answer-Key.json`: contract-timeline against an executed package's deal file, seller-offer-review against an offer's listing file. Dates in the key win over anything else.
4. For an eval that mirrors a manual test case (`manual_case` set, for example `05-seller-offer-review`), also read `out/manual-test/<manual_case>/expected.md` when the kit is built (`make manual-kit`): its numbers come from the skills' scripts at build time. Where it and `expected_output` disagree on a number the inputs settle, the kit's number wins: grade by it and add a failed expectation starting `EVAL DEFECT: stale number` that names both.
5. Same-run consistency: when the expectations say two outputs must agree (the PDF and the reply, the report and the deck, the PDF and the calendar file, the CMA's range and the offer report built from it in the same chat), check the values in both files of that run.
6. When the task asks for it, also read the previous iteration's `grading.json` for the same eval and say for each expectation that failed there whether it passes now.
7. Write one `grading.json` per run, at `run-<k>/with_skill/grading.json`:

   ```json
   {"expectations": [{"text": "...", "passed": true, "evidence": "quote or file:line"}],
    "summary": {"passed": 0, "failed": 0, "total": 0, "pass_rate": 0.0}}
   ```

   Be strict and literal: pass only with concrete evidence from that run. When an expectation is wrong or impossible given the inputs (a defective eval), mark it failed and start its evidence with `EVAL DEFECT:`.
8. Check every reply and file for the legacy form name (FR/BAR; the forms are FAR/BAR), em dashes in prose (a lone one in an empty table cell is fine), and fair-housing problems (describing people instead of the property). Add each one found as a failed expectation (in every run of the eval, passed where it isn't found, so the lists stay aligned).

Finish with a short report: for each eval, passed/total per run and each failed expectation in one line (mark eval defects, and say which runs it failed in); then every real bug you saw in the outputs (a wrong number or date, a contradiction between files), with file evidence. Edit nothing but the `grading.json` files. After grading, the lead runs `dev/evals/spread.py N` to compare the runs.
