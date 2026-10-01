# Eval grader instructions

You grade eval runs of one real estate skill. Repo: `<repo>`. Read-only except the `grading.json` files you write. Your task names the skill (`<skill>`), the iteration (`N`) and the eval ids.

For each eval id:

1. Read its `expected_output` in `dev/evals/<skill>/evals.json` and split it into separate, checkable expectations (one claim each: a date, a number, a behavior, something the reply must or must not do).
2. Read the run in `out/evals/iteration-N/<skill>/eval-<id>/with_skill/outputs/`: `response.md` (the chat reply), `friction.md`, and every file. Read PDFs with `pdftotext -layout`; read `.ics` and `.json` directly.
3. For a mock-package eval (`mock_package` set), also grade against the answer key at `out/mock-contracts/<starter>/key/*-Answer-Key.json`: contract-timeline against an executed package's deal file, seller-offer-review against an offer's listing file. Dates in the key win over anything else.
4. When the task asks for it, also read the previous iteration's `grading.json` for the same eval and say for each expectation that failed there whether it passes now.
5. Write `out/evals/iteration-N/<skill>/eval-<id>/with_skill/grading.json`:

   ```json
   {"expectations": [{"text": "...", "passed": true, "evidence": "quote or file:line"}],
    "summary": {"passed": 0, "failed": 0, "total": 0, "pass_rate": 0.0}}
   ```

   Be strict and literal: pass only with concrete evidence. When an expectation is wrong or impossible given the inputs (a defective eval), mark it failed and start its evidence with `EVAL DEFECT:`.
6. Check every reply and file for the legacy form name (FR/BAR; the forms are FAR/BAR), em dashes in prose (a lone one in an empty table cell is fine), and fair-housing problems (describing people instead of the property). Add each one found as a failed expectation.

Finish with a short report: for each eval, passed/total and each failed expectation in one line (mark eval defects); then every real bug you saw in the outputs (a wrong number or date, a contradiction between files), with file evidence. Edit nothing but the `grading.json` files.
